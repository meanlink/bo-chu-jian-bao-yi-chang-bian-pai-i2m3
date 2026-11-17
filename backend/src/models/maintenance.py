from sqlalchemy import String, JSON, Double, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base


class Maintenance(Base):
    """Planned maintenance exemption entered per broadcast channel."""
    __tablename__ = 'maintenances'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    channel: Mapped[str] = mapped_column(String(80))
    start_at: Mapped[str] = mapped_column(String(32))
    end_at: Mapped[str] = mapped_column(String(32))
    note: Mapped[str] = mapped_column(String(500), default='')
    status: Mapped[str] = mapped_column(String(20), default='draft')
    revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Double)
    effective_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    revoked_at: Mapped[float | None] = mapped_column(Double, nullable=True)


class MaintenanceVersion(Base):
    """Immutable frozen snapshot taken when a draft becomes effective (or is revoked)."""
    __tablename__ = 'maintenance_versions'
    __table_args__ = (UniqueConstraint('maintenance_id', 'version', name='uq_maintenance_version'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    maintenance_id: Mapped[int] = mapped_column(ForeignKey('maintenances.id'))
    version: Mapped[int]
    action: Mapped[str] = mapped_column(String(20))
    channel: Mapped[str] = mapped_column(String(80))
    start_at: Mapped[str] = mapped_column(String(32))
    end_at: Mapped[str] = mapped_column(String(32))
    daily: Mapped[list] = mapped_column(JSON, default=list)
    total_minutes: Mapped[float] = mapped_column(Double, default=0.0)
    intervals: Mapped[list] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Double)


class ExemptionChannel(Base):
    """Per-channel monotonic revision counter; bumped on effective and revoke."""
    __tablename__ = 'exemption_channels'
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(80), unique=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[float] = mapped_column(Double)
