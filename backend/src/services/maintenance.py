"""Planned-maintenance exemption lifecycle: draft entry, freeze on effect, revoke and invalidation."""
import time
from fastapi import HTTPException
from sqlalchemy import select, func
from src.models import Job, Maintenance, MaintenanceVersion, ExemptionChannel
from src.services import audit
from src.services.exemption_math import (
    day_list, format_moment, minutes_by_day, parse_moment, split_interval, total_minutes,
)
from src.constants.enums import MaintenanceStatus

CHANNEL_OPTIONS = ('新闻一频', '文化二频', '城市直播')


def _channel_row(db, channel, create=False):
    row = db.scalar(select(ExemptionChannel).where(ExemptionChannel.channel == channel))
    if row is None and create:
        row = ExemptionChannel(channel=channel, revision=0, updated_at=time.time())
        db.add(row)
        db.flush()
    return row


def lock_channel(db, channel, create=False):
    """Serialise revision changes and approvals per channel (no-op lock on SQLite)."""
    _channel_row(db, channel, create=create)
    if create:
        db.flush()
    row = db.scalar(select(ExemptionChannel).where(ExemptionChannel.channel == channel).with_for_update())
    return row


def current_revision(db, channel):
    row = _channel_row(db, channel)
    return int(row.revision) if row else 0


def bump_revision(db, channel, locked=False):
    if not locked:
        lock_channel(db, channel, create=True)
    row = db.scalar(select(ExemptionChannel).where(ExemptionChannel.channel == channel).with_for_update())
    if row is None:
        row = ExemptionChannel(channel=channel, revision=0, updated_at=time.time())
        db.add(row)
        db.flush()
    row.revision = int(row.revision or 0) + 1
    row.updated_at = time.time()
    db.flush()
    return int(row.revision)


def _validate(channel, start, end):
    if channel not in CHANNEL_OPTIONS:
        raise HTTPException(422, '未知播出链路')
    try:
        start_dt = parse_moment(start, '检修开始时刻')
        end_dt = parse_moment(end, '检修结束时刻')
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    if end_dt <= start_dt:
        raise HTTPException(422, '检修结束时刻必须晚于开始时刻')
    try:
        split_interval(start_dt, end_dt)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    return format_moment(start_dt), format_moment(end_dt)


def effective_rows(db, channel):
    return list(db.scalars(select(Maintenance).where(
        Maintenance.channel == channel,
        Maintenance.status == MaintenanceStatus.effective.value,
    ).order_by(Maintenance.start_at)))


def effective_snapshot(db, channel):
    return [{'id': row.id, 'channel': row.channel, 'start_at': row.start_at, 'end_at': row.end_at}
            for row in effective_rows(db, channel)]


def latest_effective_basis(db, channel):
    revision = current_revision(db, channel)
    items = effective_snapshot(db, channel)
    daily = minutes_by_day(items, channel)
    return {
        'channel': channel,
        'revision': revision,
        'exemptions': items,
        'daily': day_list(daily),
        'total_minutes': total_minutes(daily),
    }, daily


def create_draft(db, data, user):
    channel = str(data.channel).strip()
    start, end = _validate(channel, data.start_at, data.end_at)
    existing = db.scalar(select(Maintenance).where(
        Maintenance.channel == channel,
        Maintenance.status == MaintenanceStatus.draft.value,
    ))
    if existing:
        raise HTTPException(409, '该链路已有待生效的检修豁免草稿，请先编辑或撤销')
    item = Maintenance(
        name=data.name.strip(), channel=channel, start_at=start, end_at=end,
        note=(data.note or '').strip()[:500], status=MaintenanceStatus.draft.value,
        created_by=user.id, created_at=time.time(),
    )
    db.add(item)
    db.flush()
    return item


def update_draft(db, maintenance_id, data, user):
    item = db.get(Maintenance, maintenance_id)
    if not item:
        raise HTTPException(404, '检修豁免不存在')
    if item.status != MaintenanceStatus.draft.value:
        raise HTTPException(409, '只有草稿可以修改；已生效的豁免请撤销后重新登记')
    channel = str(data.channel).strip()
    start, end = _validate(channel, data.start_at, data.end_at)
    other = db.scalar(select(Maintenance).where(
        Maintenance.channel == channel,
        Maintenance.status == MaintenanceStatus.draft.value,
        Maintenance.id != item.id,
    ))
    if other:
        raise HTTPException(409, '该链路已有待生效的检修豁免草稿')
    item.name = data.name.strip()
    item.channel = channel
    item.start_at = start
    item.end_at = end
    item.note = (data.note or '').strip()[:500]
    db.flush()
    return item


def _next_version(db, maintenance_id, fallback=0):
    value = db.scalar(select(func.max(MaintenanceVersion.version)).where(
        MaintenanceVersion.maintenance_id == maintenance_id))
    return int(value or fallback) + 1


def _snapshot(db, item, user, action, revision):
    daily = split_interval(parse_moment(item.start_at), parse_moment(item.end_at))
    row = MaintenanceVersion(
        maintenance_id=item.id, version=_next_version(db, item.id, item.version or 0), action=action,
        channel=item.channel, start_at=item.start_at, end_at=item.end_at,
        daily=day_list(daily), total_minutes=total_minutes(daily),
        intervals=[[item.start_at, item.end_at]], revision=revision,
        created_by=user.id, created_at=time.time(),
    )
    db.add(row)
    db.flush()
    return row


def make_effective(db, maintenance_id, user):
    item = db.get(Maintenance, maintenance_id)
    if not item:
        raise HTTPException(404, '检修豁免不存在')
    if item.status == MaintenanceStatus.effective.value:
        return item, []
    if item.status != MaintenanceStatus.draft.value:
        raise HTTPException(409, '已撤销的检修豁免不能再次生效，请新建草稿')
    lock_channel(db, item.channel, create=True)
    revision = bump_revision(db, item.channel, locked=True)
    snapshot = _snapshot(db, item, user, 'effective', revision)
    item.status = MaintenanceStatus.effective.value
    item.revision = revision
    item.version = snapshot.version
    item.effective_at = time.time()
    db.flush()
    affected = invalidate_channel(db, item.channel, revision, f'检修豁免生效：{item.name}', user)
    audit.record(db, user.email, 'maintenance.effective', {
        'id': item.id, 'channel': item.channel, 'revision': revision,
        'version': snapshot.version, 'affected_jobs': [job.id for job in affected],
    })
    return item, affected


def revoke(db, maintenance_id, user):
    item = db.get(Maintenance, maintenance_id)
    if not item:
        raise HTTPException(404, '检修豁免不存在')
    if item.status == MaintenanceStatus.revoked.value:
        return item, []
    was_effective = item.status == MaintenanceStatus.effective.value
    lock_channel(db, item.channel, create=True)
    revision = bump_revision(db, item.channel, locked=True) if was_effective else current_revision(db, item.channel)
    snapshot = _snapshot(db, item, user, 'revoked', revision)
    item.status = MaintenanceStatus.revoked.value
    item.revoked_at = time.time()
    item.version = snapshot.version
    if was_effective:
        item.revision = revision
    db.flush()
    affected = []
    if was_effective:
        affected = invalidate_channel(db, item.channel, revision, f'检修豁免撤销：{item.name}', user)
    audit.record(db, user.email, 'maintenance.revoke', {
        'id': item.id, 'channel': item.channel, 'revision': revision,
        'was_effective': was_effective, 'affected_jobs': [job.id for job in affected],
    })
    return item, affected


def invalidate_channel(db, channel, revision, reason, user=None):
    """Move associated *unapproved* analyses to pending recalculation.

    Approved results and their reports keep the basis frozen at approval. Unapproved
    analyses are preserved (original result retained) but cannot be approved until a
    recalculation completes against the new revision. ``recalc_required`` is monotonic:
    an in-flight computation started on an older revision cannot clear it.
    """
    affected = []
    jobs = list(db.scalars(select(Job).where(Job.status.in_(('completed', 'pending_recalc', 'queued', 'running')))))
    for job in jobs:
        if str((job.params or {}).get('channel')) != channel:
            continue
        if job.approved:
            continue
        # Only analyses actually computed under an older revision need recalculation.
        # Unexecuted/never-computed jobs pick the current revision when claimed.
        if job.basis_revision is None and job.status == 'queued' and job.attempt_token is None:
            continue
        if job.basis_revision is not None and job.basis_revision >= revision:
            continue
        if job.status == 'completed':
            if job.result:
                job.held_result = job.result
            job.status = 'pending_recalc'
        elif job.status == 'queued':
            # A queued attempt has not pinned a basis yet; park it so it cannot be
            # claimed under the stale request and keep the original result intact.
            if job.attempt_token is None:
                job.status = 'pending_recalc'
        # running attempts keep their status; the finaliser parks stale attempts.
        job.recalc_required = True
        job.recalc_revision = revision
        job.recalc_reason = reason[:500]
        affected.append(job)
        audit.record(db, (user.email if user else 'system'), 'job.recalculation_required', {
            'id': job.id, 'channel': channel, 'revision': revision, 'reason': reason,
        })
    db.flush()
    return affected


def list_rows(db, channel=None):
    query = select(Maintenance).order_by(Maintenance.id.desc())
    if channel:
        query = query.where(Maintenance.channel == channel)
    return list(db.scalars(query))


def history(db, maintenance_id):
    rows = db.scalars(select(MaintenanceVersion).where(
        MaintenanceVersion.maintenance_id == maintenance_id).order_by(MaintenanceVersion.version))
    return [{
        'version': row.version, 'action': row.action, 'channel': row.channel,
        'start_at': row.start_at, 'end_at': row.end_at, 'daily': row.daily,
        'total_minutes': row.total_minutes, 'revision': row.revision, 'at': row.created_at,
    } for row in rows]


def impact(db, item, dataset_id=None):
    """Before/after deduction per day plus affected analyses and datasets."""
    from src.models import Dataset
    daily = split_interval(parse_moment(item.start_at), parse_moment(item.end_at))
    datasets = [db.get(Dataset, dataset_id)] if dataset_id else list(db.scalars(select(Dataset).order_by(Dataset.id.desc())))
    datasets = [d for d in datasets if d]
    days = []
    warnings = []
    for day, minutes in sorted(daily.items()):
        before = None
        for dataset in datasets:
            matches = [row for row in dataset.records
                       if str(row.get('channel')) == item.channel and str(row.get('day')) == day]
            if matches:
                before = round(sum(float(row.get('interruption_min', 0)) for row in matches), 4)
                break
        after = None if before is None else round(before - minutes, 4)
        if before is not None and minutes > before + 1e-9:
            warnings.append(f'{day} 检修豁免 {minutes:g} 分钟超过原停播 {before:g} 分钟，重算将拒绝扣除')
        days.append({'day': day, 'exempt_minutes': round(minutes, 4),
                     'original_interruption': before, 'net_interruption': after})
    affected = [job for job in db.scalars(select(Job).where(
                    Job.status.in_(('completed', 'pending_recalc', 'queued', 'running'))))
                if str((job.params or {}).get('channel')) == item.channel
                and not job.approved
                and (job.basis_revision is None or job.basis_revision < current_revision(db, item.channel))]
    approved = [job for job in db.scalars(select(Job).where(Job.status == 'completed'))
                if str((job.params or {}).get('channel')) == item.channel and job.approved]
    return {
        'id': item.id, 'name': item.name, 'channel': item.channel, 'status': item.status,
        'start_at': item.start_at, 'end_at': item.end_at,
        'total_minutes': total_minutes(daily), 'days': days,
        'affected_jobs': [{'id': job.id, 'name': job.name, 'status': job.status, 'approved': job.approved} for job in affected],
        'approved_jobs': [{'id': job.id, 'name': job.name, 'basis_revision': job.basis_revision} for job in approved],
        'warnings': warnings,
    }
