from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.schemas import LoginIn, LoginOut, UserOut, UserProfileUpdateIn
from app.services.auth import create_token, current_user, hash_password, verify_password


router = APIRouter(prefix="/auth", tags=["auth"])
ACTIVE_ROLES = {"sales", "admin"}


@router.post("/login", response_model=LoginOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or user.role not in ACTIVE_ROLES or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return LoginOut(token=create_token(user), user=user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(payload: UserProfileUpdateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if payload.name is not None:
        next_name = payload.name.strip()
        if not next_name:
            raise HTTPException(status_code=400, detail="姓名不能为空")
        user.name = next_name

    if payload.password:
        next_password = payload.password.strip()
        if len(next_password) < 6:
            raise HTTPException(status_code=400, detail="密码至少 6 位")
        user.password_hash = hash_password(next_password)

    db.add(user)
    db.commit()
    db.refresh(user)
    return user
