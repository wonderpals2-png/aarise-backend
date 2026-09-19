import datetime
import math
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import auth, models, schemas
from ..database import get_db


DEMO_DRIVERS = [
    {"name": "Ananya Sharma", "vehicle_model": "Honda Activa 6G", "vehicle_color": "Pearl White", "plate": "TS 09 GH 4821"},
    {"name": "Kavya Reddy", "vehicle_model": "TVS Jupiter", "vehicle_color": "Matte Blue", "plate": "TS 10 FA 7316"},
    {"name": "Priya Nair", "vehicle_model": "Suzuki Access 125", "vehicle_color": "Metallic Grey", "plate": "TS 08 JL 9054"},
    {"name": "Meera Iyer", "vehicle_model": "Honda Dio", "vehicle_color": "Vibrant Orange", "plate": "TS 11 BK 2689"},
    {"name": "Sneha Patel", "vehicle_model": "Yamaha Fascino", "vehicle_color": "Dark Matte Blue", "plate": "TS 07 CR 6142"},
]
FARE_BASE = 30
FARE_PER_KM = 12
ROAD_FACTOR = 1.3
T_SEARCH = 4
T_ARRIVE = 25
T_OTP_WAIT = 8
T_RIDE_MIN = 30
T_RIDE_MAX = 60
DRIVER_START_KM = 1.2


router = APIRouter(prefix="/rides", tags=["rides"])


def now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_km = 6371.0
    lat1_rad, lng1_rad, lat2_rad, lng2_rad = map(math.radians, (lat1, lng1, lat2, lng2))
    d_lat = lat2_rad - lat1_rad
    d_lng = lng2_rad - lng1_rad
    value = math.sin(d_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(d_lng / 2) ** 2
    return radius_km * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _estimate(payload: schemas.RideEstimateIn) -> tuple[float, int]:
    distance_km = _haversine_km(
        payload.pickup_lat, payload.pickup_lng, payload.drop_lat, payload.drop_lng
    ) * ROAD_FACTOR
    return distance_km, round(FARE_BASE + FARE_PER_KM * distance_km)


def _ride_duration(ride: models.Ride) -> float:
    return max(T_RIDE_MIN, min(T_RIDE_MAX, ride.distance_km * 6))


def _status(ride: models.Ride, current_time: datetime.datetime) -> str:
    if ride.cancelled_at is not None:
        return "cancelled"
    elapsed = max(0.0, (current_time - ride.requested_at).total_seconds())
    if elapsed < T_SEARCH:
        return "searching"
    if elapsed < T_SEARCH + T_ARRIVE:
        return "driver_arriving"
    if elapsed < T_SEARCH + T_ARRIVE + T_OTP_WAIT:
        return "driver_arrived"
    if elapsed < T_SEARCH + T_ARRIVE + T_OTP_WAIT + _ride_duration(ride):
        return "in_ride"
    return "completed"


def _destination(lat: float, lng: float, bearing_deg: int, distance_km: float) -> tuple[float, float]:
    angular_distance = distance_km / 6371.0
    bearing = math.radians(bearing_deg)
    lat_rad = math.radians(lat)
    lng_rad = math.radians(lng)
    out_lat = math.asin(
        math.sin(lat_rad) * math.cos(angular_distance)
        + math.cos(lat_rad) * math.sin(angular_distance) * math.cos(bearing)
    )
    out_lng = lng_rad + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(lat_rad),
        math.cos(angular_distance) - math.sin(lat_rad) * math.sin(out_lat),
    )
    return math.degrees(out_lat), math.degrees(out_lng)


def _interpolate(start_lat: float, start_lng: float, end_lat: float, end_lng: float, fraction: float) -> tuple[float, float]:
    fraction = max(0.0, min(1.0, fraction))
    return (
        start_lat + (end_lat - start_lat) * fraction,
        start_lng + (end_lng - start_lng) * fraction,
    )


def _driver_position(ride: models.Ride, status: str, elapsed: float) -> tuple[float, float]:
    if status == "driver_arriving":
        start_lat, start_lng = _destination(
            ride.pickup_lat, ride.pickup_lng, ride.bearing_deg, DRIVER_START_KM
        )
        return _interpolate(
            start_lat,
            start_lng,
            ride.pickup_lat,
            ride.pickup_lng,
            (elapsed - T_SEARCH) / T_ARRIVE,
        )
    if status == "driver_arrived":
        return ride.pickup_lat, ride.pickup_lng
    if status == "in_ride":
        trip_elapsed = elapsed - T_SEARCH - T_ARRIVE - T_OTP_WAIT
        return _interpolate(
            ride.pickup_lat,
            ride.pickup_lng,
            ride.drop_lat,
            ride.drop_lng,
            trip_elapsed / _ride_duration(ride),
        )
    return ride.drop_lat, ride.drop_lng


def _ride_view(ride: models.Ride, db: Session, current_time: datetime.datetime) -> dict:
    status = _status(ride, current_time)
    if status == "completed" and ride.completed_at is None:
        ride.completed_at = current_time
        db.commit()
        db.refresh(ride)

    result = {
        "id": ride.id,
        "status": status,
        "pickup_lat": ride.pickup_lat,
        "pickup_lng": ride.pickup_lng,
        "pickup_label": ride.pickup_label,
        "drop_lat": ride.drop_lat,
        "drop_lng": ride.drop_lng,
        "drop_label": ride.drop_label,
        "distance_km": ride.distance_km,
        "est_fare": ride.est_fare,
    }
    if status not in {"searching", "cancelled"}:
        driver = DEMO_DRIVERS[ride.demo_driver_idx]
        elapsed = max(0.0, (current_time - ride.requested_at).total_seconds())
        driver_lat, driver_lng = _driver_position(ride, status, elapsed)
        result.update(
            driver_name=driver["name"],
            vehicle_model=driver["vehicle_model"],
            vehicle_color=driver["vehicle_color"],
            plate=driver["plate"],
            driver_lat=driver_lat,
            driver_lng=driver_lng,
            eta_sec=max(0, math.ceil(T_SEARCH + T_ARRIVE - elapsed)),
        )
    if status in {"driver_arriving", "driver_arrived"}:
        result["otp"] = ride.otp
    return result


def _get_owned_ride(ride_id: str, rider: models.User, db: Session) -> models.Ride:
    ride = db.query(models.Ride).filter(models.Ride.id == ride_id, models.Ride.rider_id == rider.id).first()
    if ride is None:
        raise HTTPException(status_code=404, detail="Ride not found")
    return ride


@router.post("/estimate", response_model=schemas.RideEstimateOut)
def estimate_ride(
    payload: schemas.RideEstimateIn,
    current_user: models.User = Depends(auth.get_current_user),
):
    distance_km, est_fare = _estimate(payload)
    return {"distance_km": distance_km, "est_fare": est_fare}


@router.post("", response_model=schemas.RideOut, response_model_exclude_none=True, status_code=201)
def create_ride(
    payload: schemas.RideCreateIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    active_rides = (
        db.query(models.Ride)
        .filter(
            models.Ride.rider_id == current_user.id,
            models.Ride.cancelled_at.is_(None),
            models.Ride.completed_at.is_(None),
        )
        .order_by(models.Ride.requested_at.desc())
        .all()
    )
    for active_ride in active_rides:
        if _status(active_ride, now()) != "completed":
            raise HTTPException(status_code=409, detail="You already have an active ride")
        active_ride.completed_at = now()
    if active_rides:
        db.commit()

    distance_km, est_fare = _estimate(payload)
    ride = models.Ride(
        rider_id=current_user.id,
        pickup_lat=payload.pickup_lat,
        pickup_lng=payload.pickup_lng,
        pickup_label=payload.pickup_label,
        drop_lat=payload.drop_lat,
        drop_lng=payload.drop_lng,
        drop_label=payload.drop_label,
        distance_km=distance_km,
        est_fare=est_fare,
        otp=f"{secrets.randbelow(10000):04d}",
        demo_driver_idx=secrets.randbelow(len(DEMO_DRIVERS)),
        bearing_deg=secrets.randbelow(360),
        requested_at=now(),
    )
    db.add(ride)
    db.commit()
    db.refresh(ride)
    return _ride_view(ride, db, now())


@router.get("/active", response_model=schemas.RideOut, response_model_exclude_none=True)
def active_ride(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    ride = (
        db.query(models.Ride)
        .filter(
            models.Ride.rider_id == current_user.id,
            models.Ride.cancelled_at.is_(None),
            models.Ride.completed_at.is_(None),
        )
        .order_by(models.Ride.requested_at.desc())
        .first()
    )
    if ride is None:
        raise HTTPException(status_code=404, detail="No active ride")
    view = _ride_view(ride, db, now())
    if view["status"] == "completed":
        raise HTTPException(status_code=404, detail="No active ride")
    return view


@router.get("/{ride_id}", response_model=schemas.RideOut, response_model_exclude_none=True)
def get_ride(
    ride_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    return _ride_view(_get_owned_ride(ride_id, current_user, db), db, now())


@router.post("/{ride_id}/cancel", response_model=schemas.RideOut, response_model_exclude_none=True)
def cancel_ride(
    ride_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    ride = _get_owned_ride(ride_id, current_user, db)
    status = _status(ride, now())
    if status == "in_ride":
        raise HTTPException(status_code=409, detail="An in-progress ride cannot be cancelled")
    if status == "completed":
        if ride.completed_at is None:
            ride.completed_at = now()
            db.commit()
        raise HTTPException(status_code=409, detail="A completed ride cannot be cancelled")
    if status != "cancelled":
        ride.cancelled_at = now()
        db.commit()
        db.refresh(ride)
    return _ride_view(ride, db, now())
