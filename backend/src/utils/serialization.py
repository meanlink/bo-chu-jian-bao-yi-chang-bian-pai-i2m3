import hashlib, json
def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
def dataset_dict(d):
    return {'id':d.id, 'name':d.name, 'source':d.source, 'rows':len(d.records), 'checksum':d.checksum, 'created_at':d.created_at}
def job_dict(j, include_held=False):
    data={k:getattr(j,k) for k in ['id','name','dataset_id','params','status','result','error','approved','created_at','finished_at',
                                   'recalc_required','recalc_revision','recalc_reason','result_revision',
                                   'basis','basis_revision','approved_at','approved_by','retry_count','last_error_at']}
    data['has_held_result']=bool(getattr(j,'held_result',None))
    if include_held:
        data['held_result']=getattr(j,'held_result',None)
    return data
def report_dict(r):
    return {k:getattr(r,k) for k in ['id','name','job_id','destination','interval_seconds','next_run','enabled','basis','basis_revision']}
def delivery_dict(d):
    return {k:getattr(d,k) for k in ['id','report_id','created_at','checksum','filename','destination','basis','basis_revision']}
def maintenance_dict(m):
    return {k:getattr(m,k) for k in ['id','name','channel','start_at','end_at','note','status','revision','version',
                                     'created_by','created_at','effective_at','revoked_at']}
