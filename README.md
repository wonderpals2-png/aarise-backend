# Aarise backend

FastAPI backend for the Aarise safety-watch app: accounts, emergency
contacts, SOS alerts, and live location, for both the phone app (WebView)
and the ESP32/SIM7000E watch firmware.

## Run it

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

SQLite database `aarise.db` is created automatically on first run in the
project folder. Interactive API docs: http://localhost:8000/docs

## Environment variables

| Variable                | Default                          | Purpose                                  |
|--------------------------|-----------------------------------|-------------------------------------------|
| `AARISE_SECRET_KEY`      | dev key (INSECURE)                | JWT signing key — set a real random value in production |
| `AARISE_DEVICE_KEY`      | dev key (INSECURE)                | Shared secret the watch firmware sends on every request |
| `AARISE_DATABASE_URL`    | `sqlite:///./aarise.db`           | Swap for Postgres etc. in production      |

Set both keys before deploying anywhere reachable from the internet:

```bash
export AARISE_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
export AARISE_DEVICE_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
```

## Endpoints

Auth (phone number + password):
- `POST /auth/register` — {name, phone, password} → JWT
- `POST /auth/login` — OAuth2 form (`username`=phone, `password`) → JWT
- `GET  /auth/me` — current user
- `PATCH /auth/me` — {name} update display name
- `POST /auth/device` — {device_id} pair this account to a physical watch

Contacts (JWT required):
- `GET/POST /contacts`
- `DELETE /contacts/{id}`

Alerts:
- `GET /alerts` — history for the signed-in user
- `POST /alerts/sos` — {type, latitude, longitude} — phone app trigger (JWT)
- `POST /alerts/device-sos?device_id=...` — watch firmware trigger (`X-Device-Key` header instead of JWT)
- `PATCH /alerts/{id}/resolve`

Location:
- `GET /location/latest`, `GET /location/history`
- `POST /location/refresh` — phone GPS fallback (JWT)
- `POST /location/device-ping?device_id=...` — watch firmware GPS ping (`X-Device-Key` header)

## Wiring in real SMS/push notifications

`app/notify.py` currently just logs what it would send. Replace the body of
`notify_contacts()` with a real Twilio/MSG91/FCM call — every caller already
just reads the returned "contacts notified" count, so nothing else changes.

## Watch firmware integration (ESP32 + SIM7000E)

The watch never logs in — it authenticates with the fixed `X-Device-Key`
header and identifies itself with the `device_id` a human paired via the
app's setup screen (`POST /auth/device`). On the SOS button interrupt and
on each periodic GPS fix, have the firmware call:

```
POST /alerts/device-sos?device_id=AARISE-ESP32-0001
X-Device-Key: <AARISE_DEVICE_KEY>
{"type": "SOS", "latitude": 17.385, "longitude": 78.4867}

POST /location/device-ping?device_id=AARISE-ESP32-0001
X-Device-Key: <AARISE_DEVICE_KEY>
{"latitude": 17.385, "longitude": 78.4867, "battery_pct": 81}
```
