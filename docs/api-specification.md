# ReLy API Specification (v1, Week 12 prototype)

**Base URL:** the Lambda Function URL printed by `infrastructure/deploy.sh`, e.g.
`https://<url-id>.lambda-url.us-east-1.on.aws` (kept in `.env`, never committed).
**Format:** JSON over HTTPS. **All data is simulated.**

## 1. Resource: `TrafficSignal`

| Field | Type | Required on create | Rules | Notes |
|---|---|---|---|---|
| `signal_id` | string | ✅ | 1–64 chars, `A-Z a-z 0-9 - _` | Primary key (DynamoDB partition key) |
| `location` | string | ✅ | 1–120 chars | Human-readable name |
| `latitude` | number | ✅ | −90 … 90 | |
| `longitude` | number | ✅ | −180 … 180 | |
| `current_phase` | string | ✅ | `RED` \| `YELLOW` \| `GREEN` | |
| `remaining_seconds` | number | ✅ | 0 … 600 | **Input:** seconds left in the phase. **Output:** recomputed on every read |
| `confidence_score` | number | ✅ | 0 … 1 | Reliability of the reading |
| `data_source` | string | ✅ | `MANUAL` \| `SIMULATOR` | Who controls the record |
| `congestion_level` | string | optional | `FREE` \| `MODERATE` \| `HEAVY` | `null` if unknown |
| `detour` | object \| null | optional | `{label: string ≤160, lat, lng}` | Suggested alternative waypoint |
| `phase_ends_at` | string (ISO-8601 UTC) | server-set | — | Stored instead of `remaining_seconds` |
| `updated_at` | string (ISO-8601 UTC) | server-set | — | Time of last write |

**Why `phase_ends_at`?** A stored "18 seconds left" is wrong one second later. The API stores
the absolute end time and returns `remaining_seconds = max(0, ceil(phase_ends_at − now))`,
so every read is current. `remaining_seconds = 0` means "awaiting update".

Unknown fields → `400`. `updated_at` / `phase_ends_at` sent by a client are ignored.

## 2. Endpoints (four CRUD operations)

| CRUD | Method & path | Success | Errors |
|---|---|---|---|
| Create | `POST /signals` | `201` created record | `400`, `409` |
| Read (all) | `GET /signals` | `200` `{items, count, generated_at}` | — |
| Read (one) | `GET /signals/{signal_id}` | `200` record | `400`, `404` |
| Update | `PUT /signals/{signal_id}` | `200` updated record | `400`, `404`, `409` |
| Delete | `DELETE /signals/{signal_id}` | `200` `{deleted}` | `400`, `404` |
| (health) | `GET /` | `200` `{service, status, time}` | — |

Other methods on a known path → `405`. Unknown paths → `404`.

### 2.1 Create — `POST /signals`
```http
POST /signals
Content-Type: application/json

{
  "signal_id": "YK-NOLKM-03",
  "location": "Simpang Titik Nol Kilometer",
  "latitude": -7.8013,
  "longitude": 110.3648,
  "current_phase": "RED",
  "remaining_seconds": 45,
  "confidence_score": 0.92,
  "congestion_level": "HEAVY",
  "detour": { "label": "Turn right via Jl. KH Ahmad Dahlan", "lat": -7.8017, "lng": 110.3605 },
  "data_source": "MANUAL"
}
```
`201 Created`
```json
{
  "signal_id": "YK-NOLKM-03",
  "location": "Simpang Titik Nol Kilometer",
  "latitude": -7.8013, "longitude": 110.3648,
  "current_phase": "RED",
  "confidence_score": 0.92,
  "congestion_level": "HEAVY",
  "detour": { "label": "Turn right via Jl. KH Ahmad Dahlan", "lat": -7.8017, "lng": 110.3605 },
  "data_source": "MANUAL",
  "phase_ends_at": "2026-11-26T03:15:45.120Z",
  "updated_at": "2026-11-26T03:15:00.120Z",
  "remaining_seconds": 45
}
```
Creating an existing `signal_id` → `409 ALREADY_EXISTS` (use `PUT`). The check is atomic
(DynamoDB condition `attribute_not_exists(signal_id)`).

### 2.2 Read all — `GET /signals`
`200 OK` → `{"items": [TrafficSignal, …], "count": 5, "generated_at": "…Z"}` (sorted by `signal_id`).

### 2.3 Read one — `GET /signals/{signal_id}`
`200 OK` → one `TrafficSignal`. Unknown id → `404 NOT_FOUND`.

### 2.4 Update — `PUT /signals/{signal_id}`
Partial update: send only the fields to change (at least one). `signal_id` in the body, if
present, must match the URL.
```http
PUT /signals/YK-NOLKM-03?if_source=SIMULATOR
{ "current_phase": "GREEN", "remaining_seconds": 30, "confidence_score": 0.9, "congestion_level": "MODERATE" }
```
Optional query `if_source=MANUAL|SIMULATOR`: update only if the record's current
`data_source` equals it, otherwise `409 SOURCE_CONFLICT` with
`details: {"data_source": "MANUAL"}`. The simulator always sends `if_source=SIMULATOR`,
so it can never overwrite an operator's manual edit (atomic DynamoDB condition).

### 2.5 Delete — `DELETE /signals/{signal_id}`
`200 OK` → `{"deleted": "YK-NOLKM-03"}`. Unknown id → `404`.

## 3. Errors
```json
{ "error": { "code": "VALIDATION_ERROR", "message": "request is invalid",
             "details": ["current_phase must be one of RED, YELLOW, GREEN",
                         "confidence_score must be between 0 and 1"] } }
```
| Status | `code` | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Bad JSON, missing/unknown fields, out-of-range values, bad `signal_id` |
| 404 | `NOT_FOUND` / `ROUTE_NOT_FOUND` | Record or route does not exist |
| 405 | `METHOD_NOT_ALLOWED` | Wrong method for the path |
| 409 | `ALREADY_EXISTS` / `SOURCE_CONFLICT` | Duplicate create / source mismatch on update |
| 500 | `INTERNAL_ERROR` | Unexpected failure (details only in CloudWatch, with request id) |

## 4. Authentication, authorization and CORS (prototype assumptions)
- **No end-user authentication** in Week 12: the Function URL uses `AuthType: NONE`.
  Acceptable only because all data is simulated and non-sensitive.
- **Server-side protection:** strict input validation, atomic conditional writes, the
  Lambda is invocable *only* through its URL (`InvokedViaFunctionUrl`), and the Lambda's
  data access is through the `LabRole` IAM role — clients never hold AWS credentials.
- **CORS:** allowed methods `GET, POST, PUT, DELETE`, header `content-type`; origin is a
  deploy parameter (`*` for the prototype; set to the dashboard's origin once hosted).
- **Planned (future work):** Amazon Cognito sign-in for the Admin screen, or `AuthType:
  AWS_IAM` with signed requests for the simulator; per-client rate limiting (API Gateway
  usage plans when available).

## 5. How each client uses the API
| Client | Calls |
|---|---|
| Driver app (Trip/Drive/Signals screens) | `GET /signals` every 15 s; counts down locally between refreshes |
| Admin screen (operator) | `POST`, `PUT`, `DELETE` for manual CRUD; sets `data_source: MANUAL` |
| Simulator | startup: `GET /signals/{id}` → `POST /signals` only if `404`; then `PUT /signals/{id}?if_source=SIMULATOR` on each phase change; `GET /signals` every 60 s to resume released signals |
| Smoke test | every route + error cases, on a temporary record it deletes afterwards |
