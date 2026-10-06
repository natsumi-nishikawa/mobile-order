from pydantic import BaseModel, Field, field_validator


class StaffAccountResponse(BaseModel):
    username: str
    email: str
    display_name: str | None
    enabled: bool
    status: str


class StaffAccountCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str | None = Field(default=None, max_length=100)
    temporary_password: str = Field(min_length=8, max_length=256)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
            raise ValueError("有効なメールアドレスを入力してください")
        return cleaned


class StaffPasswordReset(BaseModel):
    temporary_password: str = Field(min_length=8, max_length=256)
