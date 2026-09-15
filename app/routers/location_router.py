import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db

router = APIRouter(prefix="/location", tags=["location"])

# Shared secret the ESP32/SIM7000E watch firmware sends on every ping.
# Set AARISE_DEVICE_KEY in the environment before deploying; this default is for local dev only.
DEVICE_KEY = os.getenv("AARISE_DEVICE_KEY", "dev-device-key-change-me")


@router.get("/latest", response_model=schemas.LocationOut)
def latest_location(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    ping = (
        db.query(models.LocationPing)
        .filter(models.LocationPing.user_id == current_user.id)
        .order_by(models.LocationPing.created_at.desc())
        .first()
    )
    if not ping:
        raise HTTPException(status_code=404, detail="No location fix yet")
    return ping


@router.get("/history", response_model=List[schemas.LocationOut])
def location_history(
    limit: int = 50,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    pings = (
        db.query(models.LocationPing)
        .filter(models.LocationPing.user_id == current_user.id)
        .order_by(models.LocationPing.created_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return pings


@router.post("/refresh", response_model=schemas.LocationOut)
def refresh_from_app(
    payload: schemas.LocationIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Used by the phone app's own GPS as a fallback when the watch has no signal."""
    ping = models.LocationPing(
        user_id=current_user.id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy_m=payload.accuracy_m,
        battery_pct=payload.battery_pct,
        source="app",
    )
    db.add(ping)
    db.commit()
    db.refresh(ping)
    return ping


@router.post("/device-ping", response_model=schemas.LocationOut)
def device_ping(
    device_id: str,
    payload: schemas.LocationIn,
    x_device_key: str = Header(...),
    db: Session = Depends(get_db),
):
    """Called directly by the watch firmware over HTTPS via the SIM7000E LTE modem."""
    if x_device_key != DEVICE_KEY:
        raise HTTPException(status_code=401, detail="Invalid device key")

    user = db.query(models.User).filter(models.User.device_id == device_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="No account paired to this device id")

    ping = models.LocationPing(
        user_id=user.id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy_m=payload.accuracy_m,
        battery_pct=payload.battery_pct,
        source="watch",
    )
    db.add(ping)
    db.commit()
    db.refresh(ping)
    return ping
