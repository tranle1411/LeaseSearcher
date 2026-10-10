# Deploy the replacement without interrupting the Streamlit demo

The existing Render service runs Streamlit. The new app uses a Docker runtime and a different start command. Keep the old service while validating a **new free Docker web service**. Do not change the legacy root `requirements.txt` or its start command to run V2.

## 1. Publish the reviewed changes

Inspect `git status`, review the changes and commit/push them to your GitHub repository. Do not add `.local`, `.env`, credentials, generated private review workbooks or `node_modules`. The Docker image includes only the validated snapshot and application; it excludes raw source spreadsheets and the person-level IPUMS file.

## 2. Create the free Render service

In Render select **New → Web Service**, connect `tranle1411/LeaseSearcher`, and select the branch containing V2.

| Setting | Value |
|---|---|
| Name | `lease-searcher-v2` (or another available name) |
| Language/runtime | Docker |
| Dockerfile path | `./Dockerfile` |
| Root directory | blank (repository root) |
| Instance | Free |
| Health check path | `/api/health` |
| Docker command override | blank; use the Dockerfile CMD |
| Environment variables | none required for snapshot mode |

Alternatively use **New → Blueprint** with the supplied `render.yaml`; verify it creates only the free web service. No paid database, persistent disk, AWS account, map API key or paid domain is required. The app binds `0.0.0.0:$PORT`, as required by [Render's port guidance](https://render.com/docs/web-services#port-binding).

Wait for “Your service is live,” then check `/api/health` and open the root URL. Run a search and download Excel. The default search should return ten historical matches with demo-assumption and estimated-cost labels. Enabling “Hide unconfirmed availability” can correctly return zero. Test on a phone and check the logs for startup errors. Keep the old URL until this succeeds. The new service receives its own URL; update portfolio/client links after validation rather than assuming the original URL moved.

## 3. Optional Supabase PostgreSQL

Snapshot mode is sufficient for the first presentation. PostgreSQL support can be exercised locally without a new account. To use Supabase, create or use a suitable project, obtain its **server connection string**, and keep the password out of Git/chat. On an IPv4-only host, use a supported session-pooler endpoint from Supabase's Connect panel; follow [Supabase connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres). Use `sslmode=require` and the `postgresql+psycopg://` scheme.

From a trusted local terminal, set `DATABASE_URL`, then:

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m backend.storage
```

Add the same `DATABASE_URL` to Render's environment settings and redeploy. `/api/metadata` should report `postgresql`. If unreachable, absent or mismatched, it reports `snapshot-fallback`; the snapshot remains usable. Migrations/seeding are explicit deployment steps, never run inside search requests. After each reviewed snapshot change, migrate if needed and seed that exact version **before** deploying its image. Old versions remain available for audit.

## 4. Understand the free demo's limits

[Render free services](https://render.com/docs/free) sleep after inactivity and can take about a minute to wake. Open the demo before a meeting. Free services share the account's monthly usage allowance; two running free demos can consume it faster. Filesystem changes are ephemeral, so rebuild reviewed snapshots in Git rather than uploading data into the running container. [Supabase free projects](https://supabase.com/docs/guides/platform/free-project-pausing) can pause for inactivity; restore them before a demo or use the explicit snapshot fallback. No artificial keep-alive is configured.

## What the owner must supply

- GitHub push and Render account actions if these accounts are not connected to the working environment.
- No broker verification is required for the approved demo assumptions. Current evidence is needed for a future verified product; the optional `.local/broker-review.xlsx` standardizes collection.
- A Census API key only if county demographics should be refreshed; credentials stay in environment settings.
- A Supabase connection string only if enabling hosted PostgreSQL; not required for the free snapshot presentation.

Docker is not installed on the implementation machine. Local Python, PostgreSQL and browser checks were run directly. The Docker build/smoke job is configured in GitHub Actions and still needs its first remote run.
