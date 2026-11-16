from pydantic import BaseModel, EmailStr, Field, ConfigDict
from app.models.entities import UserRole

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)

class CreateUserRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    role: UserRole = UserRole.SELLER
    territory: str | None = Field(default=None, max_length=160)
    temporary_password: str | None = Field(default=None, min_length=12, max_length=256)

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    territory: str | None
    active: bool
    must_change_password: bool
