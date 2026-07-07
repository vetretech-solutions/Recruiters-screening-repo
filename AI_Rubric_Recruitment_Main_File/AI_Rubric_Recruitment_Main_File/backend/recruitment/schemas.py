from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str = Field(min_length=2)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str = "admin"
    status: str = "active"
    tenant_id: str | None = None
    tenant_name: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class PaginatedUsers(BaseModel):
    items: list[UserOut]
    total: int
    page: int
    page_size: int


class CreateUserRequest(BaseModel):
    full_name: str = Field(min_length=2)
    email: EmailStr
    role: str
    password: str = Field(min_length=8)
    status: str = "active"


class UpdateUserRequest(BaseModel):
    full_name: str | None = None
    status: str | None = None


class SetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class ContactRequest(BaseModel):
    full_name: str = Field(min_length=2)
    email: EmailStr
    company: str | None = None
    message: str = Field(min_length=10)


class ContactSubmissionOut(BaseModel):
    id: int
    full_name: str
    email: str
    company: str | None
    message: str
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedContactSubmissions(BaseModel):
    items: list[ContactSubmissionOut]
    total: int
    page: int
    page_size: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class GenerateJDRequest(BaseModel):
    natural_language: str = Field(min_length=10)


class UpdateJDRequest(BaseModel):
    jd: dict[str, Any]


class JobPostingOut(BaseModel):
    id: int
    title: str
    jd: dict[str, Any]
    natural_language_input: str | None
    status: str
    created_at: datetime
    updated_at: datetime | None

    class Config:
        from_attributes = True


class PlatformInfo(BaseModel):
    id: str
    name: str
    logo: str
    description: str
    supports_oauth: bool = False


class PlatformConnectionOut(BaseModel):
    platform: str
    account_email: str
    account_name: str | None = None
    account_url: str | None = None
    connected_at: datetime
    is_oauth: bool = False
    can_post: bool = True

    class Config:
        from_attributes = True


class ConnectPlatformRequest(BaseModel):
    email: str = ""
    password: str = ""


class PostToPlatformRequest(BaseModel):
    platform: str
    force: bool = False


class PlatformPostOut(BaseModel):
    id: int
    platform: str
    external_url: str | None
    external_post_id: str | None = None
    account_url: str | None = None
    account_email: str | None = None
    account_name: str | None = None
    apply_url: str
    status: str
    posted_at: datetime
    applicant_count: int = 0
    message: str | None = None

    class Config:
        from_attributes = True


class ApplicantOut(BaseModel):
    id: int
    full_name: str
    email: str
    phone: str | None
    platform: str
    applied_at: datetime
    has_resume: bool = False
    linkedin_url: str | None = None
    current_title: str | None = None
    current_company: str | None = None
    years_experience: str | None = None
    location: str | None = None
    resume_filename: str | None = None

    class Config:
        from_attributes = True


class ApplicantDetailOut(ApplicantOut):
    resume_text: str | None = None
    cover_letter: str | None = None

    class Config:
        from_attributes = True


class ApplyRequest(BaseModel):
    full_name: str = Field(min_length=2)
    email: EmailStr
    phone: str | None = None
    linkedin_url: str | None = None
    current_title: str | None = None
    current_company: str | None = None
    years_experience: str | None = None
    location: str | None = None
    cover_letter: str | None = None
    resume_text: str | None = None
