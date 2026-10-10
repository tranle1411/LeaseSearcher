# LeaseSearcher

A California restaurant-location research demo for a consulting-client conversation. React/TypeScript collects a restaurant brief; FastAPI applies explicit demo eligibility rules, ranks at most ten sites, explains each score and exports the same shortlist to Excel. There is no trained ML model.

**Demo policy:** assume workbook listings exist and are restaurant-eligible; these are not verified approvals. Estimate monthly cost from midpoint advertised rent and the midpoint of the offered size range overlapping the requested range, plus disclosed monthly fees. Annual rates are divided by 12. Undisclosed fees remain unknown and excluded. Missing usable rent, size, coordinates or source links still exclude a listing. Synthetic records exist only in tests.

## Architecture

```mermaid
flowchart LR
  Raw[Historical CSV / Excel / geocode cache] --> Import[Python validated import]
  Review[Broker review workbook] --> Import
  ACS[Optional Census county aggregates] --> Import
  Import --> Snapshot[Versioned JSON snapshot + lineage + quarantine report]
  Snapshot --> DB[(PostgreSQL immutable versions)]
  Snapshot --> API[FastAPI / deterministic scoring / Excel]
  DB --> API
  API --> UI[React + TypeScript + Leaflet]
  CI[pytest + Vitest + Playwright / GitHub Actions] --> Container[Docker / Render]
```

The small demo loads a compact snapshot once at startup. It never loads the 95 MB person-level IPUMS file during a web request. PostgreSQL stores versioned validated snapshot documents through SQLAlchemy; Alembic owns the schema. It is **not** a normalized property warehouse or a PostGIS system. Database reads must match the bundled version and content; an outage uses that identical snapshot, reports `snapshot-fallback`, and retries after a 30-second cooldown. Snapshot-only mode works without credentials.

See [current-project audit](PROJECT_AUDIT.md), [design and future budget](ARCHITECTURE_V2.md), and [deployment guide](docs/DEPLOYMENT.md). The original Streamlit files remain available during migration; root `requirements.txt` still belongs to that app.

## Run locally

Prerequisites: Python 3.12, Node 22+, pnpm 11.25.0. Install pnpm with `npm install --global pnpm@11.25.0` if necessary.

PowerShell, from the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements/dev.txt
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open [the local demo](http://127.0.0.1:8000) or [OpenAPI docs](http://127.0.0.1:8000/docs). On macOS/Linux use `.venv/bin/python` in place of `.venv\Scripts\python.exe`.

For frontend development run `pnpm --dir frontend dev` in a second terminal; Vite proxies `/api` to port 8000. The production build serves UI and API from one origin, with no CORS configuration or frontend secrets.

With Docker installed, `docker compose up --build` starts PostgreSQL, applies migrations, seeds the pinned dataset, and serves the app on port 8000. The local-only database password in Compose is for disposable development. Never reuse it on a public database. Docker was unavailable on the implementation machine; image build and smoke checks are included in CI, but have not yet run remotely.

## Reproduce and review the data

```powershell
.venv\Scripts\python.exe -m pipeline.build
.venv\Scripts\python.exe -m pipeline.review
```

The first command rebuilds `datasets/snapshot.json` deterministically from the supplied wide Crexi export, original and prepared rent workbooks, restaurant observations and geocode cache. `datasets/build-config.json` pins demo assumptions, midpoint pricing and address-only locations. Broker review is optional for this demo. The second produces `.local/broker-review.xlsx` with stable listing IDs, source links, reference rent and blank review fields. Give the workbook to the person verifying the lease facts. Only rows with evidence are imported; all three required checks must be explicitly TRUE, dates must be valid, and complete fees require a positive total cost. Unknown values remain unknown. An invalid review aborts rather than silently approving a row.

```powershell
.venv\Scripts\python.exe -m pipeline.build --verifications .local/broker-review.xlsx
```

Check the report before publishing the new snapshot. Review exact unit identity, area and precise coordinates as well as eligibility and cost. `evidence` should identify a shareable source/document and what it establishes; keep confidential evidence outside public Git. Reviewers supply an expiry date, and expired approvals automatically fail. Availability is a separate status: the checkbox accepts only explicitly confirmed records checked within 30 days. Without the checkbox, historical unconfirmed records can qualify under the demo assumptions. Set `eligibility_policy` to `strict` in the build config and rebuild to require current complete verification instead.

Current import: 713 raw Crexi rows → 708 accepted records and 5 quarantined rows; 244 parsed rents, 70 cached address coordinates, 269 missing counties, zero verification records, and 37,430 deduplicated restaurant observations. Original card rents and sizes are joined by provider listing ID. A unique normalized-address match to the prepared workbook is a labeled fallback. Conflicting values are not guessed. Total building area and legacy `Total_Rent` are not treated as available unit size or complete monthly cost. The wide export contains no rent or coordinates; those come from the workbooks and cache.

Missing counties remain labeled. Current availability is not checked automatically. Source hashes, policies, collection period, quarantine reasons and coverage counts are embedded in every snapshot. CSV hashes normalize CRLF to LF; Excel hashes use original binary bytes. Builds do not refresh collection or verification dates. ZIP-center substitution is disabled; approximate coordinates are never silently substituted.

### Optional county demographics

Current Census requests require an API key. Request a free key from [Census](https://api.census.gov/data/key_signup.html), keep it in your environment, then run:

```powershell
$env:CENSUS_API_KEY = 'your-key'
.venv\Scripts\python.exe -m pipeline.census --year 2024 --output .local/acs-2024.json
.venv\Scripts\python.exe -m pipeline.build --areas .local/acs-2024.json
```

Use the same `--areas` and `--verifications` inputs on subsequent rebuilds; omitting them builds the baseline with the pinned demo policy. The Census adapter uses ACS 5-year **county** population, median household income, broad Asian population share, and published margins of error. It rejects negative sentinel estimates. These are not neighborhood footfall or cuisine demand. Without aggregates, affected optional features receive a neutral score. The original IPUMS sample is not used as population evidence because it lacks person weights and contains income sentinel values.

No live scraping, licensed feed, scheduled freshness guarantee, Prefect, dbt or Power BI is claimed. The manually triggered GitHub data workflow produces a review artifact; it does not automatically publish unchecked data. Public visibility alone does not establish redistribution rights; confirm original provider and purchased-data terms before distributing the raw data to a client.

## Scoring

Eligibility is checked **before** scoring. The demo assumes existence and restaurant suitability while respecting explicit negative evidence. Reject missing usable advertised rent/size, coordinates or source links. Budget applies to a labeled estimate, not a verified total cost. Also apply offered size overlap, county, reported parking and availability filters. Fewer than ten matching sites means fewer than ten results.

Default weights follow the client's final presentation: site 40%, location 40%, competition 20%. Site gives equal weight to estimated monthly budget headroom and size compatibility (100 for a valid overlapping offered range). Location weights household income/population/optional Asian share at 30/40/30. Competition weights observed ZIP restaurant count/same-cuisine count/prepared restaurant price midpoint at 30/50/20. Fewer observed competitors and higher prepared price values score higher; this explicit heuristic may not fit every business concept. The prepared price midpoint is not a verified menu quote.

Optional ethnicity context is disabled by default and receives neutral 50. It uses broad Asian share, not ethnicity-specific demand. Other missing optional values and constant reference columns also receive 50; coverage is reported separately as a percentage. Percentile scaling uses the entire versioned dataset's 10th and 90th percentiles, independent of user county filters. Deterministic ties use listing ID. No premature county/ZIP pruning removes possible top-ranked sites. Fit is a comparative heuristic, not a probability of business success.

## Check the implementation

```powershell
.venv\Scripts\python.exe -m ruff check backend pipeline migrations tests scripts
.venv\Scripts\python.exe -m pytest -q
pnpm --dir frontend test
pnpm --dir frontend build
pnpm --dir frontend exec playwright install chromium
# Keep the API on port 8000 running for this command:
pnpm --dir frontend test:e2e
.venv\Scripts\python.exe scripts/benchmark.py
```

For PostgreSQL integration tests use a separate test database:

```powershell
$env:DATABASE_URL = 'postgresql+psycopg://USER:PASSWORD@HOST:5432/lease_test'
$env:TEST_DATABASE_URL = $env:DATABASE_URL
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m backend.storage
.venv\Scripts\python.exe -m pytest -q
```

The PostgreSQL test inserts and deletes a test snapshot; never point it at a production database. GitHub Actions supplies an isolated PostgreSQL 17 service, rebuilds the source data, checks reproducibility, runs API/UI/browser tests, and builds/smoke-tests the container. Browser ranking fixtures are intercepted test responses, never included in the deployed dataset. Exact Python pins and the pnpm lockfile are committed for reproducibility; `requirements/*.in` and `scripts/lock_requirements.py` describe the update process.

Local benchmark results are recorded in [docs/benchmark.json](docs/benchmark.json). They describe a warm local API and real nonempty demo rankings, not Render performance, cold starts or production reliability.

## SWE learning path

1. Trace `Search` in `backend/schemas.py` through `/api/search`, the pure scorer, and React state. Learn HTTP status codes, validation and OpenAPI.
2. Change a scoring assumption and add a behavior test. Learn deterministic functions, boundaries, missingness and regression testing.
3. Follow `pipeline/build.py` from raw observations to validated contracts and hashes. Learn joins, stable identifiers, quarantine and reproducibility.
4. Run migrations and PostgreSQL tests, then simulate an unavailable DB. Learn transactions, immutable versions, connection pooling and failure behavior.
5. Modify the UI, run Vitest and Playwright, then inspect the production build. Learn TypeScript, React state, accessible inputs and integration testing.
6. Follow the Docker stages and CI workflow. Deploy to Render, inspect logs and measure that instance before adding a resume performance claim.

After deployment, a defensible description is: “Built a React/TypeScript and FastAPI restaurant-site research demo with PostgreSQL versioned datasets, reproducible validated imports, explainable ranking, synchronized maps, Excel exports and automated API/browser tests.” Do not claim nationwide inventory, live listings, ML, traffic prediction, measured business outcomes or remotely passing CI until demonstrated.
