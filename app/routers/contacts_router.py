from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..database import get_db

router = APIRouter(prefix="/contacts", tags=["contacts"])


def _to_out(c: models.Contact) -> schemas.ContactOut:
    return schemas.ContactOut(id=c.id, name=c.name, phone=c.phone, relationship=c.relationship_label)


@router.get("", response_model=List[schemas.ContactOut])
def list_contacts(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    contacts = (
        db.query(models.Contact)
        .filter(models.Contact.user_id == current_user.id)
        .order_by(models.Contact.name)
        .all()
    )
    return [_to_out(c) for c in contacts]


@router.post("", response_model=schemas.ContactOut, status_code=201)
def add_contact(
    payload: schemas.ContactIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    contact = models.Contact(
        user_id=current_user.id,
        name=payload.name,
        phone=payload.phone,
        relationship_label=payload.relationship,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return _to_out(contact)


@router.delete("/{contact_id}", status_code=204)
def delete_contact(
    contact_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    contact = (
        db.query(models.Contact)
        .filter(models.Contact.id == contact_id, models.Contact.user_id == current_user.id)
        .first()
    )
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.delete(contact)
    db.commit()
    return None
