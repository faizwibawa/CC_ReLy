"""ReLy-SignalHandler — AWS Lambda entry point.

Invoked through a Lambda Function URL (payload format 2.0). One function handles all
routes of the ReLy REST API:

    GET    /                      health check
    POST   /signals               create (register) a traffic signal
    GET    /signals               list all traffic signals
    GET    /signals/{signal_id}   read one traffic signal
    PUT    /signals/{signal_id}   update a traffic signal (partial update allowed)
    DELETE /signals/{signal_id}   delete a traffic signal

Remaining time is stored as an absolute timestamp (`phase_ends_at`) and converted to
`remaining_seconds` on every read, so the value never goes stale between updates.
"""
import base64
import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

from repository import (
    AlreadyExists,
    DynamoSignalRepository,
    NotFound,
    SourceConflict,
)
from validation import DATA_SOURCES, ValidationError, validate_payload, validate_signal_id

SERVICE_NAME = "ReLy-SignalHandler"
_repo = None


def get_repo():
    global _repo
    if _repo is None:
        _repo = DynamoSignalRepository(os.environ.get("TABLE_NAME"))
    return _repo


def set_repo(repo):
    """Used by unit tests to inject an in-memory repository."""
    global _repo
    _repo = repo


# --------------------------------------------------------------------------- helpers
def utc_now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def response(status, body=None):
    resp = {"statusCode": status, "headers": {"Content-Type": "application/json"}}
    if body is not None:
        resp["body"] = json.dumps(body)
    return resp


def error(status, code, message, details=None):
    payload = {"error": {"code": code, "message": message}}
    if details:
        payload["error"]["details"] = details
    return response(status, payload)


def present(item, now=None):
    """Shape a stored item for API output: compute remaining_seconds from phase_ends_at."""
    now = now or utc_now()
    out = dict(item)
    ends = out.get("phase_ends_at")
    if ends:
        delta = (parse_iso(ends) - now).total_seconds()
        out["remaining_seconds"] = max(0, math.ceil(delta))
    else:
        out["remaining_seconds"] = 0
    out.setdefault("congestion_level", None)
    out.setdefault("detour", None)
    return out


def to_storage(changes, now):
    """Convert validated client fields into stored attributes."""
    stored = dict(changes)
    if "remaining_seconds" in stored:
        seconds = stored.pop("remaining_seconds")
        stored["phase_ends_at"] = iso(now + timedelta(seconds=seconds))
    stored["updated_at"] = iso(now)
    return stored


def parse_body(event):
    raw = event.get("body")
    if raw in (None, ""):
        raise ValidationError(["request body is required"])
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise ValidationError(["request body must be valid JSON"])


# --------------------------------------------------------------------------- routes
def create_signal(event):
    data = validate_payload(parse_body(event), partial=False)
    now = utc_now()
    item = to_storage(data, now)
    try:
        get_repo().create(item)
    except AlreadyExists:
        return error(409, "ALREADY_EXISTS", f"signal '{data['signal_id']}' already exists; use PUT to update it")
    return response(201, present(item, now))


def list_signals(_event):
    now = utc_now()
    items = sorted((present(i, now) for i in get_repo().list()), key=lambda i: i["signal_id"])
    return response(200, {"items": items, "count": len(items), "generated_at": iso(now)})


def get_signal(_event, signal_id):
    try:
        return response(200, present(get_repo().get(signal_id)))
    except NotFound:
        return error(404, "NOT_FOUND", f"signal '{signal_id}' not found")


def update_signal(event, signal_id):
    data = validate_payload(parse_body(event), partial=True)
    if "signal_id" in data and data.pop("signal_id") != signal_id:
        raise ValidationError(["signal_id in body does not match the URL"])

    params = event.get("queryStringParameters") or {}
    required_source = params.get("if_source")
    if required_source is not None and required_source not in DATA_SOURCES:
        raise ValidationError([f"if_source must be one of {', '.join(DATA_SOURCES)}"])

    now = utc_now()
    try:
        item = get_repo().update(signal_id, to_storage(data, now), required_source)
    except NotFound:
        return error(404, "NOT_FOUND", f"signal '{signal_id}' not found")
    except SourceConflict as exc:
        return error(
            409,
            "SOURCE_CONFLICT",
            f"signal '{signal_id}' is controlled by {exc.actual_source}; update skipped",
            {"data_source": exc.actual_source},
        )
    return response(200, present(item, now))


def delete_signal(_event, signal_id):
    try:
        get_repo().delete(signal_id)
    except NotFound:
        return error(404, "NOT_FOUND", f"signal '{signal_id}' not found")
    return response(200, {"deleted": signal_id})


def route(event):
    http = event.get("requestContext", {}).get("http", {})
    method = http.get("method", "GET").upper()
    path = (event.get("rawPath") or http.get("path") or "/").rstrip("/") or "/"
    parts = [unquote(p) for p in path.strip("/").split("/") if p]

    if parts == []:
        if method == "GET":
            return response(200, {"service": SERVICE_NAME, "status": "ok", "time": iso(utc_now())})
        return error(405, "METHOD_NOT_ALLOWED", f"{method} not allowed on /")

    if parts[0] != "signals" or len(parts) > 2:
        return error(404, "ROUTE_NOT_FOUND", f"no route for {path}")

    if len(parts) == 1:
        if method == "GET":
            return list_signals(event)
        if method == "POST":
            return create_signal(event)
        return error(405, "METHOD_NOT_ALLOWED", f"{method} not allowed on /signals")

    signal_id = parts[1]
    validate_signal_id(signal_id)
    if method == "GET":
        return get_signal(event, signal_id)
    if method == "PUT":
        return update_signal(event, signal_id)
    if method == "DELETE":
        return delete_signal(event, signal_id)
    return error(405, "METHOD_NOT_ALLOWED", f"{method} not allowed on /signals/{{signal_id}}")


def log(entry):
    print(json.dumps(entry, default=str))


def lambda_handler(event, context):
    started = time.perf_counter()
    request_id = getattr(context, "aws_request_id", "local")
    http = event.get("requestContext", {}).get("http", {})
    try:
        result = route(event)
    except ValidationError as exc:
        result = error(400, "VALIDATION_ERROR", "request is invalid", exc.errors)
    except Exception as exc:  # unexpected failure: log details, return a generic 500
        log({"level": "ERROR", "request_id": request_id, "error": repr(exc)})
        result = error(500, "INTERNAL_ERROR", f"unexpected error (request id {request_id})")
    log(
        {
            "level": "INFO",
            "request_id": request_id,
            "method": http.get("method"),
            "path": event.get("rawPath"),
            "status": result["statusCode"],
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    )
    return result
