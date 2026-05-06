# Demand Planning Agent Runbook

## Project Overview

This project automates a monthly demand collection cycle for distributors:

1. Generate distributor-specific recommendations.
2. Build and send demand request emails with `DEMAND.xlsx` attached.
3. Wait for distributor replies by email.
4. Parse reply text or Excel attachments.
5. Save parsed demand into PostgreSQL.
6. Publish reply events to RedPanda.
7. Signal a Temporal workflow to validate and persist confirmed demand.
8. Expose dashboards and inspection UIs through FastAPI, Temporal UI, RedPanda Console, Inngest, and Metabase.

## What Actually Exists In This Repo

The repo does **not** match some of the file names in the requested inspection list.

Important mismatches:

- `pipeline.py` is missing.
- `signal_reply.py` is missing.
- `app/workflows/*.py` source files are missing.
- `app/events/producer.py` and `app/events/consumer.py` are missing.
- `app/agents/agent_registry.py` and `app/agents/agent_logger.py` are missing as source files.
- Several names appear only as stale `__pycache__` artifacts, not real Python sources.

The current live code uses these files instead:

- API entrypoint: `app/main.py`
- Poller / reply loop: `run_pipeline_service.py`
- Workflow definition: `app/temporal/workflow.py`
- Workflow activities: `app/temporal/activities.py`
- Workflow worker: `app/temporal/worker.py`
- Temporal client helper: `app/temporal/client.py`
- Event producer: `app/events/producers.py`
- Event consumer: `app/events/consumers.py`
- Email reader: `read_replies.py`
- Email processor: `process_replies.py`
- Email sender: `app/services/send_demand_email_service.py`
- Parsed reply persistence: `save_to_postgres.py`

## Architecture Diagram

```text
Distributor List
    |
    v
FastAPI /agent/cycle/start
    |
    +--> start Temporal workflow per distributor
    |
    +--> build recommendations
    |
    +--> send demand email + attach DEMAND.xlsx
    |
    v
Distributor replies by email
    |
    v
run_pipeline_service.py (gmail poller)
    |
    +--> read_replies.py
    +--> reply_parser_service.py
    +--> attachment_parser_service.py
    +--> save_to_postgres.py
    +--> app/events/producers.py -> RedPanda topic ReplyReceived
    |
    v
RedPanda consumer thread inside run_pipeline_service.py
    |
    v
Temporal workflow signal
    |
    v
app/temporal/workflow.py
    |
    +--> validate_reply_activity
    +--> write_confirmed_qty_activity
    +--> send_confirmation_email_activity
    +--> emit_demand_confirmed_activity
    |
    v
PostgreSQL confirmed_demands
    |
    v
Metabase dashboard / SQL inspection
```

## Main Components

### FastAPI

`app/main.py` creates the API server. It:

- initializes `confirmed_demands` on startup
- serves `/health`
- serves `/send-test`
- serves `/send-bulk`
- mounts `/agent/*`
- mounts `/graph/*`
- mounts `/recommendations/*`
- mounts `/reply-validation/*`
- mounts `/webhook/reply`
- registers Inngest at `/api/inngest`

### PostgreSQL

Stores:

- schema and seed data from `db/postgres/demand_planning.sql`
- distributor and SKU master data
- `parsed_replies`
- `parsed_reply_items`
- `confirmed_demands`
- `recommended_products`

### FalkorDB

Graph DB used for recommendation lookup. `app/repositories/graph_repository.py` queries it to fetch collaborative-filtering-style product recommendations.

### RedPanda

Event bus used for:

- `ReplyReceived`
- `DemandConfirmed`

Producer: `app/events/producers.py`  
Consumer: `app/events/consumers.py`

### Temporal

Durable workflow engine used to wait for replies and continue the demand-confirmation flow.

Main files:

- `app/temporal/workflow.py`
- `app/temporal/activities.py`
- `app/temporal/worker.py`
- `app/temporal/client.py`

### Metabase

Dashboard UI. It is intended to read from PostgreSQL tables like:

- `parsed_replies`
- `parsed_reply_items`
- `confirmed_demands`

### Inngest

Present. It exposes:

- monthly cron trigger
- manual event trigger `demand/cycle.start`

Current implementation only calls `/send-bulk`; it does not start Temporal workflows or process replies by itself.

### `pipeline.py`

`pipeline.py` does **not** exist in this repo.

The nearest current equivalent is `run_pipeline_service.py`, which:

- polls Gmail
- parses replies
- saves parsed data
- emits `ReplyReceived`
- signals / starts Temporal workflows

### `worker.py`

Current worker file is `app/temporal/worker.py`.

It registers:

- `DemandPlanningWorkflow`
- `fetch_context_activity`
- `validate_reply_activity`
- `write_confirmed_qty_activity`
- `send_confirmation_email_activity`
- `emit_demand_confirmed_activity`

### `client.py`

Current client file is `app/temporal/client.py`.

It only creates a Temporal client connection.

### `signal_reply.py`

Missing as a source file.

Equivalent runtime behavior exists in:

- `run_pipeline_service.py`
- `app/controllers/postal_webhook_controller.py`

Both can signal Temporal workflows after a reply arrives.

## Required Environment Variables

Expected by `app/core/config.py` and helper scripts:

```env
POSTGRES_HOST
POSTGRES_PORT
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD

FALKOR_HOST
FALKOR_PORT
FALKOR_GRAPH

EMAIL_ADDRESS
EMAIL_APP_PASSWORD
SMTP_SERVER
SMTP_PORT

IMAP_SERVER
IMAP_PORT

REDPANDA_BROKER
TEMPORAL_HOST
```

Also present in `.env`:

- `IMAP_HOST`
- `MAIL_USERNAME`
- `MAIL_PASSWORD`
- `ATTACHMENT_DIR`

## Docker Services

Defined in `docker-compose.yml`:

- `postgres`
- `falkordb`
- `redpanda`
- `redpanda_console`
- `temporal`
- `temporal_ui`
- `fastapi`
- `inngest`
- `temporal_worker`
- `gmail_poller`
- `metabase`

## Full Run Commands

## Recommended Run Path

This repo is meant to be run with Docker Compose. That is the correct full-system path.

### 1. Start the full stack

```powershell
docker compose up --build
```

### 2. Initialize PostgreSQL schema and seed data

Open a second terminal in the repo root:

```powershell
Get-Content db\postgres\demand_planning.sql | docker exec -i demand_postgres psql -U postgres -d demand_planning
Get-Content db\postgres\seed_data.sql | docker exec -i demand_postgres psql -U postgres -d demand_planning
python db\postgres\seed_recommended_products.py
```

### 3. Seed FalkorDB graph data

Open another terminal:

```powershell
python db\falkordb\falkordb_seed.py
```

### 4. Open the main API

```text
http://localhost:8000/docs
```

### 5. Start the live demand cycle

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/agent/cycle/start
```

This:

- starts one Temporal workflow per distributor
- sends recommendation emails with `DEMAND.xlsx`

### 6. Wait for distributor reply or force one inbox pass

Automatic path:

- `gmail_poller` reads Gmail every `POLL_INTERVAL_SECONDS`

Manual one-pass trigger:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/agent/replies/process-once
```

### 7. Track the whole system from one terminal

```powershell
docker compose logs -f
```

Or only the core pipeline services:

```powershell
docker compose logs -f fastapi gmail_poller temporal_worker inngest
```

## Manual Non-Docker Equivalents

These are useful for understanding, but Docker Compose already runs most of them.

### Start Temporal server

Handled by Docker:

```powershell
docker compose up temporal
```

### Start Temporal worker

Handled by Docker, but direct equivalent is:

```powershell
python -m app.temporal.worker
```

### Start workflow client

There is **no standalone workflow client runner** in the current repo.

Equivalent start paths:

- `POST /agent/cycle/start`
- Temporal auto-start inside `run_pipeline_service.py`

### Send reply signal

There is **no `signal_reply.py` file**.

Equivalent signal paths:

- reply arrives via `run_pipeline_service.py`
- or webhook `POST /webhook/reply`

### Run RedPanda consumer

Two possible paths:

Current main path:

- consumer thread is started inside `run_pipeline_service.py`

Legacy standalone path:

```powershell
python run_consumer.py
```

## How To Test Email

### Send one test email

```powershell
Invoke-RestMethod http://localhost:8000/send-test
```

### Send the distributor batch

```powershell
Invoke-RestMethod http://localhost:8000/send-bulk
```

Or use the preferred orchestration endpoint:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/agent/cycle/start
```

## How To Test Temporal Workflow

### Start workflow via API

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/agent/cycle/start
```

### Open Temporal UI

```text
http://localhost:8088
```

Look for workflow IDs like:

```text
demand-D01-cycle
demand-D02-cycle
...
```

## How To Check Database Records

### Open psql inside Docker

```powershell
docker exec -it demand_postgres psql -U postgres -d demand_planning
```

Then query:

```sql
SELECT * FROM parsed_replies ORDER BY id DESC LIMIT 20;
SELECT * FROM parsed_reply_items ORDER BY id DESC LIMIT 20;
SELECT * FROM confirmed_demands ORDER BY id DESC LIMIT 20;
SELECT * FROM recommended_products ORDER BY id DESC LIMIT 20;
SELECT * FROM skus ORDER BY sku_code;
```

## How To Check RedPanda Events

### Open RedPanda Console

```text
http://localhost:8080
```

Relevant topics:

- `ReplyReceived`
- `DemandConfirmed`

### Or inspect from terminal

```powershell
docker compose logs -f redpanda redpanda_console
```

## How To Check Metabase

### Open Metabase UI

```text
http://localhost:3002
```

If it starts successfully, configure PostgreSQL from the browser.

Use:

- Host: `postgres`
- Port: `5432`
- Database: `demand_planning`
- Username: `postgres`
- Password: `postgres`

## How The Complete Demand Cycle Works

1. Distributor list comes from `app/data/distributor_data.py`.
2. Recommendations come from `app/services/sku_recommendation_service.py`.
3. Email payload is built by `app/services/build_demand_email_service.py`.
4. Email is sent by `app/services/send_demand_email_service.py`.
5. Temporal workflow is started by `/agent/cycle/start`.
6. Workflow waits in `app/temporal/workflow.py` for a reply signal.
7. Distributor replies by email.
8. `run_pipeline_service.py` reads Gmail using `read_replies.py`.
9. Reply text is parsed by `app/services/reply_parser_service.py`.
10. Excel attachment is parsed by `app/services/attachment_parser_service.py`.
11. Parsed reply is stored by `save_to_postgres.py`.
12. `ReplyReceived` event is published by `app/events/producers.py`.
13. Consumer thread inside `run_pipeline_service.py` reads the event.
14. Temporal workflow is signaled with `parsed_reply_id`.
15. `validate_reply_activity` checks parsed rows.
16. `write_confirmed_qty_activity` writes `confirmed_demands`.
17. Weekly split is generated very simply as `qty // 4` inside `write_confirmed_qty_activity`.
18. `send_confirmation_email_activity` sends confirmation email.
19. `emit_demand_confirmed_activity` publishes `DemandConfirmed`.

## How To Know Each Step Worked

### Email sent

- Terminal: `fastapi` logs or `/send-bulk` API response
- Temporal UI: not visible yet
- RedPanda: not published at this stage
- PostgreSQL: no write for send step

### Workflow started

- Terminal: response from `/agent/cycle/start`
- Temporal UI: workflow `demand-Dxx-cycle`
- RedPanda: not relevant
- PostgreSQL: no direct row yet

### Reply read from Gmail

- Terminal: `gmail_poller` logs show `Found N new reply(s)`
- Temporal UI: workflow still waiting
- RedPanda: not yet
- PostgreSQL: not yet until save happens

### Reply parsed and stored

- Terminal: `gmail_poller` shows parsed output
- Temporal UI: still waiting until signal delivered
- RedPanda: `ReplyReceived` emitted
- PostgreSQL:
  - `parsed_replies`
  - `parsed_reply_items`

### Workflow signaled

- Terminal: `gmail_poller` or webhook logs show signal sent
- Temporal UI: workflow leaves waiting state
- RedPanda: `ReplyReceived`
- PostgreSQL: parsed rows already present

### Reply validated

- Terminal: `temporal_worker` logs
- Temporal UI: activity success
- RedPanda: still only `ReplyReceived` at this point
- PostgreSQL: no new row until write activity completes

### Weekly plan / confirmed demand written

- Terminal: `temporal_worker` logs
- Temporal UI: `write_confirmed_qty_activity`
- RedPanda: `DemandConfirmed` after write
- PostgreSQL: `confirmed_demands`

### Confirmation email sent

- Terminal: `temporal_worker` shows `[Confirmation] Email sent`
- Temporal UI: `send_confirmation_email_activity`
- RedPanda: not required
- PostgreSQL: no dedicated email audit table

### Final event published

- Terminal: `temporal_worker` or `redpanda` logs
- Temporal UI: workflow completed
- RedPanda: `DemandConfirmed`
- PostgreSQL: `confirmed_demands` should already exist

## Is `pipeline.py` Fully Connected?

No. `pipeline.py` is not present in this repo.

The currently connected runtime entrypoint is `run_pipeline_service.py`.

Even `run_pipeline_service.py` is only one part of the system:

- it does not start PostgreSQL
- it does not start FalkorDB
- it does not start Temporal server
- it does not start FastAPI
- it assumes those services are already running

So `python pipeline.py` cannot be the correct full-project startup sequence here.

## Exact Correct Run Sequence

1. `docker compose up --build`
2. initialize Postgres schema
3. seed Postgres data
4. seed `recommended_products`
5. seed FalkorDB graph
6. open `http://localhost:8000/docs`
7. call `POST /agent/cycle/start`
8. send a distributor email reply
9. wait for `gmail_poller` or call `POST /agent/replies/process-once`
10. inspect Temporal UI, RedPanda Console, PostgreSQL, and Metabase

## Current Blockers

### 1. Missing `pipeline.py`

Blocker:

- documentation or expectations reference `pipeline.py`
- actual file is missing

Fix:

- use `run_pipeline_service.py` as the real poller entrypoint
- update docs and commands to reference that file

### 2. Some requested architecture files do not exist

Blocker:

- `app/workflows/*.py`, `signal_reply.py`, `app/events/producer.py`, `app/events/consumer.py`, `app/agents/*.py` source files are missing

Fix:

- document the real files currently used
- remove stale references from any older docs

### 3. Email sending fails if `EMAIL_ADDRESS` or `EMAIL_APP_PASSWORD` is missing

Blocker:

- SMTP login cannot happen

Fix:

- set `.env` values:

```env
EMAIL_ADDRESS=your@gmail.com
EMAIL_APP_PASSWORD=your_gmail_app_password
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=465
```

### 4. Gmail reply reading fails if IMAP credentials are missing

Blocker:

- `read_replies.py` raises if `EMAIL_ADDRESS` or `EMAIL_APP_PASSWORD` is missing

Fix:

- set:

```env
IMAP_SERVER=imap.gmail.com
IMAP_PORT=993
EMAIL_ADDRESS=your@gmail.com
EMAIL_APP_PASSWORD=your_gmail_app_password
```

### 5. SKU11 / SKU12 or other new SKU codes may be missing from `skus`

Blocker:

- `db/postgres/seed_data.sql` seeds only `SKU01` through `SKU10`
- new recommendation SKUs may not exist in Postgres

Fix:

- add missing SKUs to `skus`
- add mappings in `distributor_skus` if needed
- re-run SQL seed or create insert statements

Example:

```sql
INSERT INTO skus (sku_code, sku_name, category, unit_of_measure, is_active)
VALUES ('SKU11', 'NEW SKU 11', 'CATEGORY', 'units', TRUE)
ON CONFLICT (sku_code) DO NOTHING;
```

### 6. FalkorDB graph seed uses a different graph name than app config

Blocker:

- app default graph is `demand_graph`
- `db/falkordb/falkordb_seed.py` seeds `demand_planning_graph`

Fix:

- make them the same
- easiest fix is to edit `GRAPH_NAME` in `db/falkordb/falkordb_seed.py` to `demand_graph`
- then re-run:

```powershell
python db\falkordb\falkordb_seed.py
```

### 7. Metabase may crash if database `metabase` does not exist

Blocker:

- compose sets:
  - `MB_DB_DBNAME=metabase`
- but Postgres service only creates `demand_planning`

Fix:

- create the `metabase` database manually:

```powershell
docker exec -it demand_postgres psql -U postgres -c "CREATE DATABASE metabase;"
```

Alternative:

- reconfigure Metabase to use another application DB, but separate DB is cleaner

### 8. Temporal worker fails if Temporal server is not running

Blocker:

- `app/temporal/worker.py` must connect to `TEMPORAL_HOST`

Fix:

- start `temporal` first via Docker Compose
- verify:

```powershell
docker compose ps
docker compose logs -f temporal temporal_worker
```

### 9. RedPanda consumer fails if broker is not running

Blocker:

- `consume_reply_received()` depends on broker availability

Fix:

- start `redpanda`
- verify:

```powershell
docker compose logs -f redpanda redpanda_console
```

### 10. Postal webhook path is incomplete

Blocker:

- `app/controllers/postal_webhook_controller.py` calls `parse_reply()`
- but `parse_reply()` does not save to DB and does not return `parsed_reply_id`
- webhook then tries to use `parsed_reply_id` anyway

Fix:

- persist webhook replies with `save_to_postgres.save_parsed_reply()`
- then signal Temporal with the real saved ID

### 11. Legacy `run_consumer.py` uses a different workflow ID convention

Blocker:

- `run_consumer.py` uses `demand-{distributor_id}-{parsed_reply_id}`
- current system uses `demand-{distributor_id}-cycle`

Fix:

- do not use `run_consumer.py` for the current main path
- if you keep it, align it with `app/temporal/workflow_ids.py`

### 12. Recommendations depend on both Postgres and FalkorDB seed data

Blocker:

- if `recommended_products` is empty or Falkor graph is not seeded, recommendation quality drops

Fix:

- run:

```powershell
python db\postgres\seed_recommended_products.py
python db\falkordb\falkordb_seed.py
```

## Summary

- `pipeline.py` is **not fully connected** because it does not exist here.
- the current full-system run path is **Docker Compose + FastAPI + Temporal + Gmail poller**
- the exact correct run sequence is:
  - start Compose
  - initialize Postgres
  - seed `recommended_products`
  - seed FalkorDB
  - trigger `/agent/cycle/start`
  - reply by email
  - watch `gmail_poller`, `temporal_worker`, RedPanda, PostgreSQL, and Metabase
