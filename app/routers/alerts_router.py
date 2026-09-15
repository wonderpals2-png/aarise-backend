import datetime
import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db
from ..notify import notify_contacts

router = APIRouter(prefix="/alerts", tags=["alerts"])

DEVICE_KEY = os.getenv("AARISE_DEVICE_KEY", "dev-device-key-change-me")


def _fire_alert(db: Session, user: models.User, payload: schemas.AlertIn) -> models.Alert:
    alert = models.Alert(
        user_id=user.id,
        type=payload.type or "SOS",
        latitude=payload.latitude,
        longitude=payload.longitude,
        status="Active",
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    contacts = db.query(models.Contact).filter(models.Contact.user_id == user.id).all()
    notified = notify_contacts(user, contacts, alert)

    alert.contacts_notified = notified
    db.commit()
    db.refresh(alert)
    return alert


@router.get("", response_model=List[schemas.AlertOut])
def list_alerts(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.Alert)
        .filter(models.Alert.user_id == current_user.id)
        .order_by(models.Alert.created_at.desc())
        .all()
    )


@router.post("/sos", response_model=schemas.AlertOut, status_code=201)
def trigger_sos(
    payload: schemas.AlertIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Called by the phone app's 'Hold for SOS' button."""
    return _fire_alert(db, current_user, payload)


@router.post("/device-sos", response_model=schemas.AlertOut, status_code=201)
def trigger_sos_from_device(
    device_id: str,
    payload: schemas.AlertIn,
    x_device_key: str = Header(...),
    db: Session = Depends(get_db),
):
    """Called directly by the watch firmware when the physical SOS button is pressed."""
    if x_device_key != DEVICE_KEY:
        raise HTTPException(status_code=401, detail="Invalid device key")

    user = db.query(models.User).filter(models.User.device_id == device_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="No account paired to this device id")

    return _fire_alert(db, user, payload)


@router.patch("/{alert_id}/resolve", response_model=schemas.AlertOut)
def resolve_alert(
    alert_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    alert = (
        db.query(models.Alert)
        .filter(models.Alert.id == alert_id, models.Alert.user_id == current_user.id)
        .first()
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status = "Resolved"
    alert.resolved_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(alert)
    return alert
