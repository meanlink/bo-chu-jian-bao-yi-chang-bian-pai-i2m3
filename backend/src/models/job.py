from sqlalchemy import String, JSON, Double, ForeignKey, Boolean, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base


class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default='queued')
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(String(1000), default='')
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Double)
    finished_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    # Recalculation state and frozen calculation basis.
    recalc_required: Mapped[bool] = mapped_column(Boolean, default=False)
    recalc_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recalc_reason: Mapped[str] = mapped_column(String(500), default='')
    held_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    basis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    basis_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempt_started: Mapped[float | None] = mapped_column(Double, nullable=True)
    attempt_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_at: Mapped[float | None] = mapped_column(Double, nullable=True)
