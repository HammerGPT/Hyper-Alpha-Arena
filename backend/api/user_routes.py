"""
User authentication API routes
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List
import logging

from database.connection import SessionLocal
from database.models import User, UserExchangeConfig
from repositories.user_repo import (
    create_user, get_user, get_user_by_username,
    update_user, create_auth_session, verify_auth_session
)
from schemas.user import (
    UserCreate, UserUpdate, UserOut, UserLogin, UserAuthResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/register", response_model=UserOut)
async def register_user(user_data: UserCreate, db: Session = Depends(get_db)):
    try:
        # Check if username exists
        existing = get_user_by_username(db, user_data.username)
        if existing:
            raise HTTPException(status_code=400, detail="Username already exists")
        
        # Create new user
        user = create_user(
            db=db,
            username=user_data.username,
            email=user_data.email,
            password=user_data.password
        )
        
        return UserOut(
            id=user.id,
            username=user.username,
            email=user.email,
            is_active=user.is_active == "true"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User registration failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"User registration failed: {str(e)}")


@router.post("/login", response_model=UserAuthResponse)
async def login_user(login_data: UserLogin, db: Session = Depends(get_db)):
    try:
        # For now, just verify username exists and create session
        # Password verification can be implemented later
        user = get_user_by_username(db, login_data.username)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Create auth session
        session = create_auth_session(db, user.id)
        if not session:
            raise HTTPException(status_code=500, detail="Failed to create session")
        
        return UserAuthResponse(
            user=UserOut(
                id=user.id,
                username=user.username,
                email=user.email,
                is_active=user.is_active == "true"
            ),
            session_token=session.session_token,
            expires_at=session.expires_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User login failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"User login failed: {str(e)}")


@router.get("/profile", response_model=UserOut)
async def get_user_profile(session_token: str, db: Session = Depends(get_db)):
    try:
        user_id = verify_auth_session(db, session_token)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        
        user = get_user(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return UserOut(
            id=user.id,
            username=user.username,
            email=user.email,
            is_active=user.is_active == "true"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get user profile: {str(e)}")


@router.put("/profile", response_model=UserOut)
async def update_user_profile(
    session_token: str, 
    user_data: UserUpdate, 
    db: Session = Depends(get_db)
):
    try:
        user_id = verify_auth_session(db, session_token)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        
        # Check if new username is taken (if provided)
        if user_data.username:
            existing = get_user_by_username(db, user_data.username)
            if existing and existing.id != user_id:
                raise HTTPException(status_code=400, detail="Username already exists")
        
        user = update_user(
            db=db,
            user_id=user_id,
            username=user_data.username,
            email=user_data.email
        )
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return UserOut(
            id=user.id,
            username=user.username,
            email=user.email,
            is_active=user.is_active == "true"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update user profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update user profile: {str(e)}")


@router.get("/", response_model=List[UserOut])
async def list_users(db: Session = Depends(get_db)):
    try:
        users = db.query(User).filter(User.is_active == "true").order_by(User.username).all()
        return [
            UserOut(
                id=user.id,
                username=user.username,
                email=user.email,
                is_active=user.is_active == "true"
            )
            for user in users
        ]
        
    except Exception as e:
        logger.error(f"Failed to list users: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list users: {str(e)}")


@router.get("/exchange-config")
async def get_exchange_config(db: Session = Depends(get_db)):
    """Get current exchange configuration for default user"""
    try:
        # Use default user_id=1 for now
        config = db.query(UserExchangeConfig).filter(UserExchangeConfig.user_id == 1).first()
        if not config:
            # Return default if no config exists
            return {"selected_exchange": "hyperliquid"}
        return {"selected_exchange": config.selected_exchange}
    except Exception as e:
        logger.error(f"Failed to get exchange config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get exchange config: {str(e)}")


@router.post("/exchange-config")
async def set_exchange_config(exchange_data: dict, db: Session = Depends(get_db)):
    """Set exchange configuration for default user"""
    try:
        selected_exchange = exchange_data.get("selected_exchange")
        if not selected_exchange or selected_exchange not in ["hyperliquid", "binance", "aster"]:
            raise HTTPException(status_code=400, detail="Invalid exchange selection")

        # Use default user_id=1 for now
        config = db.query(UserExchangeConfig).filter(UserExchangeConfig.user_id == 1).first()
        if config:
            config.selected_exchange = selected_exchange
        else:
            config = UserExchangeConfig(user_id=1, selected_exchange=selected_exchange)
            db.add(config)

        db.commit()
        return {"selected_exchange": selected_exchange, "status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to set exchange config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to set exchange config: {str(e)}")