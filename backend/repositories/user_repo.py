from sqlalchemy.orm import Session
from typing import Optional
from database.models import User, UserAuthSession
import hashlib
import secrets
import datetime


def create_user(
    db: Session,
    username: str,
    email: str = None,
    password: str = None
) -> User:
    """Create a new user"""
    user = User(
        username=username,
        email=email,
        password_hash=_hash_password(password) if password else None,
        is_active="true"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_or_create_user(
    db: Session, 
    username: str = "default",
    email: str = None,
    password: str = None
) -> User:
    """Get or create user for default mode
    
    Note: For default/simulation mode, creates user without authentication.
    """
    user = db.query(User).filter(User.username == username).first()
    if user:
        return user
    
    # Create default user without password requirement
    return create_user(db, username, email, password)


def get_user(db: Session, user_id: int) -> Optional[User]:
    """Get user by ID"""
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """Get user by username"""
    return db.query(User).filter(User.username == username).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Get user by email"""
    return db.query(User).filter(User.email == email).first()


def update_user(
    db: Session,
    user_id: int,
    username: str = None,
    email: str = None
) -> Optional[User]:
    """Update user information"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    
    if username is not None:
        user.username = username
    if email is not None:
        user.email = email
    
    db.commit()
    db.refresh(user)
    return user


def _hash_password(password: str) -> str:
    """Hash password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()


def set_user_password(db: Session, user_id: int, password: str) -> Optional[User]:
    """Set or update user trading password"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    
    user.password = _hash_password(password)
    db.commit()
    db.refresh(user)
    return user


def verify_user_password(db: Session, user_id: int, password: str) -> bool:
    """Verify user trading password"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.password:
        return False
    
    return user.password == _hash_password(password)


def user_has_password(db: Session, user_id: int) -> bool:
    """Check if user has set a trading password"""
    user = db.query(User).filter(User.id == user_id).first()
    return user is not None and user.password is not None and user.password.strip() != ""


def create_auth_session(db: Session, user_id: int) -> Optional[UserAuthSession]:
    """Create a new authentication session for user (180 days expiry)"""
    # Clean up expired sessions for this user
    cleanup_expired_sessions(db, user_id)
    
    # Generate session token
    session_token = secrets.token_urlsafe(32)
    
    # Set expiry to 180 days from now
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=180)
    
    # Create session
    session = UserAuthSession(
        user_id=user_id,
        session_token=session_token,
        expires_at=expires_at
    )
    
    db.add(session)
    db.commit()
    db.refresh(session)
    
    return session


def verify_auth_session(db: Session, session_token: str) -> Optional[int]:
    """Verify session token and return user_id if valid"""
    session = db.query(UserAuthSession).filter(
        UserAuthSession.session_token == session_token,
        UserAuthSession.expires_at > datetime.datetime.utcnow()
    ).first()
    
    return session.user_id if session else None


def cleanup_expired_sessions(db: Session, user_id: int = None) -> int:
    """Clean up expired sessions. If user_id provided, clean only for that user"""
    query = db.query(UserAuthSession).filter(
        UserAuthSession.expires_at <= datetime.datetime.utcnow()
    )
    
    if user_id:
        query = query.filter(UserAuthSession.user_id == user_id)
    
    deleted_count = query.count()
    query.delete()
    db.commit()
    
    return deleted_count


def revoke_auth_session(db: Session, session_token: str) -> bool:
    """Revoke a specific session token"""
    session = db.query(UserAuthSession).filter(
        UserAuthSession.session_token == session_token
    ).first()
    
    if session:
        db.delete(session)
        db.commit()
        return True
    
    return False


def revoke_all_user_sessions(db: Session, user_id: int) -> int:
    """Revoke all sessions for a user"""
    deleted_count = db.query(UserAuthSession).filter(
        UserAuthSession.user_id == user_id
    ).count()
    
    db.query(UserAuthSession).filter(
        UserAuthSession.user_id == user_id
    ).delete()
    
    db.commit()
    return deleted_count
