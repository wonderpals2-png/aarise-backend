from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .database import engine
from .routers import auth_router, contacts_router, location_router, alerts_router, ride_router

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Aarise API", version="0.1.0")

# The Android app runs the frontend inside a WebView loaded from local assets, so
# requests come from a "null"/file origin. Loosen CORS accordingly; tighten the
# allow_origins list if you move the frontend to a hosted domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(contacts_router.router)
app.include_router(location_router.router)
app.include_router(alerts_router.router)
app.include_router(ride_router.router)


@app.get("/health")
def health():
    return {"status": "ok"}
