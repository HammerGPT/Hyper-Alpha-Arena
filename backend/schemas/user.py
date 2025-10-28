from pydantic import BaseModel
from typing import Optional


class UserCreate(BaseModel):
    """Create a new user for authentication"""
    username: str
    email: Optional[str] = None
    password: Optional[str] = None  # For future authentication if needed


class UserUpdate(BaseModel):
    """Update user information"""
    username: Optional[str] = None
    email: Optional[str] = None


class UserOut(BaseModel):
    """User output for authentication"""
    id: int
    username: str
    email: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    """User login credentials"""
    username: str
    password: str


class UserAuthResponse(BaseModel):
    """User authentication response"""
    user: UserOut
    session_token: str
    expires_at: str
