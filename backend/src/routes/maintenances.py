from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.config.database import get_db
from src.models import Maintenance, Dataset
from src.schemas.maintenance import MaintenanceInput
from src.middlewares.auth import current_user, can_write, admin_only
from src.services import maintenance
from src.services.audit import record
from src.utils.serialization import maintenance_dict
from src.constants.enums import MaintenanceStatus

router = APIRouter(prefix='/maintenances')


def _load(db, maintenance_id):
    item = db.get(Maintenance, maintenance_id)
    if not item:
        raise HTTPException(404, '检修豁免不存在')
    return item


@router.get('')
def listing(channel: str | None = None, status: str | None = None, db=Depends(get_db), u=Depends(current_user)):
    rows = maintenance.list_rows(db, channel)
    if status:
        rows = [row for row in rows if row.status == status]
    return [maintenance_dict(row) for row in rows]


@router.get('/status')
def channel_status(db=Depends(get_db), u=Depends(current_user)):
    return {channel: maintenance.current_revision(db, channel) for channel in maintenance.CHANNEL_OPTIONS}


@router.get('/{id}')
def detail(id: int, db=Depends(get_db), u=Depends(current_user)):
    item = _load(db, id)
    return {**maintenance_dict(item), 'history': maintenance.history(db, id),
            'impact': maintenance.impact(db, item)}


@router.get('/{id}/impact')
def impact(id: int, dataset_id: int | None = None, db=Depends(get_db), u=Depends(current_user)):
    item = _load(db, id)
    if dataset_id is not None and not db.get(Dataset, dataset_id):
        raise HTTPException(404, '数据批次不存在')
    return maintenance.impact(db, item, dataset_id)


@router.post('', status_code=201)
def create(data: MaintenanceInput, db=Depends(get_db), u=Depends(can_write)):
    item = maintenance.create_draft(db, data, u)
    record(db, u.email, 'maintenance.draft', {'id': item.id, 'channel': item.channel,
                                              'start_at': item.start_at, 'end_at': item.end_at})
    db.commit()
    return maintenance_dict(item)


@router.put('/{id}')
def update(id: int, data: MaintenanceInput, db=Depends(get_db), u=Depends(can_write)):
    item = maintenance.update_draft(db, id, data, u)
    record(db, u.email, 'maintenance.update', {'id': item.id, 'channel': item.channel,
                                               'start_at': item.start_at, 'end_at': item.end_at})
    db.commit()
    return maintenance_dict(item)


@router.post('/{id}/effective')
def effective(id: int, db=Depends(get_db), u=Depends(admin_only)):
    item, affected = maintenance.make_effective(db, id, u)
    db.commit()
    return {**maintenance_dict(item), 'affected_jobs': [{'id': job.id, 'name': job.name} for job in affected]}


@router.post('/{id}/revoke')
def revoke(id: int, db=Depends(get_db), u=Depends(admin_only)):
    item, affected = maintenance.revoke(db, id, u)
    db.commit()
    return {**maintenance_dict(item), 'affected_jobs': [{'id': job.id, 'name': job.name} for job in affected]}


@router.get('/{id}/history')
def versions(id: int, db=Depends(get_db), u=Depends(current_user)):
    _load(db, id)
    return maintenance.history(db, id)
