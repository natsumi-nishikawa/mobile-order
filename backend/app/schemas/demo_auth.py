from pydantic import BaseModel, Field


class DemoLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class DemoSessionResponse(BaseModel):
    authenticated: bool
    expires_at: int
    csrf_token: str


class DemoLogoutResponse(BaseModel):
    authenticated: bool = False
