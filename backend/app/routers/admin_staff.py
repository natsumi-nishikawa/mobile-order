from fastapi import APIRouter, Depends, status

from app.schemas.admin_staff import StaffAccountCreate, StaffAccountResponse, StaffPasswordReset
from app.services.cognito_users import (
    create_staff_account,
    list_staff_accounts,
    reset_staff_password,
    set_staff_enabled,
)
from app.store_auth import require_admin


router = APIRouter(
    prefix="/api/admin/staff-users",
    tags=["Admin staff users"],
    dependencies=[Depends(require_admin)],
)


@router.get("", response_model=list[StaffAccountResponse])
def get_staff_users():
    return list_staff_accounts()


@router.post("", response_model=StaffAccountResponse, status_code=status.HTTP_201_CREATED)
def create_staff_user(data: StaffAccountCreate):
    return create_staff_account(str(data.email), data.temporary_password, data.display_name)


@router.post("/{username}/disable", status_code=status.HTTP_204_NO_CONTENT)
def disable_staff_user(username: str):
    set_staff_enabled(username, False)


@router.post("/{username}/enable", status_code=status.HTTP_204_NO_CONTENT)
def enable_staff_user(username: str):
    set_staff_enabled(username, True)


@router.post("/{username}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(username: str, data: StaffPasswordReset):
    reset_staff_password(username, data.temporary_password)
