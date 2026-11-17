"""Schema bootstrap plus additive migrations for already-provisioned databases."""
from sqlalchemy import inspect, text
from src.config.database import Base, engine
from src import models

# Columns added after the first release. ``create_all`` never alters existing tables,
# so these are applied explicitly; every entry is idempotent.
ADDITIVE_COLUMNS = {
    'jobs': {
        'recalc_required': 'BOOLEAN NOT NULL DEFAULT 0',
        'recalc_revision': 'INTEGER NULL',
        'recalc_reason': "VARCHAR(500) NOT NULL DEFAULT ''",
        'held_result': 'JSON NULL',
        'result_revision': 'INTEGER NULL',
        'basis': 'JSON NULL',
        'basis_revision': 'INTEGER NULL',
        'approved_at': 'DOUBLE NULL',
        'approved_by': 'INTEGER NULL',
        'attempt_token': 'VARCHAR(64) NULL',
        'attempt_started': 'DOUBLE NULL',
        'attempt_revision': 'INTEGER NULL',
        'retry_count': 'INTEGER NOT NULL DEFAULT 0',
        'last_error_at': 'DOUBLE NULL',
    },
    'reports': {
        'basis': 'JSON NULL',
        'basis_revision': 'INTEGER NULL',
    },
    'deliveries': {
        'basis': 'JSON NULL',
        'basis_revision': 'INTEGER NULL',
    },
}


def _existing_columns(connection, table):
    inspector = inspect(connection)
    return {column['name'] for column in inspector.get_columns(table)}


def migrate():
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        for table, columns in ADDITIVE_COLUMNS.items():
            present = _existing_columns(connection, table)
            for name, ddl in columns.items():
                if name in present:
                    continue
                connection.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
        # Rows produced before versioned exemptions existed were computed with no
        # exemption in force, i.e. revision 0. Treat them as such so they stay usable.
        connection.execute(text(
            "UPDATE jobs SET basis_revision = 0, result_revision = 0 "
            "WHERE basis_revision IS NULL AND status = 'completed'"))
        connection.execute(text(
            'UPDATE reports SET basis_revision = 0 WHERE basis_revision IS NULL'))
        connection.execute(text(
            'UPDATE deliveries SET basis_revision = 0 WHERE basis_revision IS NULL'))


if __name__ == '__main__':
    migrate()
