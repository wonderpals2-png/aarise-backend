"""
Emergency-contact notification service.

This is a stub: it logs what WOULD be sent so the rest of the app (alert
history, contacts-notified count) works end-to-end today. Wire in a real
provider (Twilio, MSG91, Firebase Cloud Messaging, etc.) by replacing the
body of `notify_contacts` — nothing else in the app needs to change since
every caller already just awaits this function and reads the return count.
"""
import logging
from typing import List

from . import models

logger = logging.getLogger("aarise.notify")


def notify_contacts(user: models.User, contacts: List[models.Contact], alert: models.Alert) -> int:
    if not contacts:
        logger.warning("SOS triggered for %s but they have no emergency contacts saved", user.phone)
        return 0

    maps_link = f"https://maps.google.com/?q={alert.latitude},{alert.longitude}" if alert.latitude else "location unavailable"
    message = (
        f"AARISE ALERT: {user.name} triggered {alert.type}. "
        f"Live location: {maps_link}"
    )

    for contact in contacts:
        # TODO: replace with a real SMS/push call, e.g.:
        # twilio_client.messages.create(to=contact.phone, from_=TWILIO_NUMBER, body=message)
        logger.info("[SOS NOTIFY -> %s (%s)] %s", contact.name, contact.phone, message)

    return len(contacts)
