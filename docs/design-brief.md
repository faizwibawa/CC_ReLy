# ReLy — Design Brief (Week 12: Design & AWS Setup)

**Student:** Faiz Gymnastiar Wibawa · **Course:** AWS Cloud Computing (Individual Project) ·
**Track:** C — Serverless · **Repository:** `faizwibawa/CC_RelyXAWS`

## 1. Use case
**ReLy (Real-Time Traffic Signal Insight)** is a driving companion used alongside Google
Maps. It shows the status of traffic lights along the driver's route (phase, seconds
remaining, confidence) and the congestion around them. When the next light is **RED and
traffic is HEAVY**, ReLy suggests a nearby detour (e.g., a side street) and hands the route
to Google Maps through a deep link. To limit driver distraction, the driving screen is
glanceable and alerts are designed for voice/vibration.

For Week 12 the cloud part is framed as a **traffic-signal registry** (an inventory of
signal assets and their live status), which the driver app reads and an operator maintains.
Signal data comes from two sources: **manual entry** by an operator and a **Python
simulator** that generates phase changes. **All data is simulated**; no real traffic
controllers or municipal systems are connected.

## 2. Chosen track and architecture
**Track C — Serverless:** *Lambda Function URL → AWS Lambda → Amazon DynamoDB*, with IAM
(`LabRole`) and CloudWatch Logs, deployed by CloudFormation (see `docs/architecture.md`).

**Deviation from the track example:** the briefing's example uses API Gateway. In the AWS
Academy sandbox, `apigateway:POST` is denied for both the student identity and `LabRole`
(verified with the IAM policy simulator), so a **Lambda Function URL** provides the HTTPS
route instead. The track's three checkpoints are still met:
**API route** (Function URL + Lambda routing), **function test** (unit tests, live smoke
test, CloudWatch logs) and **storage permissions** (DynamoDB access only through LabRole).

## 3. Data entity — `TrafficSignal`
DynamoDB table `ReLy-TrafficSignals`, partition key `signal_id` (String), on-demand capacity.

| Attribute | Type | Description / rule |
|---|---|---|
| `signal_id` | String (PK) | Unique id, e.g. `YK-NOLKM-03` |
| `location` | String | Human-readable intersection name |
| `latitude`, `longitude` | Number | Valid coordinates |
| `current_phase` | String | `RED` / `YELLOW` / `GREEN` |
| `remaining_seconds` | Number | ≥ 0; stored as `phase_ends_at`, computed on read |
| `confidence_score` | Number | 0 – 1 |
| `congestion_level` | String | `FREE` / `MODERATE` / `HEAVY` |
| `detour` | Map / null | `{label, lat, lng}` suggested alternative waypoint |
| `data_source` | String | `MANUAL` / `SIMULATOR` |
| `updated_at` | String | ISO-8601 UTC, set by the server |

## 4. Four CRUD endpoints
| CRUD | Endpoint | Purpose |
|---|---|---|
| **Create** | `POST /signals` | Register a signal (`409` if it already exists) |
| **Read** | `GET /signals` · `GET /signals/{signal_id}` | List all / get one |
| **Update** | `PUT /signals/{signal_id}` | Partial update; `?if_source=SIMULATOR` prevents overwriting manual edits |
| **Delete** | `DELETE /signals/{signal_id}` | Remove a signal |

Errors use one JSON shape (`400` validation, `404`, `405`, `409`, `500`). Full details:
`docs/api-specification.md`.

## 5. Security, network and cost (summary)
- Single public HTTPS entry point; no VPC needed (managed services only).
- Clients hold no AWS credentials; data access only through the Lambda's role.
- Prototype limits: no end-user authentication and `LabRole` broader than least privilege
  (sandbox cannot create roles) — both documented, with Cognito / scoped roles as next steps.
- Estimated cost: under US$0.01 per lab session; no idle cost.

## 6. Scope boundary
**Week 12 (this submission):** signal registry API on AWS, simulator, mobile-first client,
connectivity and test evidence. **Future work:** live route reading and rerouting, real
traffic data, Google Maps Platform integration, GPS proximity alerts, authentication.
