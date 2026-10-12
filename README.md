# AI Engineering Knowledge Assistant

Production-oriented FastAPI application for grounded AI-engineering answers. Curators upload TXT, text PDF, and DOCX material; the worker parses and stages it; a curator explicitly approves it; students can then ask questions with inspectable sources.

## What is implemented

- FastAPI web/API and a restrained white, responsive, keyboard-accessible UI.
- Supabase PostgreSQL metadata, private Supabase Storage, Qdrant Cloud retrieval, Supabase Auth verification, and OpenAI-compatible answer/embedding adapters.
- Durable worker jobs, leases, retry state, SHA-256 duplicate protection, document lifecycle controls, publication gating, explicit approval, and source-only retrieval.
- TXT/PDF/DOCX parsing, OCR-required classification, source locations, Q/A validation, bounded token-aware chunks, citations, rate limits, CSRF-protected signed sessions, roles, migrations, Docker, Render profiles, fixtures, and an evaluation runner.

The only supported production data stores are PostgreSQL, private object storage, and Qdrant. No document or vector data is kept on the Render filesystem.

## Before running

1. Copy `.env.example` to `.env` and add the values from your Supabase, Qdrant, and LLM provider accounts. Do not commit `.env`.
2. Create a **private** Supabase Storage bucket named by `SUPABASE_STORAGE_BUCKET`.
3. Use Supabase’s transaction/session pooler URL for `DATABASE_URL` when Render needs IPv4.
4. Apply the migration once as a release action—not from web or worker startup:

   ```bash
   alembic upgrade head
   ```

5. Create the first server-managed curator after inviting them in Supabase Auth:

   ```bash
   python -m app.operator bootstrap-curator --auth-user-id YOUR_SUPABASE_USER_UUID --email curator@example.com
   ```

## Local development

Start local PostgreSQL and Qdrant, while keeping Supabase Storage/Auth and the selected LLM configured externally:

```bash
docker compose up -d
cp .env.example .env
# Set DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/ai_engineering
alembic upgrade head
uvicorn app.main:app --reload
```

In the low-cost/staging profile set `INGESTION_RUNNER=embedded` only if a single web process actually runs the runner. The included production Render manifest uses `INGESTION_RUNNER=separate` and `python -m app.worker`; do not enable both runners against the same queue.

The sign-in dialog accepts a Supabase access token while you decide on the final hosted Supabase sign-in/redirect screen. The server validates the token with Supabase and stores only a signed HttpOnly application session cookie; it never trusts client-controlled roles.

## Deploy to Render

Use `render.yaml` for the paid always-on web-plus-worker production profile. `render.staging.yaml` is a low-cost single-web-service starting profile and cannot promise background processing while Render sleeps.

Set these secret environment variables in Render: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_SECRET_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `LLM_API_KEY`, and `SESSION_SECRET`. Select a specific production `LLM_MODEL`; `openrouter/free` is restricted to development/testing unless deliberately enabled with `ALLOW_FREE_ROUTER_IN_PRODUCTION=true`. This is not an SLA-backed configuration.

Deployment order: run migration → deploy web → deploy worker → bootstrap curator → upload/review/approve the five documents → perform a cited question/append/restart check → run live evaluation → perform restore drill.

## Operations

- `GET /health/live` is public and deliberately reveals no dependencies.
- `GET /api/v1/operator/readiness` is curator-only and reports sanitised dependency status.
- Failed documents retain their error state for review. Scanned PDFs become `OCR_REQUIRED`; OCR is intentionally not automatic.
- A delete immediately makes a document unavailable, then queues idempotent vector/storage cleanup.
- Reindex work requires the `maintenance-lock` command so uploads/approval/lifecycle writes are blocked while existing approved sources stay queryable.

Backups are a launch prerequisite, not something this repository can perform without a destination: configure managed PostgreSQL backup/logical exports, private-object export or versioned backup, and retain the profile metadata. Vectors can be regenerated from canonical passages. Choose backup destination, schedule, retention, RPO/RTO, then prove the plan with a staging restore. Until that is done, production launch is blocked.

## Tests and evaluations

```bash
pytest -q -p no:rerunfailures
ruff format --check app tests evaluations
ruff check app tests evaluations
python -m evaluations.run --dataset dev --mode offline
python -m evaluations.run --dataset dev --mode retrieval
python -m evaluations.run --dataset test --mode end-to-end
python -m evaluations.compare --baseline path/to/baseline.json --candidate path/to/candidate.json
```

`retrieval` and `end-to-end` intentionally require `EVALUATION_LIVE_ENABLED=true`; configure isolated evaluation database records, object prefix, and Qdrant collection first. Offline output proves deterministic fixture structure only—it is not a model-quality or provider-availability claim. The fixtures have 30 development cases and 20 held-out cases split by question family.

## Current verification boundary

The repository includes deterministic parser/settings/UI-contract checks and an offline evaluation run. Live storage, Qdrant, Supabase authentication, answer-model behavior, Render deployment, browser screenshots, and backup restore require the provider accounts/credentials and are intentionally not claimed as verified yet.
