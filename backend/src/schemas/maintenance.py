from pydantic import BaseModel, Field


class MaintenanceInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    channel: str = Field(min_length=2, max_length=80)
    start_at: str = Field(min_length=8, max_length=32)
    end_at: str = Field(min_length=8, max_length=32)
    note: str = Field(default='', max_length=500)
