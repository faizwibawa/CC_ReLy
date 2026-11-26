# AWS Evidence

Every file here is a genuine capture from the AWS Academy sandbox or a real test run.
Account IDs and live Function URLs are cropped or omitted.

| # | File | What it shows | Requirement |
|---|---|---|---|
| 01 | `01-connectivity-test-cloudshell.png` | CloudShell, 26 Nov 2026: HTTP 200 from a test Lambda Function URL that wrote and read back a record in DynamoDB `ReLy-TrafficSignals` (ACTIVE, on-demand, PK `signal_id`); same record read directly with the CLI | Initial AWS connectivity; storage permissions |
| 02 | *pending* | `deploy.sh` output: stack deployed + health check HTTP 200 | API route |
| 03 | *pending* | `api_smoke_test.py` against the live URL (11 checks) | Function test / CRUD |
| 04 | *pending* | DynamoDB console: items written by the simulator | Database connectivity |
| 05 | *pending* | Lambda console: function, LabRole, Function URL | Components / IAM |
| 06 | *pending* | CloudWatch Logs: JSON request lines | Logs / function execution |
| 07 | *pending* | Simulator terminal output (phase changes, manual override 409) | Hybrid ingestion |
| 08 | *pending* | Mobile app showing live data | End-to-end |

Local test outputs (no AWS): `local-unit-tests.txt`, `local-smoke-test.txt`, and
`local-app-integration.png` (mobile web app in API mode against `backend/local_server.py` while the
simulator runs — Admin, Signals and Drive screens showing simulator-written records).
