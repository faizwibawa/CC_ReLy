"""Input validation for the ReLy TrafficSignal entity.

Kept free of AWS dependencies so it can be unit-tested locally.
"""
import re

PHASES = ("RED", "YELLOW", "GREEN")
CONGESTION_LEVELS = ("FREE", "MODERATE", "HEAVY")
DATA_SOURCES = ("MANUAL", "SIMULATOR")

SIGNAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_REMAINING_SECONDS = 600  # a single phase longer than 10 minutes is treated as bad data

# Fields a client may send. `updated_at` and `phase_ends_at` are always set by the server.
REQUIRED_ON_CREATE = (
    "signal_id",
    "location",
    "latitude",
    "longitude",
    "current_phase",
    "remaining_seconds",
    "confidence_score",
    "data_source",
)
OPTIONAL_FIELDS = ("congestion_level", "detour")
WRITABLE_FIELDS = REQUIRED_ON_CREATE + OPTIONAL_FIELDS


class ValidationError(Exception):
    """Raised when a request body is invalid. `errors` is a list of messages."""

    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = errors


def _is_number(value):
    # bool is a subclass of int in Python; reject it explicitly.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_range(errors, name, value, low, high):
    if not _is_number(value):
        errors.append(f"{name} must be a number")
    elif not (low <= value <= high):
        errors.append(f"{name} must be between {low} and {high}")


def validate_signal_id(signal_id):
    if not isinstance(signal_id, str) or not SIGNAL_ID_PATTERN.match(signal_id):
        raise ValidationError(
            ["signal_id must be 1-64 characters: letters, digits, '-' or '_'"]
        )


def _validate_detour(errors, detour):
    if detour is None:
        return
    if not isinstance(detour, dict):
        errors.append("detour must be an object or null")
        return
    label = detour.get("label")
    if not isinstance(label, str) or not label.strip() or len(label) > 160:
        errors.append("detour.label must be a non-empty string (max 160 chars)")
    _check_range(errors, "detour.lat", detour.get("lat"), -90, 90)
    _check_range(errors, "detour.lng", detour.get("lng"), -180, 180)
    unknown = set(detour) - {"label", "lat", "lng"}
    if unknown:
        errors.append(f"detour has unknown fields: {', '.join(sorted(unknown))}")


def validate_payload(body, *, partial):
    """Validate a create (partial=False) or update (partial=True) body.

    Returns a cleaned dict containing only writable fields.
    """
    if not isinstance(body, dict):
        raise ValidationError(["request body must be a JSON object"])

    errors = []
    unknown = set(body) - set(WRITABLE_FIELDS)
    # Server-managed fields are silently ignored rather than rejected, so a client
    # can send back an object it previously received.
    unknown -= {"updated_at", "phase_ends_at"}
    if unknown:
        errors.append(f"unknown fields: {', '.join(sorted(unknown))}")

    if not partial:
        missing = [f for f in REQUIRED_ON_CREATE if f not in body]
        if missing:
            errors.append(f"missing required fields: {', '.join(missing)}")
    elif not any(f in body for f in WRITABLE_FIELDS if f != "signal_id"):
        errors.append("update body must contain at least one updatable field")

    if "signal_id" in body:
        try:
            validate_signal_id(body["signal_id"])
        except ValidationError as exc:
            errors.extend(exc.errors)

    if "location" in body:
        loc = body["location"]
        if not isinstance(loc, str) or not loc.strip() or len(loc) > 120:
            errors.append("location must be a non-empty string (max 120 chars)")

    if "latitude" in body:
        _check_range(errors, "latitude", body["latitude"], -90, 90)
    if "longitude" in body:
        _check_range(errors, "longitude", body["longitude"], -180, 180)

    if "current_phase" in body and body["current_phase"] not in PHASES:
        errors.append(f"current_phase must be one of {', '.join(PHASES)}")

    if "remaining_seconds" in body:
        _check_range(
            errors, "remaining_seconds", body["remaining_seconds"], 0, MAX_REMAINING_SECONDS
        )

    if "confidence_score" in body:
        _check_range(errors, "confidence_score", body["confidence_score"], 0, 1)

    if "congestion_level" in body and body["congestion_level"] not in CONGESTION_LEVELS:
        errors.append(f"congestion_level must be one of {', '.join(CONGESTION_LEVELS)}")

    if "data_source" in body and body["data_source"] not in DATA_SOURCES:
        errors.append(f"data_source must be one of {', '.join(DATA_SOURCES)}")

    if "detour" in body:
        _validate_detour(errors, body["detour"])

    if errors:
        raise ValidationError(errors)

    return {k: v for k, v in body.items() if k in WRITABLE_FIELDS}
