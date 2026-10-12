# AI Engineering Knowledge Chatbot — Production Requirements for Codex

Version: 2.0 | Date: 11 October 2026 | Scope: production application, initially five documents

## 1. Implementation mandate and priorities

Build a maintainable production application that answers AI engineering questions from a curated, growing document knowledge base. Curators upload TXT, text-based PDF, and DOCX files; students ask questions and receive grounded answers with source citations. Process new files incrementally without rebuilding or deleting previously indexed content.

The frontend must be minimal, professional, and predominantly white. Follow the precise visual specification in section 9. The primary experience is asking a question and reading a clear answer; document management is secondary and role-restricted.

This version supersedes the earlier demo specification: do not use SQLite or local files for hosted durable data, do not require a local embedding model on Render, and do not use shared access tokens as the production user-authentication system. Implement PostgreSQL metadata/jobs, private object storage, authentication/roles, provider adapters, durable indexing, operational checks, and pipeline evaluations.

Implement the code, deployment configuration, tests, sample fixtures, and documentation. Credentials and approved deployment plans may be supplied later: complete independent work without inventing secrets or claiming unperformed live verification. Do not deploy or purchase resources unless separately requested. Do not ingest unrelated personal files. Inspect any actual repository instructions first; this document does not override its security requirements.

Priorities: working document-to-answer flow, source integrity, accessible UI, recoverable ingestion, configurable providers, and clear operational handoff. Avoid speculative infrastructure and ornamental interface features.

## 2. Fixed architecture and deployment profiles

| Component | Selected implementation | Requirement |
|---|---|---|
| Backend | Python 3.11+, FastAPI | Serve UI and API from same origin |
| Frontend | Semantic HTML, CSS tokens, lightweight JavaScript | White, professional, responsive; no separate frontend hosting/build required |
| Hosting | Render Docker web service | Stateless except bounded temporary parsing files |
| Worker | Render background worker, same repository/image | Separate process; durable PostgreSQL job queue |
| Metadata and canonical text | Supabase PostgreSQL | SQLAlchemy + Alembic migrations; source of truth |
| Original documents | Private Supabase Storage bucket | Storage adapter; generated object keys |
| Vector search | Qdrant Cloud | One physical collection per immutable index profile |
| Default embeddings | Qdrant Cloud Inference, `sentence-transformers/all-minilm-l6-v2` | Hosted inference; 384-dimensional model; avoid PyTorch in deployed base image |
| Answer model | Configurable OpenAI-compatible API, initially OpenRouter | Specific model configurable; record actual returned model |
| Authentication | Supabase Auth | Invited users; server-checked student/curator roles |
| Evaluations | pytest + evaluation runner | Offline, retrieval, and real generation checks separately |

The production hosting profile uses an always-on Render web service and background worker. This profile requires paid hosting resources; do not describe it as an entirely free deployment. Supabase/Qdrant entry-tier quotas can be used initially if appropriate to measured usage. The application must support later upgrades without code rewrites.

Also supply a low-cost development/staging profile: free Render web service, external durable PostgreSQL/storage, and an embedded ingestion runner in the single web-service process. It must use the same durable queue/leases and resume jobs after wake-up; it cannot promise unattended progress while the service sleeps. This is a hosting profile, not a different data model. Prevent both embedded and separate runners from being enabled accidentally. A dedicated free Render background worker is not assumed available.

Use `openrouter/free` only as an explicit development/testing option. Production should select a specific model with suitable quota/availability; its name and budget are operator configuration. No automatic paid-model fallback. Free services/models can be used for initial tests, but passing tests does not establish availability or an SLA.

No Render persistent disk is required: application records are in PostgreSQL; original files in private storage; vectors in Qdrant. Temporary files are deleted after parsing. API and worker do not share a local filesystem. Use a Supabase session-pooler connection string where IPv4 compatibility is needed; use small connection pools and TLS.

## 3. Provider boundaries and contracts

Services depend on typed domain contracts and injected adapters, not vendor SDK types. Only adapter modules import provider SDK objects. Factories select implementations from validated environment settings; no vendor conditionals inside ingestion/retrieval/answer services.

```mermaid
flowchart TD
    UI["White chat and curator UI"] --> API["FastAPI on Render"]
    API --> DB["Supabase PostgreSQL"]
    API --> FS["Private document storage"]
    API --> QA["Retrieval and answer services"]
    QA --> Q["Qdrant and embedding adapter"]
    QA --> L["Configurable LLM adapter"]
    W["Ingestion worker"] --> DB
    W --> FS
    W --> Q
```

Required ports: MetadataRepository, DocumentStorage, RetrievalIndex, EmbeddingStrategy, LLMProvider, IdentityProvider. Provide production adapters and in-memory/fake adapters for contract tests.

Important: Qdrant Cloud Inference performs embedding during upsert/query; do not invent a separate endpoint that returns arbitrary embedding arrays. Support a provider-neutral representation union:

```python
# Domain objects; neither contains Qdrant SDK types.
VectorInput = DenseVector | InferenceText
# DenseVector: values + embedding profile fingerprint.
# InferenceText: text + embedding profile fingerprint.

class EmbeddingStrategy(Protocol):
    def profile(self) -> EmbeddingProfile: ...
    async def prepare_documents(self, texts: list[str]) -> list[VectorInput]: ...
    async def prepare_query(self, text: str) -> VectorInput: ...

class RetrievalIndex(Protocol):
    async def ensure_index(self, profile: IndexProfile) -> None: ...
    async def upsert(self, index_name: str, points: list[IndexPoint]) -> None: ...
    async def search(self, index_name: str, query: VectorInput,
                     limit: int, filters: SearchFilters) -> list[SearchHit]: ...
    async def delete_document(self, index_name: str, document_id: str) -> None: ...
    async def health(self) -> HealthResult: ...

class LLMProvider(Protocol):
    async def generate(self, request: GenerationRequest) -> GenerationResult: ...
```

The Qdrant adapter converts InferenceText into its supported Document object with cloud inference enabled and a profile-to-model mapping. An external/local embedding strategy returns DenseVector instead. Implement the Qdrant-cloud path and an OpenAI-compatible HTTP embedding strategy, so a later embedding switch has a working alternative. A local model strategy is optional and must not add large ML dependencies to the default deployment.

Validate compatibility between embedding strategy and index adapter at startup; a different vector provider may require DenseVector. Changing from Qdrant-hosted inference to another database requires an external/local embedding strategy and reindexing; not every combination is a configuration-only swap. Keep this limitation explicit.

Implement PostgreSQLMetadataRepository, SupabaseDocumentStorage, QdrantRetrievalIndex, QdrantCloudEmbeddingStrategy, OpenAICompatibleEmbeddingStrategy, OpenAICompatibleLLMProvider, and SupabaseIdentityProvider. Translate provider exceptions into stable application errors. LLM generation must work with ordinary chat completions without tool calling or JSON-schema capabilities. Streaming is optional, not a blocker.

## 4. Configuration contract

Commit a validated `.env.example` with placeholders and comments, never actual secrets. These are application variable names, not claims about vendor-specific naming.

```dotenv
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8000
PUBLIC_BASE_URL=http://localhost:8000
INGESTION_RUNNER=embedded
# Production: separate runner; Render worker invokes python -m app.worker.
TEMP_DIR=/tmp/ai-engineering

DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres
DB_POOL_SIZE=3
DB_MAX_OVERFLOW=2
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_PUBLISHABLE_KEY=
SUPABASE_SECRET_KEY=
SUPABASE_STORAGE_BUCKET=knowledge-documents
AUTH_PROVIDER=supabase
ALLOW_PUBLIC_SIGNUP=false
SAVE_CHAT_HISTORY=false

VECTOR_DB_PROVIDER=qdrant
QDRANT_URL=https://YOUR_CLUSTER_ENDPOINT
QDRANT_API_KEY=
QDRANT_COLLECTION_PREFIX=ai_engineering
QDRANT_TIMEOUT_SECONDS=20

EMBEDDING_PROVIDER=qdrant_cloud
EMBEDDING_MODEL=sentence-transformers/all-minilm-l6-v2
EMBEDDING_MODEL_REVISION=
EMBEDDING_DIMENSIONS=384
EMBEDDING_BATCH_SIZE=32
EMBEDDING_TOKENIZER_MODEL=sentence-transformers/all-MiniLM-L6-v2
# Used only for openai_compatible embedding strategy:
EMBEDDING_BASE_URL=
EMBEDDING_API_KEY=

LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=openrouter/free
LLM_API_KEY=
LLM_TEMPERATURE=0.1
LLM_MAX_OUTPUT_TOKENS=700
LLM_MAX_INPUT_TOKENS=4096
LLM_TIMEOUT_SECONDS=45
LLM_FREE_ONLY=true
ALLOW_FREE_ROUTER_IN_PRODUCTION=false

CHUNK_TARGET_TOKENS=180
CHUNK_OVERLAP_TOKENS=30
RETRIEVAL_CANDIDATE_K=20
RETRIEVAL_CONTEXT_K=5
RETRIEVAL_MIN_COSINE_SCORE=0.35
MAX_CONTEXT_CHARACTERS=6000
MAX_QUERY_CHARACTERS=2000
MAX_UPLOAD_MB=10
MAX_PDF_PAGES=200
MAX_EXTRACTED_CHARACTERS=1000000
WORKER_CONCURRENCY=1
JOB_MAX_ATTEMPTS=3
JOB_LEASE_SECONDS=120
PROVIDER_MAX_RETRIES=2
CHAT_REQUESTS_PER_USER_PER_MINUTE=10
LOG_LEVEL=INFO
```

Production template: APP_ENV=production, bind 0.0.0.0, honour Render's PORT, HTTPS PUBLIC_BASE_URL, INGESTION_RUNNER=separate, and an explicitly selected LLM model. Changing LLM_FREE_ONLY to false permits the configured paid model, not unspecified automatic fallbacks. If a free router is deliberately allowed in production, expose that reliability limitation in operator documentation; do not call it an SLA-backed setup.

Validate all limits, chunk overlap, providers, index compatibility, URLs, and secrets. In production reject missing identity/storage/database settings; do not silently fall back to SQLite, public buckets, fake models, or in-memory data. Liveness can remain healthy during a temporary provider outage, but protected readiness must report degraded dependencies. A similarity threshold is a tunable heuristic, not an answer-confidence percentage.

## 5. Document parsing, approval, and chunking

Accept TXT (UTF-8/BOM), PDF (pypdf), and DOCX (python-docx). Validate extension and signature; reject unsupported/legacy DOC, encrypted PDFs, invalid text, and excessive files/pages/extracted size. Bound DOCX ZIP expanded bytes and entry count before parsing; do not follow external relationships. Preserve paragraph/table order where practical, headings, newlines, and code text. PDF layout and diagrams can lose information: surface extraction warnings. Entirely image-only/scanned PDFs become OCR_REQUIRED; automatic OCR/image understanding is not included.

Preserve actual 1-based PDF page locations. DOCX citations use headings/paragraph/table positions, never invented page numbers. TXT uses heading/line locations where available. Store original bytes and canonical extracted text for reprocessing.

Upload content modes: general_document, curated_qa, questions_only. Recognise curated pairs only using Q:/A: or Question:/Answer: labels, supporting multiline answers. Reject incomplete blocks for curator correction; do not invent answers. General documents are references, not approved exact answers. Questions-only uploads create pending questions and no answer-source vectors.

Worker extracts/previews content and builds a staged index. Curator approves publication after reviewing extraction warnings and content; approval before completion may not bypass indexing. Document becomes READY only when approved and completely indexed. A separate approve action is required; no hidden automatic approval. Quarantined/unapproved/partial sources cannot answer student questions.

Use the embedding tokenizer to bound all prepared text including prefixes/special tokens. Default MiniLM has a short input limit; default target is 180 tokens with 30 overlap, checked against the active profile's declared/model-card limit. Download only tokenizer assets for hosted inference, not model weights. When a remote model's tokenizer/limit cannot be verified, refuse activation until configured; no silent truncation. Split by paragraphs/sections, then token-aware windows. Preserve full canonical text and source locations across chunks.

Short Q&A: index question plus answer together. Long Q&A: split answer, repeat a bounded question prefix, keep full approved answer as a canonical record. Long user queries receive a clear shortening request in v1. Changing the embedding/chunking profile requires reindexing.

## 6. Durable ingestion and document lifecycle

1. Validate upload and calculate SHA-256 server-side; filenames are display data only.
2. Create a uniquely reserved document/job record in PostgreSQL. A unique knowledge-base/file-hash constraint handles simultaneous duplicates. Return the existing record for identical bytes rather than making a duplicate corpus.
3. Store originals under server-generated keys in a private bucket, then commit the queued job. Handle upload failure with an explicit failed record. Queue only after storage succeeds. Implement a reconciliation task for abandoned reservations/orphan objects; never assume storage and SQL share a transaction.
4. Return 202 with document/job IDs. Worker claims eligible jobs with a transaction and row locks/SKIP LOCKED, releases transactions before external calls, renews durable leases, and bounds concurrency.
5. Extract, persist canonical passages transactionally, prepare embedding inputs in batches, and upsert deterministic point UUIDs derived from document/profile/ordinal. Retry cannot multiply passages or points.
6. Mark processing complete as AWAITING_APPROVAL; approved/fully indexed documents become READY. Record stages, progress, warnings, attempts, and timestamps.
7. Resume expired leases after crashes. Transient 429/5xx/timeouts use bounded exponential backoff/jitter and Retry-After; permanent parse/auth/configuration errors require intervention.

States: UPLOADING, QUEUED, PROCESSING, AWAITING_APPROVAL, READY, FAILED, OCR_REQUIRED, INACTIVE, DELETING, DELETED. Questions-only documents need zero vectors but require normal content review/publication semantics for pending questions.

PostgreSQL is the publication gate. Qdrant has no cross-service transaction: retrieval cross-checks READY/active/approved documents and profile IDs in SQL, even when partial/stale vectors remain. Over-retrieve/backfill within bounded limits to recover useful context after filtering. Never reset collections on startup.

New/changed files append as new records. Explicit replacement stages a new version; after indexing and approval, atomically activate the replacement and inactivate the old version in SQL. Failed replacements leave the old approved version usable. Record lineage and audit changes.

Curators can deactivate/reactivate eligible versions or request deletion. Deletion first makes material unavailable for retrieval, then a durable idempotent cleanup removes storage objects, canonical content, and vectors. Retain only minimal audit metadata where retention policy permits. UI explains deletion and requires confirmation. Define backup-retention/deletion implications in operator documentation; no invented compliance guarantee.

## 7. Canonical database records and vector contract

PostgreSQL migrations with foreign keys/constraints cover:

- memberships: authenticated Supabase user ID, student/curator role, active flag; no browser-controlled privilege assignment.
- documents: UUID, filename/type/hash, object key, content mode, lifecycle/approval/active fields, creator/approver, lineage, warnings/counts, timestamps.
- passages: UUID, document UUID, ordinal, full canonical text, QA association, source location, text hash, parser/chunker versions.
- curated_qa: question, full approved answer, optional topic/tags, document/source IDs.
- jobs: type, document/profile IDs, stage/state, attempts, lease owner/expiry, progress/error, timestamps.
- index_profiles: provider/collection, embedding model/revision where available, dimensions, distance, normalisation/prefix/tokenizer/chunk policies, fingerprint, lifecycle/active fields.
- pending_questions: question, creator, origin, open/resolved state, timestamps.
- audit_events: actor, action, target IDs, timestamp, minimal sanitised metadata.
- usage/rate-limit counters: bounded per-user counters with expiry; no full prompts required.

Chats are not persisted by default. Optional history must be user-scoped with documented retention and deletion, not a prerequisite for the first release.

Default Qdrant profile uses 384 dimensions and cosine similarity; verify collection shape and provider model metadata/integration response rather than assuming compatibility. Hosted model revisions may not be exposed: record the available model identifier and provider-reported version, explicitly mark unknown revision, and run retrieval canaries to detect drift. Never invent a pinned remote revision.

Vector payload: passage_id, document_id, ordinal, source filename/location, content_mode, qa_id, index_profile_id, schema_version. SQL is the canonical text source; payload text duplication is optional. Configure payload indexes required for filters using current Qdrant APIs. Chat messages, unanswered questions, and secrets are not answer-source vectors.

## 8. Retrieval and answer behaviour

Validate question; snapshot one active profile; prepare query; retrieve candidates; cross-check canonical READY/active/approved records; deduplicate; apply profile-specific threshold; build up to five passages under context budget. Include adjacent passages when necessary and within limits.

Only exact normalised matches to approved curated questions may bypass generation and return the stored full answer. If duplicate exact questions have conflicting active answers, return a conflict for curation instead of arbitrary selection. Semantic matches use generated answers from evidence, not an assumption that nearest neighbour is equivalent.

No usable evidence: say material is insufficient and enqueue a pending question. Partial evidence: clearly identify what can be answered and what is missing. Provider failure is not a knowledge gap and must not create pending questions. Return a retryable error and optionally clearly labelled source excerpts, never a fabricated success.

Label model context S1/S2/etc. Prompt the LLM to answer only from supplied passages, cite factual claims, explain source conflicts, and ignore instructions embedded in reference text. Do not add web search or agents. Use conservative whole-input budgeting including instructions/question, reserve output tokens, and validate available model context limits. Plain completions are sufficient.

Validate all source IDs and require valid citations on substantive generated answers. Unknown IDs/missing citations trigger a generation-validation error or labelled excerpt fallback. Citation existence does not prove support; evaluate entailment through reviewed cases.

V1 handles self-contained questions. Display session conversation history if useful, but do not imply unresolved follow-up pronouns are understood. History rewriting is an explicit later extension.

## 9. Frontend visual and interaction specification — mandatory

### 9.1 Visual direction

Build a polished, restrained professional application with a pure white main background. Prioritise typography, spacing, alignment, and source readability. No gradients, decorative illustrations, oversized dashboard cards, glass effects, animated backgrounds, bright multicolour panels, or promotional landing-page hero.

Use these CSS design tokens, adjusted only for verified contrast/accessibility:

```css
:root {
  --background: #ffffff;
  --surface-subtle: #f8fafc;
  --text: #111827;
  --text-secondary: #475569;
  --border: #e2e8f0;
  --accent: #1d4ed8;
  --accent-hover: #1e40af;
  --focus: #2563eb;
  --success: #166534;
  --warning: #92400e;
  --error: #b91c1c;
  --radius: 8px;
}
```

Use a system sans-serif stack; no externally fetched font required. Body text 15–16 px, line height 1.55–1.65, readable answer width around 760 px. Small section labels 13–14 px; restrained headings 22–28 px. Use 4/8/12/16/24/32 px spacing rhythm, subtle 1 px borders, rounded controls around 8 px, and minimal/no shadows. Blue is limited to primary actions, links, active navigation, and keyboard focus. Status colours have text labels and icons, never colour alone.

### 9.2 Layout

- Compact header around 64 px: text wordmark “AI Engineering”, discreet “Knowledge Assistant” subtitle where space permits, Chat/Knowledge Base navigation, account menu. Knowledge Base visible only to curators, with independent server authorisation.
- Chat uses a centred reading column; optional compact conversation navigation must not crowd it. Keep white space deliberate, not empty hero space. No permanent analytics sidebar.
- Empty chat: restrained title “Ask your AI engineering questions”, one sentence explaining document-grounded answers, and at most three example-question buttons. Examples must be labelled and aligned with real available content; do not imply the client's five documents are loaded before upload.
- Messages: user question in a subtle neutral container; assistant answer mainly on white with clear typographic hierarchy. Modest icons only where useful. Distinguish “Approved answer”, “Answer from documents”, and “Source excerpts” with understated text labels.
- Composer at bottom of reading column: multiline textarea, concise placeholder, send button with accessible label, Enter to send/Shift+Enter for newline. Disable only relevant controls while requests run. Ensure sticky positioning never obscures answer/source content or mobile keyboards.
- Source citations are clickable anchors/buttons that reveal filename, actual page/section, and excerpt in an accessible collapsible panel or drawer. Return focus when drawers close; no hover-only interactions.
- Knowledge Base uses a compact document table/list, single “Upload documents” action, counts, and status. Columns: filename, type, status, added date, actions. Mobile becomes readable stacked rows without horizontal page overflow.
- Upload panel: file picker/drag drop, supported formats/size note, content-mode selector, independent per-file progress, extraction-preview/review/approve controls. File picker remains keyboard accessible; drag-and-drop is optional.
- Curator pending questions appear in a secondary tab/section, not the student's home screen. Provider/debug configuration does not appear in ordinary student flows.

### 9.3 Required states and accessibility

Design sign-in, empty corpus, active chat, loading, insufficient evidence, conflicting evidence, provider error, upload progress, awaiting approval, READY, failed/OCR-required, session expiry, and access denied. Errors name the affected action and offer an appropriate retry/fix; do not expose stack traces. Success notices are quiet inline confirmations.

At 1440/1024/768/390 px widths, verify readable text, usable composer, and no horizontal page overflow. Use semantic buttons/forms/headings, visible focus, contrast meeting WCAG AA, labelled controls, accessible status announcements, keyboard-complete interactions, and reduced-motion support. Do not move focus/scroll unexpectedly while users read earlier messages. Render Markdown/code with a maintained sanitisation approach; raw source/model HTML never executes.

Frontend acceptance: predominantly white screenshots; consistent tokens and spacing; no decorative hero; one obvious primary action per view; citations and upload approval usable on mobile; all required states implemented. Capture representative screenshots through an available supported browser tool and inspect them; if unavailable, disclose the unperformed visual check rather than claiming it passed. Do not install unrelated browser infrastructure solely to make a screenshot claim.

## 10. API, identity, and security

Provide health/readiness, identity/session, chat, document upload/list/detail/preview/download, approval/retry/replacement/deactivation/deletion, pending-question resolution, and protected index/operator endpoints as needed. All list endpoints paginate. Chat returns answer, mode/status, citations, request_id, and actual model ID when available. Citations include source ID, document/passage IDs, filename, actual nullable page/section, and excerpt.

Stable error envelope: code, user_message, retryable, request_id. Use appropriate 401/403, 413, 415, 422, 429, and 503 statuses. Public liveness returns no dependency details; protected readiness identifies sanitised degraded components.

Supabase Auth: invited email/password users for initial deployment; no public self-signup. API validates identity via supported getUser/getClaims/JWT verification, including signature/issuer/audience/expiry. Decoding a JWT or trusting client getSession is insufficient. Use secure HttpOnly SameSite cookies and CSRF/origin protection for state-changing routes; implement refresh/logout with per-request session handling, never a global mutable authenticated client shared across users.

Students may chat and open authorised sources; curators may manage the shared knowledge base. Active membership/role comes from protected server-managed records. Bootstrap the first curator through an explicit operator command; users cannot promote themselves. One organisation/shared corpus, not multi-tenant SaaS. Role checks protect every API operation regardless of hidden UI elements.

Private object bucket; authenticated backend downloads or short-lived signed URLs after authorisation. Supabase secret key/database credentials, Qdrant key, and LLM key remain server-side. Publishable key is not an admin credential. Restrict browser access to canonical tables with RLS/permissions; if server credentials bypass RLS, enforce application membership/role checks rigorously. Least-privilege runtime DB role separate from migration/admin credentials where feasible.

Apply shared PostgreSQL-backed per-user quotas with atomic counters, bounded request/upload concurrency, and login/upload/chat limits. Avoid wildcard CORS; use same-origin HTTPS in production. No secrets, full prompts, source contents, or tokens in logs. Keep retention/settings operator-configurable; final client requirements remain to be confirmed, not invented.

## 11. Provider switching, reindexing, and rollback

Changing answer model/base URL/credentials requires adapter-compatible configuration and restart, not reindexing. Validate API/context support and rerun generation evaluations before activating a different production model. Paid model use is explicit configuration.

Embedding changes (model/version/dimensions/prefix/normalisation/tokenizer) or chunking changes create a new profile and collection. Equal dimensions do not imply equal embedding space. Changing vector providers requires an adapter and migration/reindex from canonical text. Changing storage/metadata providers requires adapter plus data migration, not just a URL swap.

Implement operator CLI: reindex, validate candidate, activate profile, rollback, and protected cleanup. Build a candidate from retained canonical text, keep old profile active until counts/integrity/retrieval evaluations pass, atomically activate in SQL, and retain the old profile for rollback. Requests snapshot one profile. While reindexing, block uploads/approval/lifecycle changes with a maintenance message for this first production release; continue queries against the old profile. Use a durable SQL lock checked by all writers, not only a process-local flag.

Collection/profile fingerprint records embedding/tokenizer/model metadata, dimensions/distance, input formatting, parser/chunker versions, and chunk parameters. Unknown hosted revision must be disclosed. Incompatible configuration cannot silently query old vectors. Cleanup targets explicit known profile IDs; never use broad collection-prefix deletion.

## 12. Deployment, operations, and repository deliverables

Supply Dockerfile, production/staging `render.yaml` profiles, compose.yaml for local PostgreSQL/Qdrant, lockfile, migrations, `.env.example`, README, sample upload, tests, and evaluations. No real secrets in manifests. Web binds 0.0.0.0 on Render PORT; worker runs the same image with a worker command. Hosted embeddings keep base-image memory low; local tests can use fakes or opt-in local models.

Use Alembic migrations once through an explicit release task before rolling out API/worker versions; no competing automatic migrations from every process. Prefer additive backward-compatible schema changes. Separate build/start/release instructions and test health checks and graceful shutdown. Worker stops claiming on shutdown and releases/lets leases expire safely.

Repository layout: app/{api,services,adapters,parsing,static}, domain/protocols/settings/composition modules, worker and operator CLI, migrations, tests/{unit,integration,fixtures}, samples, evaluations/{datasets,runner,scoring}, deployment files, README. Maintain provider-independent adapter contract tests. Do not generate unused framework scaffolding.

Implement structured stage timings, request/job IDs, error/retry counters, dependency checks, and usage tracking; configurable error-monitoring integration can be enabled with a secret DSN. Operator runbook covers provider outages/quotas, failed jobs, expired leases, schema rollback limits, account access, model changes, and storage growth.

Backups are mandatory operational preparation: PostgreSQL consistent logical exports or supported managed backups, original-object export/versioned backup, and index profile metadata. Vectors can be rebuilt from canonical text; Qdrant snapshots are optional acceleration. Document scheduling/retention and restore commands; provide a restore smoke test in staging. Do not assume free plans include backups or object versioning. Backup destination and RPO/RTO require operator/client choice; mark unconfigured backups and unperformed restore drills as production-launch blockers, not completed features.

No invented availability guarantee. Launch checklist includes configured accounts/secrets, specific model/quota, authenticated access, migration success, approved five-document ingestion, live cited answers, evaluations, restore check, and operator ownership. Until client traffic/privacy/retention/budget requirements are confirmed, record assumptions explicitly.

## 13. Acceptance checks

Require meaningful tests for:

1. Parsing/location preservation for TXT/PDF/DOCX and OCR-required cases.
2. Incremental append; duplicate/concurrent duplicate idempotency; no lost canonical long-answer text.
3. Chunk/query tokenizer bounds and compatible remote-inference/vector representations.
4. Crash/lease recovery; no partial/unapproved/deleted/inactive sources in retrieval.
5. Approval, replacement, reactivation, and deletion workflows; failed replacement preserves old answer source.
6. Provider timeout/rate-limit/auth/configuration errors; no hidden provider or paid fallback.
7. Citation IDs, correct source mapping, insufficiency/conflict handling, and prompt-injection fixtures.
8. Exact-match Q&A applicability; rephrased retrieval with reviewed evidence.
9. JWT/session/CSRF/role restrictions; no self-promotion, source leakage, script execution, or leaked secrets.
10. Index incompatibility, maintenance lock, candidate validation, activation, rollback, and targeted cleanup.
11. Rate limits, graceful shutdown, runtime readiness, migration and backup/restore smoke checks.
12. Frontend required states, keyboard navigation, responsive white layout, and visual verification where tools permit.

Offline tests must run without network or API credits; integration tests use isolated local/cloud test resources and explicit credentials. Do not mix faked tests with real-model quality claims. When credentials exist, perform one live upload/review/approve/chat/citation/append/restart check. Report unperformed browser/live/restore checks explicitly.

## 14. Implementation sequence and handoff

Implement contracts/configuration/migrations/auth, then parsers and token-aware chunking, cloud adapters, durable staged ingestion, retrieval/generation/citations, white UI, document lifecycle, deployment/runbook, provider migration, and evaluation harness. Iterate for observed failures; do not stop after scaffolding.

Deliver run/deploy/test/evaluation commands, accounts/secret names, human-review requirements, screenshots when verified, and known limitations. Distinguish “code implemented”, “tests passed”, and “production deployment verified”. No agents, MCP, automatic OCR, fine-tuning, external web search, microservices fleet, or analytics dashboard. Hybrid search/reranking/history rewriting are later evidence-driven extensions, not mandatory dependencies.

## 15. Official references and interpretation

Checked 11 October 2026. Vendor availability changes; recheck at deployment. Application limits/thresholds are design choices, not vendor guarantees.

- Render service/free/disk constraints: https://render.com/docs/free and https://render.com/docs/disks
- Supabase PostgreSQL connection/pooler guidance: https://supabase.com/docs/guides/database/connecting-to-postgres
- Supabase JWT verification: https://supabase.com/docs/guides/auth/jwts
- Supabase free quotas: https://supabase.com/docs/guides/platform/billing-on-supabase
- Qdrant hosted inference/free models: https://qdrant.tech/documentation/cloud/inference/
- Qdrant cloud inference usage: https://qdrant.tech/documentation/cloud/quickstart-cloud/
- Qdrant client inference contract: https://github.com/qdrant/qdrant-client
- OpenRouter free router and variable underlying model: https://openrouter.ai/docs/guides/routing/routers/free-router
- OpenRouter model discovery/completions: https://openrouter.ai/docs/api/api-reference/models/get-models and https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request
- MiniLM tokenizer/model limits: https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2

## 16. End-to-end pipeline evaluations — required deliverable

Build an evaluation harness alongside the production application. Its purpose is to locate failures by pipeline stage and compare configurable providers against the same evidence. Do not reduce evaluation to whether an answer sounds good.

### 16.1 Evaluation assets and separation

Deliver `evaluations/datasets/dev.jsonl`, `evaluations/datasets/test.jsonl`, source fixtures, a runner, scoring code, and a report template. Begin with at least 30 development cases and 20 held-out cases; count paraphrases as belonging to the same question family. Split by question family so variants of the same question cannot leak across development and held-out sets. Use development cases for prompts, chunking, and threshold selection; keep the held-out set unchanged for the release check. If held-out cases are used to tune, disclose that and create a new holdout before claiming an independent check.

The corpus must be an explicitly labelled sample corpus with human-authored/reviewed answers. Golden snippets are references for factual support, not a requirement to reproduce wording. Synthetic cases are useful functional fixtures but must never be presented as representative student performance. The 30/20 counts and targets below are initial release-fixture requirements, not a statistically powered benchmark.

Cover these categories across the dataset:

- Direct curated questions and paraphrases.
- Exact technical names/acronyms, including RAG, chunking, embeddings, tool calling, MCP, and context windows where source fixtures actually cover them.
- Questions requiring two passages or a split long answer.
- Unsupported questions and partially answerable questions.
- Conflicting source statements, requiring acknowledgement rather than arbitrary selection.
- New information introduced through an appended upload.
- Duplicate, unapproved, replaced, superseded, deleted, malformed, question-only, and failed/partial-ingestion documents.
- Unauthenticated/student attempts to approve, delete, change roles, or access restricted operations.
- Backup restoration, durable jobs across API/worker restarts, and active-profile rollback.
- Prompt-injection text inside source documents.
- Long queries and documents near configured limits.
- Provider timeouts, rate limits, invalid credentials, restart/retry, and index migration.

Infrastructure/failure cases can be a separate executable scenario suite rather than natural-language test rows. Keep functional invariants separate from probabilistic quality metrics.

Example case schema:

```json
{
  "case_id": "rag_paraphrase_01",
  "question_family": "rag_definition",
  "category": "paraphrase",
  "question": "Why would we fetch notes before asking the model to answer?",
  "expected_action": "answer",
  "relevant_evidence_ids": ["rag_definition"],
  "required_facts": ["retrieved evidence is supplied to generation"],
  "forbidden_claims": ["RAG guarantees every answer is correct"],
  "expected_source_locations": [
    {"fixture": "curated_ai_engineering_qa.txt", "section": "RAG"}
  ],
  "notes": "Use independently reviewed gold evidence."
}
```

Map stable fixture evidence IDs to runtime document/passage IDs after ingestion. Do not key relevance solely to physical chunk IDs, which change when chunking changes. Store text spans or evidence labels so alternative chunk configurations can be fairly evaluated. Use expected_action values `answer`, `partial_answer`, `abstain`, or `error` as appropriate.

### 16.2 Stage-specific measurements

| Stage | Measure | How to score |
|---|---|---|
| Parsing | Expected text/location preservation | Known text spans and correct PDF page/DOCX section references survive extraction |
| Chunking | Coverage and token-limit compliance | All gold evidence retained; every embedding input fits the active tokenizer limit |
| Ingestion | Publication integrity and idempotency | Only complete READY sources are retrieved; retries/duplicates preserve counts |
| Retrieval | Hit rate@5 | Fraction of answerable cases with at least one relevant evidence unit in top five |
| Retrieval | Recall@5 | Retrieved relevant evidence units divided by all required relevant units, averaged per case |
| Retrieval | MRR@20 | Mean reciprocal rank of first relevant evidence unit in the candidate results |
| Retrieval | Context coverage | Required evidence units retained in the actual budgeted LLM context, not only candidate hits |
| Answering | Correctness/completeness | Human rubric against required facts and forbidden claims |
| Grounding | Supported-claim rate | Supported substantive claims divided by all substantive claims; review against source text |
| Citations | ID validity, support, coverage | Valid source IDs; cited passage supports claim; factual claims have supporting citations |
| Abstention | Appropriate abstention and false-abstention rate | Report unsupported cases declined and answerable cases incorrectly declined separately |
| Operations | Latency and failure rate | Parse/embed/upsert/retrieve/generate stages, total latency, retries, and provider failures |
| Resources | Usage | Reported LLM tokens, embedding counts, model load time, and local memory where measurable |

Define denominators in the report. For retrieval, deduplicate evidence units across overlapping chunks. For multi-evidence questions, report full evidence coverage separately from any-hit success. Unsupported cases have no relevant-source denominator; score them through abstention/grounding, not retrieval recall.

Measure latency p50 and p95 only over labelled runs; state sample count, concurrency, network conditions, cold/warm model state, and provider/model returned. Treat quantiles from small samples as descriptive only. Separate first model download/load from steady-state query latency. Report production-provider latency separately from free-route testing. Set latency/availability targets with the client; free-route results cannot establish a production SLA.

### 16.3 Groundedness and answer review rubric

Score generated answers on a 0–2 scale for each dimension:

- Correctness: 0 incorrect; 1 partly correct; 2 correct against gold facts.
- Completeness: 0 misses core answer; 1 covers some required facts; 2 covers the required scope.
- Grounding: 0 introduces material unsupported claims; 1 partly supported; 2 substantive claims supported by provided evidence.
- Citation support: 0 missing/invalid/misleading; 1 incomplete or mixed support; 2 correct supporting references for substantive claims.
- Clarity: 0 confusing; 1 understandable with avoidable ambiguity; 2 concise and clear for a student.

Do not give an unsupported abstention a correctness score of zero when abstention is the expected behaviour. Do not allow an average rubric score to hide a fabricated source or material unsupported claim; report these as separate critical failures.

Exact-match approved answers bypass the LLM but still need correct source mapping and applicability checks. Evaluate that path separately from generated semantic-match answers.

Automated checks can verify IDs, token limits, expected source coverage, and structural behaviour. Human review is the reference for factual correctness and support. A free LLM judge is optional: if used, show it the question, gold facts, answer, and exact passages; require a rationale and cited evidence, calibrate against at least 10 human-reviewed cases, report disagreement, and do not use the judge alone as the release gate. Judge output is not empirical truth.

### 16.4 Initial release quality gates

These are provisional engineering targets on the checked-in fixture sets. Report results, not just pass/fail, and revisit targets using real student questions later.

- All deterministic ingestion, access, citation-ID, token-limit, profile-compatibility, and retry invariants must pass.
- Retrieval hit rate@5: at least 85% on answerable fixture cases; report actual numerator and denominator.
- Average evidence recall@5 and actual-context coverage: each at least 80% on answerable fixtures; report multi-evidence results separately.
- Appropriate abstention: at least 90% on unsupported fixtures; false abstention no more than 15% on answerable fixtures. Small datasets may make one case materially change percentages; show counts.
- At least 80% of reviewed generated answers score 2 for correctness and grounding; report all rubric dimensions and all failing cases.
- Zero unknown source IDs exposed as accepted citations, and zero material unsupported claims in answers marked successful on the release fixture run. If the latter gate fails, repair the prompt/retrieval/fallback or disclose the failure rather than describing the release as verified.
- No automatic unconfigured or paid-provider fallback. Provider outages must be labelled and reported separately from semantic quality failures, with an additional end-to-end success rate including outages.

Do not loosen targets silently to make the report green. Fix observed failures where practical; document limitations and provisional thresholds honestly. Passing a small fixture set does not establish production reliability; expand the reviewed test set using the client's actual five documents before launch.

### 16.5 Evaluation commands and outputs

Provide these commands, or documented equivalent commands with the same behaviour:

```bash
python -m evaluations.run --dataset dev --mode offline
python -m evaluations.run --dataset dev --mode retrieval
python -m evaluations.run --dataset test --mode end-to-end
python -m evaluations.compare --baseline path/to/baseline.json --candidate path/to/candidate.json
```

- Offline mode: fakes only; functional parsing/chunking/ingestion/citation/error invariants; never label mocked answer quality as real model performance.
- Retrieval mode: real configured embedding strategy and Qdrant; bypass answer LLM. Use a dedicated evaluation collection/profile and isolated evaluation PostgreSQL records/schema and object-storage prefix, never the curator's live corpus.
- End-to-end mode: real configured provider; explicit invocation, bounded request count, no automatic paid fallback; a configured paid production model is permitted only with an explicit evaluation request budget. Record timeouts/rate limits without dropping inconvenient cases.
- Comparison: same dataset/corpus revision; highlight changes in retrieval, grounding, abstention, failures, and latency. Flag incompatible or incomplete runs rather than comparing them as equivalent.

Write a machine-readable JSON report, per-case JSONL, and a readable Markdown summary under an ignored `evaluation_runs/<run_id>/` directory. Record git commit, dataset and corpus hashes, timestamp, configuration with secrets redacted, adapter versions, resolved embedding revision, index profile fingerprint, requested and actual LLM model IDs, prompt version, chunk parameters, score thresholds, run mode, counts, stage timings, and gate results. Include top failures and recommended next fixes. Do not log credentials or full private documents.

Cache only where explicit and labelled. A cached replay is not a live provider availability test. For comparing answer models, freeze the retrieval context so the answer-stage comparison isolates the model; run a separate full-pipeline comparison when embeddings or retrieval settings change. Repeat a small subset three times to show free-router output/model variation without implying statistical confidence.

Evaluation collection cleanup must target only the explicit evaluation namespace. Require confirmation before any CLI cleanup that could delete a non-evaluation collection. The runner must never reset the active application collection.

### 16.6 Evaluation handoff at completion

The coding agent must finish with the evaluation report or a precise statement of what could not be run and why. Provide deterministic test results, retrieval results, real LLM results, and human-review status separately. Include the baseline configuration and a repeatable command for evaluating any future provider/model change. This evaluation harness and its fixtures are part of the required implementation, not an optional future enhancement.
