import time, json, logging, secrets
from pathlib import Path
from sqlalchemy import select
from redis import Redis
from src.config.database import Session
from src.config.settings import REDIS_URL
from src.models import Job, Dataset, Report
from src.services import maintenance
from src.services.business import analyze
from src.services.reports import deliver
from src.services.audit import record
logging.basicConfig(level=logging.INFO)


def _claim(db, job_id):
    """Atomically move a queued job to running and pin the basis revision being computed."""
    job = db.get(Job, job_id, with_for_update=True)
    if not job or job.status != 'queued':
        return None
    channel = str((job.params or {}).get('channel'))
    basis, _ = maintenance.latest_effective_basis(db, channel)
    job.status = 'running'
    job.attempt_token = secrets.token_hex(16)
    job.attempt_started = time.time()
    job.attempt_revision = basis['revision']
    job.basis = basis
    job.basis_revision = basis['revision']
    job.last_error_at = None
    # A recovered attempt continues the same row; retry_count is kept for auditing.
    job.retry_count = int(job.retry_count or 0)
    job.error = ''
    db.flush()
    return job


def execute(job_id):
    with Session() as db:
        claimed = _claim(db, job_id)
        if claimed is None:
            return
        job = claimed
        token = job.attempt_token
        revision = job.attempt_revision
        db.commit()
    # Compute outside the row lock so exemption changes are not blocked by long runs.
    try:
        with Session() as db:
            job = db.get(Job, job_id)
            dataset = db.get(Dataset, job.dataset_id)
            basis = job.basis or {}
            exemptions = basis.get('exemptions', [])
            result = analyze(dataset.records, job.params, exemptions)
            json.dumps(result, allow_nan=False)
        _finalise(job_id, token, revision, result=result)
    except Exception as error:
        logging.exception('Analysis failed')
        _finalise(job_id, token, revision, error=str(error)[:990])


def _finalise(job_id, token, revision, result=None, error=None):
    """Persist a finished attempt only if no newer basis or retry superseded it."""
    with Session() as db:
        job = db.get(Job, job_id)
        if not job:
            return
        channel = str((job.params or {}).get('channel'))
        # Both approval and exemption changes lock this row, so a late completion can
        # never overwrite a newer pending-recalculation flag.
        maintenance.lock_channel(db, channel, create=True)
        job = db.get(Job, job_id, with_for_update=True)
        if not job or job.attempt_token != token:
            return  # a newer attempt owns this job
        current = maintenance.current_revision(db, channel)
        if error is not None:
            job.status = 'failed'
            job.error = error
            job.finished_at = time.time()
            job.last_error_at = time.time()
            db.commit()
            return
        if revision is not None and current > revision:
            # Basis moved forward while we were computing: this result is stale.
            job.status = 'pending_recalc'
            job.recalc_required = True
            job.recalc_revision = current
            job.recalc_reason = job.recalc_reason or '检修豁免口径在计算期间更新，需按新版重算'
            job.attempt_token = None
            job.attempt_started = None
            db.commit()
            return
        job.result = result
        job.status = 'completed'
        job.finished_at = time.time()
        job.result_revision = revision if revision is not None else job.basis_revision
        job.recalc_required = False
        job.recalc_revision = None
        job.recalc_reason = ''
        job.held_result = None
        job.attempt_token = None
        job.attempt_started = None
        record(db, 'worker', 'job.completed', {'id': job_id, 'revision': revision})
        db.commit()


def tick():
    with Session() as db:
        queued = list(db.scalars(select(Job.id).where(Job.status == 'queued').limit(3)))
    for job_id in queued:
        execute(job_id)
    with Session() as db:
        for report in db.scalars(select(Report).where(Report.enabled == True, Report.next_run <= time.time())):
            delivery = deliver(db, report)
            if delivery:
                record(db, 'worker', 'report.delivered', {'id': report.id, 'delivery': delivery.id})
        db.commit()


def recover():
    """Requeue attempts interrupted by a worker crash; retries continue the same analysis row."""
    with Session() as db:
        for job in db.scalars(select(Job).where(Job.status == 'running')):
            job.status = 'queued'
            job.retry_count = int(job.retry_count or 0) + 1
            job.attempt_token = None
            job.attempt_started = None
            record(db, 'worker', 'job.recovered', {'id': job.id, 'attempt': job.retry_count})
        db.commit()


def main():
    r = Redis.from_url(REDIS_URL, socket_timeout=3)
    # This Compose stack has a single worker. A crash must not strand its jobs.
    recover()
    while True:
        Path('/tmp/heartbeat').touch()
        try:
            item = r.blpop('analysis:queue', timeout=1)
            if item:
                execute(int(item[1]))
            tick()
        except Exception:
            logging.exception('Worker retry')
            time.sleep(2)


if __name__ == '__main__':
    main()
