from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.TokenOut, status_code=201)
def register(payload: schemas.RegisterIn, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.phone == payload.phone).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this phone number already exists")

    user = models.User(
        name=payload.name.strip() or "Aarise User",
        phone=payload.phone.strip(),
        password_hash=auth.hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = auth.create_access_token(user.id)
    return schemas.TokenOut(access_token=token, user_id=user.id, name=user.name)


@router.post("/login", response_model=schemas.TokenOut)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # form_data.username carries the phone number (OAuth2 password flow field name)
    user = db.query(models.User).filter(models.User.phone == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect phone number or password")

    token = auth.create_access_token(user.id)
    return schemas.TokenOut(access_token=token, user_id=user.id, name=user.name)


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@router.patch("/me", response_model=schemas.UserOut)
def update_name(
    payload: schemas.NameUpdateIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if not payload.name.strip():
        raise HTTPException(status_code=422, detail="Name must not be blank")
    current_user.name = payload.name.strip()
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/device", response_model=schemas.UserOut)
def pair_device(
    payload: schemas.DevicePairIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Pair the app account with a physical watch (ESP32 chip/device id)."""
    clash = (
        db.query(models.User)
        .filter(models.User.device_id == payload.device_id, models.User.id != current_user.id)
        .first()
    )
    if clash:
        raise HTTPException(status_code=409, detail="That device is already paired to another account")
    current_user.device_id = payload.device_id
    db.commit()
    db.refresh(current_user)
    return current_user
