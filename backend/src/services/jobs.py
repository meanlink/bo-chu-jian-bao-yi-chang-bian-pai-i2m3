import time
from fastapi import HTTPException
from redis import Redis
from src.config.settings import REDIS_URL
from src.models import Dataset, Job
from src.services import maintenance
from src.services.business import metadata


def create(db, data, user):
    if not db.get(Dataset, data.dataset_id):
        raise HTTPException(404, '数据批次不存在')
    allowed = {p['key']: p for p in metadata().get('parameters', [])}
    if set(data.params) - set(allowed):
        raise HTTPException(422, '包含未知分析参数')
    params = {k: p['default'] for k, p in allowed.items()}
    params.update(data.params)
    for key, p in allowed.items():
        v = params[key]
        if p['type'] == 'number':
            try:
                v = float(v)
                if not (p.get('min', -1e9) <= v <= p.get('max', 1e9)):
                    raise ValueError()
                params[key] = v
            except (ValueError, TypeError):
                raise HTTPException(422, f'{p["label"]} 超出范围或非数值')
        elif str(v) not in [str(o['value']) for o in p.get('options', [])]:
            raise HTTPException(422, f'{p["label"]} 不是有效选项')
    j = Job(name=data.name, dataset_id=data.dataset_id, params=params, created_by=user.id,
            created_at=time.time(), status='queued')
    db.add(j)
    db.flush()
    return j


def enqueue(job_id):
    try:
        r = Redis.from_url(REDIS_URL)
        r.rpush('analysis:queue', job_id)
        r.close()
    except Exception:
        pass  # SQL queued status is the durable fallback


def request_recalc(db, job_id, user):
    """Re-run the same analysis in place; retries never create a second result row."""
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, '分析任务不存在')
    if job.status == 'running':
        raise HTTPException(409, '该分析正在计算，请等待本次计算结束后重试')
    if not (job.recalc_required or job.status in ('pending_recalc', 'failed')):
        if job.approved:
            raise HTTPException(409, '该结果已获批准；如需重算请先由负责人撤销批准')
        raise HTTPException(409, '该分析没有待重算的变更')
    job.status = 'queued'
    job.error = ''
    job.finished_at = None
    db.flush()
    return job


def approve(db, job_id, user):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, '分析任务不存在')
    if job.status != 'completed':
        raise HTTPException(409, '仅已完成结果可以批准；待重算的分析须先完成重算')
    if job.recalc_required:
        raise HTTPException(409, '该结果基于旧版检修豁免口径，必须先完成重算才能批准')
    # Serialise against an exemption becoming effective in the same channel. A basis
    # computed before the new revision may not be approved (stale version).
    maintenance.lock_channel(db, str((job.params or {}).get('channel')), create=True)
    db.refresh(job)
    if job.status != 'completed':
        raise HTTPException(409, '仅已完成结果可以批准；待重算的分析须先完成重算')
    if job.recalc_required:
        raise HTTPException(409, '该结果基于旧版检修豁免口径，必须先完成重算才能批准')
    current = maintenance.current_revision(db, str((job.params or {}).get('channel')))
    if job.basis_revision is None or job.basis_revision != current:
        raise HTTPException(409, '检修豁免口径已更新，该结果属于旧版，需重算后才能批准')
    if job.approved:
        return job
    job.approved = True
    job.approved_at = time.time()
    job.approved_by = user.id
    db.flush()
    return job
