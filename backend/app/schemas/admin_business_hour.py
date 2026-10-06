from datetime import time

from pydantic import BaseModel, Field, model_validator


class AdminBusinessHourWrite(BaseModel):
    day_of_week: int = Field(ge=0, le=6, strict=True)
    is_open: bool
    opening_time: time | None = None
    closing_time: time | None = None

    @model_validator(mode="after")
    def validate_times(self):
        if self.is_open and (self.opening_time is None or self.closing_time is None):
            raise ValueError("営業日には開店時間と閉店時間が必要です")
        if self.is_open and self.opening_time == self.closing_time:
            raise ValueError("開店時間と閉店時間は異なる時刻を指定してください")
        return self


class AdminBusinessHourResponse(AdminBusinessHourWrite):
    id: int
