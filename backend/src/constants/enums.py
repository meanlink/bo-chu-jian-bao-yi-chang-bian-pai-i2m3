from enum import Enum
class Role(str, Enum):
    admin = 'admin'
    analyst = 'analyst'
    viewer = 'viewer'
class JobStatus(str, Enum):
    queued = 'queued'
    running = 'running'
    completed = 'completed'
    failed = 'failed'
    pending_recalc = 'pending_recalc'
class MaintenanceStatus(str, Enum):
    draft = 'draft'
    effective = 'effective'
    revoked = 'revoked'
