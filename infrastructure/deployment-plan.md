# ReLy — Deployment Plan

Target: **AWS Academy Cloud Foundations sandbox** (us-east-1). The sandbox deletes all
resources when a session ends, so the backend is fully defined as code and redeployed per session.

## 1. Resource inventory
| Resource | Name | Created by | Notes |
|---|---|---|---|
| CloudFormation stack | `rely-stack` | `deploy.sh` | Executed as `LabRole` |
| DynamoDB table | `ReLy-TrafficSignals` | stack | PK `signal_id` (S), on-demand |
| Lambda function | `ReLy-SignalHandler` | stack | Python 3.12, 128 MB, role `LabRole` |
| Lambda Function URL | (generated) | stack | `AuthType NONE`, CORS |
| Lambda permissions | 2 | stack | `InvokeFunctionUrl` + `InvokeFunction` (URL only) |
| Log group | `/aws/lambda/ReLy-SignalHandler` | stack | 7-day retention |
| S3 bucket | `rely-artifacts-<account>-<region>` | `deploy.sh` | Private; Lambda zip |

## 2. Prerequisites (each session)
1. Canvas → **AWS Academy Cloud Foundations → Modules → Sandbox → Sandbox Environment** →
   **Start Lab**; wait until the status is ready (~5–8 min); click **AWS** to open the console.
2. Region selector must show **N. Virginia (us-east-1)**.
3. Open **CloudShell** (terminal icon in the console's top bar).

## 3. Deployment sequence
```bash
# in CloudShell
git clone https://github.com/faizwibawa/CC_RelyXAWS.git   # or: cd CC_RelyXAWS && git pull
cd CC_RelyXAWS
bash infrastructure/deploy.sh             # ~2 min; prints RELY_API_URL and a health check
export RELY_API_URL=<printed URL>
python3 backend/tests/api_smoke_test.py   # expect 11/11 PASS
```
On your own computer: put `RELY_API_URL=...` in `.env`, then
`python simulator/simulator.py` and open the dashboard.

Optional: restrict CORS once the dashboard has a fixed URL:
`RELY_ALLOWED_ORIGIN=https://<dashboard-origin> bash infrastructure/deploy.sh`.

## 4. Verification checklist
- [ ] `deploy.sh` ends with `HTTP 200` from `GET /`
- [ ] CloudFormation console: `rely-stack` = `CREATE_COMPLETE` / `UPDATE_COMPLETE`
- [ ] DynamoDB console: table `ReLy-TrafficSignals` is **Active**; items appear after the simulator runs
- [ ] Lambda console: `ReLy-SignalHandler`, role `LabRole`, Function URL shown
- [ ] CloudWatch → Log groups → `/aws/lambda/ReLy-SignalHandler` shows JSON request lines
- [ ] Smoke test 11/11 PASS

## 5. Updating code
Edit `backend/src/*`, run unit tests locally, commit, `git pull` in CloudShell, rerun
`deploy.sh` (it uploads a new zip with a unique key, so CloudFormation updates the function).

## 6. Rollback
- **Bad code:** `git checkout <previous-commit>` in CloudShell and rerun `deploy.sh`.
- **Failed stack update:** CloudFormation rolls back automatically to the last good state;
  check *Events* tab for the failing resource.
- **Stack stuck in `ROLLBACK_COMPLETE` on first create:** `bash infrastructure/destroy.sh`, then redeploy.

## 7. Cleanup
`bash infrastructure/destroy.sh` deletes the stack and the artifact bucket and lists any
remaining `ReLy*` tables/functions (expected: none). Ending the lab session also wipes everything.

## 8. Known risks
| Risk | Mitigation |
|---|---|
| Session ends mid-demo | Deploy at the start of a fresh session; capture evidence immediately |
| Sandbox policy changes | Re-run the permission checks in `docs/architecture.md` §5 |
| Table name already used (e.g., old test stack) | Delete the other stack first |
| Public URL abused | Simulated data only; redeploy gives a new URL; future: auth + throttling |
