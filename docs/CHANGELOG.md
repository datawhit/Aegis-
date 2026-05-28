# Aegis — Sprint Audit Trail

> Append-only. Each sprint adds a new section; nothing is rewritten in
> place. This file is the engineering memory of the project — read it
> top-to-bottom to understand how we got here.

---

## SPRINT 00 — FOUNDATION

- **DATE:** 2026-05-27
- **STATUS:** Delivered. Awaiting review before Sprint 1 kickoff.
- **DURATION:** 1 day (scaffold-only sprint)
- **OWNER:** Principal Architect (claude-opus-4-7)

### SPRINT OBJECTIVE

Stand up the monorepo, infra, schemas, and abstraction interfaces that all
later sprints plug into. **No business logic.** The success criterion is
that Sprint 1 can begin writing alert-ingestion and AI-triage code without
arguing about plumbing.

### TECHNICAL SCOPE

In scope:

- Monorepo skeleton (`backend/`, `frontend/`, `docs/`)
- Docker Compose stack: Postgres 16 + pgvector, Redis 7, FastAPI, Celery
  worker, Vite/React frontend
- FastAPI app + structured logging + async SQLAlchemy + Alembic
- Foundational data model (9 tables) shipped as the initial migration
- `IdentityProvider`, `WorkflowEngine`, `AuditLogger`, `PolicyEngine`
  protocols + concrete Phase 0 implementations + stubbed alternates
- Tamper-evident audit log (SHA-256 hash chain)
- Lean frontend that proves the wiring against `/api/v1/health`
- GitHub Actions CI (ruff, mypy, pytest backend; eslint, tsc, build frontend)
- Architecture doc, ADR log, sprint changelog (this file)

Explicitly **out of scope** (deferred — see DECISIONS.md ADR-001):

- Temporal Server (Celery first; abstraction lets us swap)
- LocalStack / any AWS service
- OTel collector / Grafana / Loki (structlog with OTel-compatible names now)
- HashiCorp Vault (env vars + `.env`)
- Multi-tenancy
- Advanced RBAC (single admin role)

### PRODUCT SCOPE

Phase 0 ships **zero user-visible product features** by design. The
frontend renders a single status panel that polls `/health`. This is
intentional — it forces every Phase 0 piece to be honest about whether
it is foundation or premature feature work.

### SECURITY CONSIDERATIONS

- **Identity from day 1.** Audit log entries have real actor IDs from
  the first authenticated request. No retrofitting needed when SSO lands.
- **Default-deny policy engine.** ADR-005: every unmatched eval returns
  `ESCALATE`. No code path can produce `ALLOW` without an explicit rule
  match + rollback plan + confidence threshold.
- **Tamper-evident audit log.** SHA-256 chain (ADR-004). Verifier
  scheduled for Sprint 2.
- **JWT secret default fails loudly.** `.env.example` ships a placeholder;
  if it ends up in a non-local env we want it to be obvious.
- **CORS allowlist** is env-driven; no `allow_origins=["*"]` even in dev.
- **Idempotency keys** are first-class on `workflow_runs` and
  `remediation_actions` — duplicate submissions can never double-execute
  against integrations.

### ARCHITECTURAL DECISIONS

Each was reviewed before adoption; full text in
[DECISIONS.md](DECISIONS.md):

- **ADR-001** Lean MVP foundation over enterprise stack day 1
- **ADR-002** Celery first, Temporal-ready (workflow engine abstraction)
- **ADR-003** Local JWT now, Okta-ready (identity abstraction)
- **ADR-004** Tamper-evident audit log via SHA-256 hash chain
- **ADR-005** Default-deny + escalate-on-uncertainty for the policy engine
- **ADR-006** Defer DB-role-level audit log immutability to Sprint 2

### FEATURES IMPLEMENTED

| Feature                                | Status        | Notes                                   |
| -------------------------------------- | ------------- | --------------------------------------- |
| Docker Compose dev stack               | ✅ shipped    | `make up` brings up everything          |
| FastAPI app + health/ready endpoints   | ✅ shipped    |                                         |
| Alembic w/ initial migration           | ✅ shipped    | 9 tables + pgvector extension           |
| `IdentityProvider` interface           | ✅ shipped    |                                         |
| `LocalJWTIdentityProvider`             | ✅ shipped    | HS256, bcrypt                           |
| Okta IdentityProvider stub             | ✅ shipped    | raises NotImplementedError              |
| `/auth/login` + `/auth/me`             | ✅ shipped    | Login is audited (success AND failure)  |
| `WorkflowEngine` interface             | ✅ shipped    |                                         |
| `CeleryWorkflowEngine`                 | ✅ shipped    | Idempotent submit, cancel, rollback     |
| Temporal WorkflowEngine stub           | ✅ shipped    |                                         |
| `HashChainAuditLogger`                 | ✅ shipped    | SELECT-FOR-UPDATE on chain tip          |
| Stub policy engine (default-escalate)  | ✅ shipped    | Hard invariants from ADR-005 enforced   |
| Celery worker app + ping task          | ✅ shipped    |                                         |
| Dev admin seed script (`make seed`)    | ✅ shipped    | Refuses to run outside `local`/`ci`     |
| Vite + React frontend proving wiring   | ✅ shipped    | Polls `/health` every 5s                |
| GitHub Actions CI                      | ✅ shipped    | Backend matrix w/ Postgres+Redis        |
| Architecture + ADR + changelog docs    | ✅ shipped    |                                         |

### FILES CREATED (76)

Top-level (9):
- `README.md`, `.gitignore`, `.env.example`, `docker-compose.yml`,
  `Makefile`, `.github/workflows/ci.yml`, `docs/ARCHITECTURE.md`,
  `docs/DECISIONS.md`, `docs/CHANGELOG.md`

Backend — infra (6):
- `backend/pyproject.toml`, `backend/Dockerfile`, `backend/alembic.ini`,
  `backend/alembic/env.py`, `backend/alembic/script.py.mako`,
  `backend/alembic/versions/0001_initial_schema.py`

Backend — app foundation (5):
- `backend/app/__init__.py`, `backend/app/main.py`,
  `backend/app/config.py`, `backend/app/db.py`,
  `backend/app/logging.py`

Backend — models (10):
- `backend/app/models/__init__.py`, `.../base.py`, `.../user.py`,
  `.../alert.py`, `.../incident.py`, `.../policy.py`,
  `.../remediation_action.py`, `.../approval.py`,
  `.../workflow_run.py`, `.../audit_log.py`, `.../ai_reasoning.py`

Backend — core (12):
- `backend/app/core/__init__.py`
- `core/identity/{__init__.py, base.py, local_jwt.py, okta_stub.py}`
- `core/workflow/{__init__.py, base.py, celery_engine.py, temporal_stub.py}`
- `core/audit/{__init__.py, logger.py}`
- `core/policy/{__init__.py, engine.py}`

Backend — API + schemas + workers + scripts (12):
- `app/api/__init__.py`, `app/api/deps.py`
- `app/api/v1/{__init__.py, router.py, health.py, auth.py}`
- `app/schemas/{__init__.py, token.py, user.py}`
- `app/workers/{__init__.py, celery_app.py}`
- `app/scripts/{__init__.py, seed_dev_admin.py}`

Backend — tests (4):
- `tests/__init__.py`, `tests/conftest.py`, `tests/test_health.py`,
  `tests/test_audit_hash_chain.py`, `tests/test_policy_engine_defaults.py`

Frontend (15):
- `frontend/package.json`, `Dockerfile`, `vite.config.ts`, `tsconfig.json`,
  `tsconfig.node.json`, `tailwind.config.ts`, `postcss.config.js`,
  `.eslintrc.cjs`, `index.html`
- `src/{index.css, main.tsx, App.tsx}`
- `src/lib/{api.ts, queryClient.ts}`
- `src/stores/authStore.ts`

### FILES MODIFIED

None. Phase 0 is a greenfield sprint.

### DATABASE CHANGES

Initial schema (Alembic revision `0001_initial`):

- Enables `vector` extension (used Sprint 1+ for RAG; flipped on now to
  avoid a migration-time surprise).
- Tables: `users`, `incidents`, `alerts`, `policies`, `workflow_runs`,
  `remediation_actions`, `approvals`, `ai_reasoning_snapshots`,
  `audit_logs`.
- Indexes designed for the queries we know we'll run in Sprints 1–3:
  active incidents by status+severity, alerts by correlation key, audit
  log by actor and resource, workflow runs by status.
- Uniqueness: `alerts(source, source_event_id)`, `workflow_runs.idempotency_key`,
  `remediation_actions.idempotency_key`, `policies.name`, `users.email`,
  `audit_logs.entry_hash`.

### API CHANGES

New endpoints (all under `/api/v1`):

| Method | Path        | Auth | Description                                    |
| ------ | ----------- | ---- | ---------------------------------------------- |
| GET    | `/health`   | none | Liveness check.                                |
| GET    | `/ready`    | none | Readiness check — pings Postgres.              |
| POST   | `/auth/login` | none | Issue access + refresh JWT. Audits attempt.   |
| GET    | `/auth/me`  | bearer | Current user identity claims (round-trip test). |

### TECHNICAL DEBT INTRODUCED

| ID  | Item                                                            | Owed-by Sprint |
| --- | --------------------------------------------------------------- | -------------- |
| D-1 | DB-role-level audit immutability (currently app-layer only)     | Sprint 2       |
| D-2 | Real policy DSL (Phase 0 stub returns ESCALATE for everything)  | Sprint 2       |
| D-3 | OpenTelemetry tracing wiring (logger field names are OTel-ready)| Sprint 3       |
| D-4 | Refresh-token rotation + revoke list                            | Sprint 3       |
| D-5 | Audit-chain verifier (cron job that re-walks the chain)         | Sprint 2       |
| D-6 | Reconciler for `PENDING` workflow_runs after broker hiccups     | Sprint 2       |
| D-7 | Switch frontend auth storage from localStorage to httpOnly cookie + CSRF | Sprint 3 |
| D-8 | Production multi-stage Dockerfile + non-root user               | Sprint 1       |
| D-9 | Type stubs for `python-jose` (currently `ignore_missing_imports`) | Sprint 1     |

### RISKS IDENTIFIED

| ID  | Risk                                                                                  | Likelihood | Impact | Mitigation                                                                                  |
| --- | ------------------------------------------------------------------------------------- | ---------- | ------ | ------------------------------------------------------------------------------------------- |
| R-1 | Celery → Temporal migration carries hidden coupling we haven't seen yet               | Medium     | Medium | Workflow interface is deliberately tiny (4 methods); guardrail tests in Sprint 2            |
| R-2 | Hash chain canonicalization (`json.dumps`) is not RFC 8785 — could differ cross-lang  | Low        | Low    | Spec the canonicalization formally if we ever export the chain for external verification    |
| R-3 | `SELECT ... FOR UPDATE` on audit tip becomes a write-bottleneck under load            | Low        | Medium | Acceptable for Phase 0; revisit if `audit_logs` insert rate exceeds ~500/s                  |
| R-4 | Default-escalate policy stub creates ticket-flood early on once ingestion lands       | High       | Medium | Sprint 2 ships the real DSL + a `suppress` effect to drain low-value alerts                 |
| R-5 | Frontend `localStorage` token vulnerable to XSS exfiltration                          | Medium     | High   | Tracked as D-7; before any real customer data we move to httpOnly cookies                   |
| R-6 | No SBOM / dependency scanning in CI yet                                                | Medium     | Medium | Sprint 3 adds Trivy + Snyk equivalent                                                       |

### ROLLBACK STRATEGY

Phase 0 is greenfield infrastructure. Rollback = `make nuke && git revert`.

For each subsequent sprint we will document a real rollback path
(migrations down, feature flag flip, deploy rollback) here.

### KNOWN LIMITATIONS

1. The stub policy engine never returns `ALLOW`. Until Sprint 2, every
   proposed remediation will escalate to human approval — by design, but
   it means autonomous remediation cannot demo end-to-end yet.
2. No real workflow tasks exist. The Celery worker boots, ingests the
   `__ping__` task, and that's it.
3. `Okta` provider stub raises on use. Setting
   `AEGIS_IDENTITY_PROVIDER=okta` will produce 500s; this is deliberate
   (fail-loud).
4. No production Dockerfile yet — `Dockerfile` is dev-mode (root user,
   editable install, hot reload). D-8.
5. CI lint/typecheck pass against the code in this commit, but the CI
   job hasn't *run* yet (this is the first commit).

### OBSERVABILITY (current state)

- **Logs:** structlog → stdout, JSON in non-local, console in local. Field
  names align with OTel semantic conventions where applicable.
- **Metrics:** none yet (deferred per ADR-001). Sprint 3 wires the OTel
  collector.
- **Traces:** none yet (same).
- **Health:** `/api/v1/health` and `/api/v1/ready` exposed.
- **Audit:** `audit_logs` table is the durable, queryable trail of every
  decision. Login attempts already write to it.

### NEXT STEPS — Sprint 1 candidate scope

Working title: **"First end-to-end signal flow."**

Proposed objective: a webhook posts a Defender alert → it normalizes to
an `alerts` row → the AI triage engine creates an `Incident` with a
classification + confidence → the stub policy engine escalates → an
approval request is logged. **No remediation execution yet.** This
ensures the entire pipeline is wired end-to-end before we trust it to
take action.

Specifically:

1. `POST /api/v1/ingest/{source}` webhook endpoint with HMAC verification
2. Source-specific normalizers (Defender first; Okta + Slack-as-source
   thereafter)
3. AI triage engine — first cut, Claude-only, structured-output mode,
   reasoning snapshot persisted before any decision is taken
4. Incident creation + alert linkage logic (`correlation_key` clustering)
5. Pass the proposed action through the stub policy engine end-to-end
6. UI surface: incidents list + incident detail w/ AI reasoning panel
7. Tests: integration test that takes a sample Defender event JSON and
   asserts the incident + reasoning snapshot + audit chain entries

Carry-over from Phase 0: D-8 (prod Dockerfile), D-9 (jose type stubs).

### OPEN QUESTIONS

These are deliberately surfaced for the next strategy pass — they will
shape Sprint 1 scope or Sprint 2 architecture. See the **Strategic
Product Questions** section at the end of this file for the product-
side counterparts.

| ID    | Question                                                                                       | Needed by |
| ----- | ---------------------------------------------------------------------------------------------- | --------- |
| OQ-1  | First connector: Defender, Okta, or both in parallel?                                          | Sprint 1  |
| OQ-2  | AI triage — Claude only or dual-provider with disagreement-as-signal?                          | Sprint 1  |
| OQ-3  | How do we want the audit-chain verifier to alert on mismatch — Slack, page, both?              | Sprint 2  |
| OQ-4  | Policy DSL — homegrown JSON-rules, CEL, Rego/OPA, or Cedar?                                    | Sprint 2  |
| OQ-5  | What's the SLA on approval requests before auto-escalation to on-call?                         | Sprint 2  |
| OQ-6  | Where do we draw the line between Aegis and the customer's SIEM/SOAR? (positioning)            | Now       |
| OQ-7  | Do we ship a hosted SaaS, on-prem, or dual-deploy? (affects everything from auth to telemetry) | Now       |

---

## STRATEGIC PRODUCT QUESTIONS — Sprint 00 closeout

> Required by the master prompt: every sprint ends with strategic product
> questions, informed by current cybersecurity market dynamics. These are
> for the product owner; pick the ones to prioritize before Sprint 1 kickoff.

### 1. Positioning vs. the SOC tool stack

The crowded SOC tool stack in 2026 is: SIEM (Splunk/Sentinel/Elastic) +
EDR (CrowdStrike/Defender/SentinelOne) + SOAR (Tines/Torq/Splunk SOAR) +
case management (Tines + Smart SOAR + a Jira board). The default reaction
to a new "AI security platform" is *"is this a SOAR or a SIEM?"*

  - **Q1.** Where does Aegis sit relative to existing SOARs? Are we
    *replacing* the SOAR (riskier, larger ACV) or *governing* the SOAR
    (smaller wedge, faster adoption, but lower TCV per customer)?
  - **Q2.** If we govern, do we plan to write integrations *into* the
    incumbent SOAR (Tines step, Torq step) or *around* it (we are the
    decision layer; SOAR remains the executor)?

### 2. ICP & first paying customer

  - **Q3.** Is the design partner profile: (a) a 5–15 person SOC at a
    mid-market SaaS (200–2000 employees), (b) a managed MSSP that wants
    to multiply analyst leverage, or (c) a regulated enterprise (FinServ /
    Healthcare) with explicit AI-governance buying pressure? The product
    spec changes meaningfully across these three.
  - **Q4.** What's the *one* metric the buyer is being measured on that
    Aegis moves — MTTR? false-positive rate? Tier-1 analyst headcount?
    overnight coverage cost? Naming this number drives the whole demo
    story.

### 3. AI governance moat

The "AI governance" framing is the differentiator, but it's also the
crowded narrative right now (every vendor adds the word).

  - **Q5.** What's our defensible angle on governance that we can ship
    in Sprint 2–3? Options: (a) **policy-as-code DSL** that maps to
    common frameworks (NIST AI RMF, EU AI Act Article 13–15); (b)
    **provable audit chain** + third-party attestable exports; (c) the
    **rollback-first invariant** (no action without a defined undo);
    (d) **AI reasoning transparency** (full prompt + evidence + model
    version on every decision).
  - **Q6.** Do we want compliance certifications (SOC 2 Type II first,
    then ISO 27001) on the *roadmap*, or actively pursued from Sprint 5
    onward? Procurement at our likely ICPs will gate on this.

### 4. Pricing & packaging

  - **Q7.** Is the pricing axis (a) per-alert-ingested, (b) per-analyst
    seat, (c) per-action-executed (consumption), or (d) flat platform
    tier? Each invites different buyer objections — analyst-seat caps
    upside, consumption invites cost-shock pushback.
  - **Q8.** Do we plan a free tier / OSS core? An OSS-licensed
    "governance kernel" with paid integrations + hosted control plane
    is a defensible posture in this market, but it commits us to
    public-repo discipline forever.

### 5. AI safety positioning under the EU AI Act

The EU AI Act is in enforcement; Article 14 (human oversight) and Article
13 (transparency) map almost 1:1 to what Aegis already does
structurally.

  - **Q9.** Is "EU AI Act Article 14 conformity for high-risk AI in
    cybersecurity" worth being a marketing pillar? It's a moat against
    pure-US incumbents who haven't designed for it.

### 6. Adoption friction

  - **Q10.** Will SOCs trust an external "policy engine" deciding
    *whether* their automation runs? The path of least resistance might
    be **shadow mode first** — Aegis runs alongside, observes, scores,
    but doesn't gate. The "would-have-acted vs. did-act" report becomes
    the wedge. Do we want shadow mode as a Phase 1 *feature*, not just
    a sales motion?
  - **Q11.** Who is the buyer? CISO? Head of SecOps? VP of Engineering?
    The buyer changes whether we lead with audit/compliance, with
    analyst productivity, or with autonomy.

### 7. Competitive defensibility

  - **Q12.** The single biggest threat is one of the SOAR incumbents
    (Tines, Torq, Splunk SOAR) bolting an "AI governance module" onto
    their existing footprint. What's our 12-month moat — depth of
    reasoning-as-evidence, regulatory positioning, OSS community, or
    raw model + integration breadth? Answering this informs whether we
    bias toward **going deep on one workflow** (account takeover, say)
    or **going wide on connectors**.

---

> End of Sprint 00. Next entry: **Sprint 01 — First end-to-end signal flow.**

---

## SPRINT 01 — FIRST END-TO-END SIGNAL FLOW

- **DATE:** 2026-05-27
- **STATUS:** Delivered. Awaiting review before Sprint 2 kickoff.
- **DURATION:** 1 day
- **OWNER:** Principal Architect (claude-opus-4-7)

### SPRINT OBJECTIVE

Land the first full path: webhook → normalized alert → AI triage →
incident → proposed remediation → policy eval → escalation. **No
autonomous execution yet.** This sprint proves the pipeline is wired
end-to-end before we trust it to take action.

### TECHNICAL SCOPE

In scope:

- `POST /api/v1/ingest/{source}` with HMAC verification + replay window
- Connector framework (`Connector` protocol, registry, HMAC verifier)
- **Defender XDR connector** with normalization and entity extraction
- `AIProvider` abstraction + Claude Sonnet 4.6 implementation
  (tool_use for structured output)
- `TriageService` composing provider + reasoning-snapshot persistence
- `IncidentService` orchestrating triage → correlation → remediation
  proposal → policy eval, all inside one transaction
- Celery `workflows.triage_alert` task running the pipeline async
- `GET /api/v1/incidents` (paginated) + `GET /incidents/{id}` (detail
  with alerts, reasoning, remediation actions)
- Frontend: real routing, login page, incidents list, incident detail
  with AI reasoning panel and remediation proposal cards
- Test suite: HMAC verifier, Defender normalizer, triage service with
  fake AI provider (success + failure modes), end-to-end ingest

Explicitly out of scope:

- Executing remediation (Phase 1 stub policy escalates everything)
- Slack/Jira notifications for escalations (Sprint 2)
- Approval UI (Sprint 2)
- Real policy DSL (Sprint 2)
- DB-role-level audit immutability (Sprint 2, D-1)

### SECURITY CONSIDERATIONS

- **HMAC verification** is constant-time (`hmac.compare_digest`) with a
  5-minute replay window. Rejections audit-logged so brute-force shows
  up in the chain.
- **HMAC failure mode is undifferentiated 401.** We log specifics
  internally but never tell the caller *which* check failed.
- **Idempotency:** alerts dedupe on `(source, source_event_id)`,
  workflow runs dedupe on `idempotency_key`. Webhook redeliveries
  cannot double-trigger AI calls.
- **Triage is async.** Ingest endpoint returns ~10ms regardless of AI
  cost; bounds DoS exposure on AI billing.
- **AI failure mode is safe.** Provider errors collapse to a fallback
  triage output with `confidence=NULL`, which the policy engine
  ESCALATEs per the ADR-005 invariant. No alert is silently dropped.
- **Reasoning snapshot is persisted *before* the next step.** If the
  pipeline crashes mid-flow, the AI's evidence is already on the chain.
- **PII redaction in prompts is NOT YET wired.** The Defender normalizer
  hashes user identifiers for `correlation_key` (test asserts this),
  but the prompt itself still receives raw entity values. Tracked as
  D-11 — must land before any non-design-partner customer.

### ARCHITECTURAL DECISIONS

- **ADR-007** AIProvider abstraction, Claude Sonnet 4.6 default
- **ADR-008** Aegis-canonical HMAC for webhook ingestion, 5-minute replay
- **ADR-009** Alert→Incident correlation via correlation_key + sliding window
- **ADR-010** Triage runs async via the WorkflowEngine, not inline

### FEATURES IMPLEMENTED

| Feature                                          | Status   | Notes                                      |
| ------------------------------------------------ | -------- | ------------------------------------------ |
| Webhook ingest with HMAC + replay window         | ✅       | 401 audited; 401 reasons not leaked         |
| Defender XDR connector + normalizer              | ✅       | Rides on `incidentId` for correlation       |
| Connector registry                               | ✅       | Adding a source is one `register()` call   |
| AIProvider protocol                              | ✅       |                                            |
| AnthropicAIProvider (Claude Sonnet 4.6)          | ✅       | tool_use enforced via `tool_choice`         |
| OpenAI provider stub                             | ✅       | Fails loud on misconfig                    |
| TriageService                                    | ✅       | Snapshot persisted before return            |
| IncidentService (correlate / propose / eval)     | ✅       | Single-transaction pipeline                 |
| Celery `workflows.triage_alert` task             | ✅       | Idempotent on re-delivery (PENDING gate)   |
| GET /incidents list + filters                    | ✅       |                                            |
| GET /incidents/{id} detail                       | ✅       | Includes reasoning + remediation + alerts  |
| Frontend routing + ProtectedRoute                | ✅       |                                            |
| Login page                                       | ✅       |                                            |
| Incidents list (10s refresh)                     | ✅       |                                            |
| Incident detail w/ AI reasoning panel            | ✅       | Shows prompt template, tokens, latency     |
| Tests: HMAC verifier (7 cases)                   | ✅       |                                            |
| Tests: Defender normalizer (7 cases)             | ✅       |                                            |
| Tests: TriageService (success + failure)         | ✅       | Uses FakeAIProvider                        |
| Tests: ingest e2e (auth, dedup, audit chain)     | ✅       | Mocks Celery dispatch boundary             |

### FILES CREATED (36)

Backend — AI layer (5):
- `backend/app/core/ai/__init__.py`, `base.py`, `anthropic_provider.py`,
  `openai_stub.py`, `triage.py`

Backend — ingestion (3):
- `backend/app/core/ingestion/__init__.py`, `base.py`, `defender.py`

Backend — services + workers + prompts (4):
- `backend/app/services/__init__.py`, `incident_service.py`
- `backend/app/workers/tasks/__init__.py`, `triage.py`
- `backend/app/prompts/__init__.py`, `triage.py`

Backend — API + schemas (6):
- `backend/app/api/v1/ingest.py`, `incidents.py`
- `backend/app/schemas/alert.py`, `incident.py`, `ai_reasoning.py`, `ingest.py`

Backend — tests (7):
- `backend/tests/fakes.py`, `tests/fixtures/__init__.py`,
  `tests/fixtures/defender_alert.json`,
  `tests/test_hmac_verifier.py`, `test_defender_normalizer.py`,
  `test_triage_service.py`, `test_ingest_e2e.py`

Frontend (11):
- `frontend/src/lib/incidents.ts`, `lib/auth.ts`
- `frontend/src/components/incidents/{SeverityBadge,IncidentRow,AIReasoningPanel}.tsx`
- `frontend/src/components/layout/AppShell.tsx`
- `frontend/src/pages/{LoginPage,IncidentsListPage,IncidentDetailPage}.tsx`

### FILES MODIFIED (8)

- `backend/pyproject.toml` — add `anthropic==0.39.0`
- `backend/app/config.py` — add ingestion + correlation settings
- `backend/app/api/v1/router.py` — include ingest + incidents routers
- `backend/app/workers/celery_app.py` — `include=["app.workers.tasks"]`
- `backend/tests/conftest.py` — add `db_session` rollback fixture
- `frontend/src/App.tsx` — replace with real routing + ProtectedRoute
- `.env.example` — add ingestion + correlation env vars
- `docs/DECISIONS.md` — ADRs 007–010

### DATABASE CHANGES

**None.** The Phase 0 schema was designed for this work. Zero migrations
needed — the abstractions did the job they were meant to do.

### API CHANGES

| Method | Path                          | Auth     | Description                                       |
| ------ | ----------------------------- | -------- | ------------------------------------------------- |
| POST   | `/api/v1/ingest/{source}`     | HMAC     | Ingest webhook for a configured source            |
| GET    | `/api/v1/incidents`           | bearer   | Paginated list with optional `status`/`severity`  |
| GET    | `/api/v1/incidents/{id}`      | bearer   | Detail incl. alerts, reasoning, remediation       |

### TECHNICAL DEBT INTRODUCED

| ID   | Item                                                                                       | Owed-by Sprint |
| ---- | ------------------------------------------------------------------------------------------ | -------------- |
| D-10 | Move per-source HMAC secrets from env → DB/Vault (multi-tenant + rotation)                | Sprint 3       |
| D-11 | **PII redaction in AI prompts** (entity values currently sent as-is)                       | Sprint 2       |
| D-12 | Reconciler for orphaned `PENDING` workflow_runs (broker hiccups)                            | Sprint 2       |
| D-13 | Eager-load incidents detail in one query (currently 3 round-trips per detail GET)           | Sprint 2       |
| D-14 | Defender connector tested against fixtures only — no live signed-payload test yet           | Sprint 2       |
| D-15 | Frontend has no error boundary; a render error kills the whole shell                        | Sprint 1.5     |
| D-16 | `anthropic` SDK error taxonomy not fully mapped (rate-limit vs auth vs 5xx all → fallback)  | Sprint 2       |

(Phase 0 debt still open: D-1, D-2, D-3, D-4, D-5, D-6, D-7, D-8, D-9.)

### RISKS IDENTIFIED

| ID   | Risk                                                                                                 | Likelihood | Impact   | Mitigation                                                                       |
| ---- | ---------------------------------------------------------------------------------------------------- | ---------- | -------- | -------------------------------------------------------------------------------- |
| R-7  | Anthropic API outage stalls ALL triage; the fallback path produces noisy ESCALATE storms             | Medium     | High     | Add a circuit breaker + queue-depth metric in Sprint 2; consider OpenAI failover |
| R-8  | Defender's payload schema changes (MS rolls a v3); normalizer breaks silently                        | Low–Medium | High     | Sprint 2 adds a contract test using `mitreTechniques` field presence as canary    |
| R-9  | The `correlation_key` fallback hash can collide across distinct campaigns sharing an entity          | Medium     | Medium   | Phase 4 embedding correlation; in the interim, surface false-merge rate in UI    |
| R-10 | Sliding-window correlation creates a "first-30-min" cliff — a related alert at minute 31 starts new  | High       | Low      | Acceptable for Phase 1; tunable via env; analytics surface the distribution      |
| R-11 | Token cost on triage scales linearly with alert volume — no current cap per tenant                   | High       | Medium   | Sprint 3 adds per-tenant daily cap + alert prioritization                        |
| R-12 | Audit chain insert serializes on the tip lock; under sustained ingest could become hot               | Medium     | Medium   | Already flagged as R-3 in Sprint 00; revisit before any customer pushes >100 alerts/sec |

### ROLLBACK STRATEGY

- **Schema:** no migrations this sprint; rollback is purely application
  code (`git revert`).
- **Env:** new env keys are optional (defaults set in code). Removing them
  leaves the system functional minus the connector.
- **Feature flag:** the ingest endpoint is dispatch-by-source; removing
  `DefenderConnector` from the registry effectively disables Defender
  ingestion without other side effects.

### KNOWN LIMITATIONS

1. **No remediation execution.** Sprint 1 ends at proposal +
   ESCALATE — the policy engine still has no `ALLOW` rule.
2. **No notification of escalations** to Slack / pager. Escalations are
   visible only in the UI.
3. **No approval flow.** The `approvals` table is unused this sprint.
4. **No PII redaction in prompts** (D-11).
5. **AI reasoning panel does not show the prompt itself**, only the
   structured output. Will add a "show prompt" disclosure in Sprint 2 —
   the prompt is persisted; we just need to surface it.
6. **Frontend has no error boundary** (D-15).
7. **Live AI calls are not exercised in CI** — the e2e test mocks Celery
   dispatch (so the worker doesn't run) and the TriageService tests use
   FakeAIProvider. Live integration test against Claude is a manual /
   nightly job (D-16-related).

### OBSERVABILITY (current state)

- **Logs:** every step on the triage pipeline writes a structured event
  (`ingest.hmac_failed`, `ingest.duplicate`, `triage.recorded`,
  `incident.handled`, `workflow.submit`, `policy.eval.*`).
- **Audit chain:** entries for `alert.ingested`, `ingest.rejected`,
  `incident.created`, `incident.alert_linked`, `remediation.proposed`,
  `policy.evaluated`, `workflow.triage_completed`.
- **Metrics / traces:** still not wired (planned Sprint 3).

### NEXT STEPS — Sprint 02 candidate scope

Working title: **"Closed-loop with a human in it."**

Proposed objective: an escalation results in a Slack-delivered approval
request → a user approves → the workflow engine executes a real
remediation (the first real connector: Microsoft Graph for
`revoke_user_sessions`) → rollback is invoked on demand and the chain
records all of it.

Specifically:

1. **Real policy DSL** (D-2) — JSON-based rules first; CEL/Cedar evaluated
   in a spike alongside.
2. **Approval flow.** Slack-delivered request with approve/reject buttons
   (Slack interactive components). `approvals` table comes alive.
3. **First execution connector.** Microsoft Graph
   `users/{id}/revokeSignInSessions`. Idempotent. Rollback is no-op (it's
   not reversible) — so this action class requires explicit approval
   even at high confidence.
4. **PII redaction in prompts** (D-11) before any non-fixture data flows.
5. **Audit-chain verifier** (D-5) as a Celery beat task; alert on Slack
   on mismatch.
6. **DB role for audit log immutability** (D-1, ADR-006).
7. **Frontend:** approval inbox, action review page with rollback button.
8. **Test:** end-to-end approval → execution → rollback → chain
   verification.

Carry-over backlog from Phase 0/1: D-3, D-6, D-7, D-8, D-9, D-10, D-12,
D-13, D-14, D-15, D-16.

### OPEN QUESTIONS

| ID    | Question                                                                                                      | Needed by |
| ----- | ------------------------------------------------------------------------------------------------------------- | --------- |
| OQ-8  | What's the canonical action class for our **first** remediation (`revoke_user_sessions` is my default — confirm)? | Sprint 2  |
| OQ-9  | Approval channel — Slack only in Sprint 2, or Slack + Email + Web UI in parallel?                             | Sprint 2  |
| OQ-10 | For `mitreTechniques` from Defender vs Aegis's own LLM-derived mapping — which wins? Both? Audit both?         | Sprint 2  |
| OQ-11 | Should the AI's prompt itself be visible in the analyst UI, or only the structured output?                    | Sprint 2  |
| OQ-12 | Do we ship a per-tenant daily AI-budget cap in Sprint 3, or push it to a Phase 4 pricing milestone?           | Sprint 3  |

---

## STRATEGIC PRODUCT QUESTIONS — Sprint 01 closeout

> Sprint 00's 12 questions still stand — Q3 (design-partner profile) and
> Q6 (compliance certification posture) remain the highest-leverage. Below
> are the *new* questions that surfaced as we built Sprint 01.

### 1. The "shadow mode" question is now urgent

Sprint 1 ended at "AI proposes; policy engine escalates". Before we add
autonomous execution (Sprint 2's wedge), the customer-facing posture has
to be decided.

  - **Q13.** Do we ship Sprint 2 with **shadow mode by default** — i.e.,
    the system always escalates regardless of what policies allow, and
    customers opt into autonomous execution per action class? This is
    the trust-building posture; it also delays autonomous-execution
    revenue. The alternative — opt-out — is faster to monetize and
    riskier.

### 2. AI provider risk concentration

ADR-007 commits to Anthropic Claude as the Phase 1 provider. R-7 flags
the outage risk.

  - **Q14.** What's the contractual exposure if Anthropic has a 4-hour
    outage during a customer's incident? Is "you're SOC for the duration
    of an outage" a defensible position for an MSSP customer, or do we
    need to ship multi-provider failover in Sprint 3?

### 3. The "audit chain as product" question

The hash-chained audit log is shipped and working. It's also currently
internal infrastructure with no customer-facing surface.

  - **Q15.** Is the audit chain a **marketable artifact** — i.e., do we
    sell "you can export a cryptographically-verifiable transcript of
    every AI decision to your compliance officer" as a feature in
    Sprint 3? It's a differentiator against incumbents who track AI
    decisions in best-effort logs.

### 4. The "explainability tax"

Every triage call persists prompt + evidence + structured output. At
scale, this is a non-trivial storage cost (kilobytes per alert × ~5k
alerts/day per customer × retention years).

  - **Q16.** Retention policy: 90 days hot in Postgres, then archive to
    S3 with content-addressed pointers? Or full retention in Postgres
    until the customer asks for an export?

### 5. The connector-strategy fork

Sprint 2 needs a first **execution** connector (not just ingestion). The
choice shapes the customer's first "wow" moment.

  - **Q17.** Are we building Microsoft Graph (`revoke_user_sessions`)
    first — broadest enterprise reach? Okta (same action, more SaaS-native
    feel)? Or CrowdStrike `isolate_host` (most dramatic visible action,
    biggest demo punch, but limits ICP)?

### 6. Pricing for the LLM cost pass-through

Triage cost is now a real line item: ~$0.005–$0.02 per alert on Sonnet 4.6
depending on payload size.

  - **Q18.** Do we **pass through** AI cost transparently, **absorb** it
    into seat pricing, or **cap** it per tenant with overage billing?
    Each implies a different sales conversation and a different product
    visibility on the cost surface.

---

> End of Sprint 01. Next entry: **Sprint 02 — Closed-loop with a human in it.**

---

## SPRINT 02 — CLOSED-LOOP WITH A HUMAN IN IT

- **DATE:** 2026-05-28
- **STATUS:** Delivered. Awaiting review before Sprint 3 kickoff.
- **DURATION:** 1 day
- **OWNER:** Principal Architect (claude-opus-4-7)

### SPRINT OBJECTIVE

Land the full closed loop: an incident escalates → a Slack-delivered
approval request → a user approves → the workflow engine executes a real
remediation (or its dry-run shadow) → rollback is invocable on demand,
and the audit chain records every step. This is the **trust wedge** of
the product, made tangible.

### TECHNICAL SCOPE

In scope:

- **JSON policy DSL** (`and/or/not/eq/in/gte/lte/matches`) +
  `JSONPolicyEngine` with conflict-detection and DENY-wins-over-equal-priority
  semantics. Three seed policies for the demo.
- **PII redaction** in AI prompts; per-snapshot lookup table so the UI
  can de-redact for display.
- **DB-role audit immutability** (`aegis_audit_writer` INSERT-only) +
  **HashChainVerifier** Celery beat task that re-walks the chain daily.
- **Execution connector framework** + Microsoft Graph connector
  (`revoke_user_sessions`) with **dry-run** posture by default — real
  Graph calls behind `AEGIS_MS_GRAPH_LIVE=true`.
- **Slack Notifier** with Block Kit approval requests; dry-run logs the
  rendered payload when `AEGIS_SLACK_ENABLED=false`.
- **`POST /api/v1/slack/interact`** Slack-signed webhook receiving
  approve/reject button clicks.
- **ApprovalService** state machine: request / approve / reject / expire.
- **RemediationExecutor** service + Celery `workflows.execute_remediation`
  task + rollback task.
- **IncidentService updated:** policy ALLOW + `requires_approval=false`
  dispatches executor; ALLOW + approval-required creates an Approval;
  ESCALATE creates an Approval; DENY hard-stops.
- New REST: `GET /approvals`, `POST /approvals/{id}/decision`,
  `POST /remediations/{id}/rollback`, `GET/POST /policies` (admin),
  `POST /slack/interact`.
- Frontend: approval inbox page with approve/reject mutations,
  remediation rollback control in incident detail, prompt-disclosure on
  AI reasoning panel (data already persisted in Sprint 1).
- Tests: policy DSL (10 cases), PII redaction (6 cases), audit verifier
  (clean chain + tampering + link break detection), full e2e
  approval→execute→rollback path with audit-chain assertion.

Explicitly out of scope:

- Email + Web-UI approval channels (Phase 3)
- Policy update/delete + policy edit UI (Phase 3)
- Real MS Graph live calls in CI (dry-run is the demo; live behind
  flag for ops smoke)
- Multi-tenant policy ownership (Phase 4)
- CEL / Cedar policy DSL spike (Phase 3+)

### SECURITY CONSIDERATIONS

- **Default-deny preserved.** Baseline policy still ESCALATEs everything
  unmatched. Specific ALLOW rules require explicit operator opt-in via
  `constraints.requires_approval = false`.
- **DENY wins over equal-priority ALLOW.** No silent permissive merge.
- **Audit immutability** now enforced at two layers: DB role +
  hash-chain verifier. Each catches what the other misses.
- **PII redaction** is on by default in production; tests opt out
  explicitly via `redactor=None`. New AI providers MUST NOT see raw
  entity values.
- **Slack signature** verifies v0 HMAC with 5-min replay window.
- **Approval expiry** bounded — stale PENDING approvals move to EXPIRED
  every minute via Celery beat (no one-click forever-approvals).
- **Rollback authorization:** any authenticated user can POST to
  `/remediations/{id}/rollback`. Phase 3 will gate on role; the
  decision is logged with actor identity in the chain.

### ARCHITECTURAL DECISIONS

- **ADR-011** JSON policy DSL with opt-in autonomy per action class
- **ADR-012** Slack as the Sprint 2 approval channel; dry-run by default
- **ADR-013** PII redaction in AI prompts; per-snapshot lookup table
- **ADR-014** DB-role-level audit immutability via `aegis_audit_writer`

### FEATURES IMPLEMENTED

| Feature                                                | Status | Notes                                       |
| ------------------------------------------------------ | ------ | ------------------------------------------- |
| JSON policy DSL                                        | ✅     | 8 operators; <100 LOC evaluator             |
| `JSONPolicyEngine`                                     | ✅     | Conflict-detect; DENY wins                  |
| Seed policies (baseline-deny + 2 demo rules)           | ✅     | `make seed-policies`                        |
| PII redactor (emails, IPs, hosts, file hashes)         | ✅     | Salted tokens; per-call lookup              |
| TriageService PII redaction wired                      | ✅     | Lookup stored on snapshot evidence          |
| `aegis_audit_writer` DB role migration                 | ✅     | Idempotent CREATE ROLE                      |
| `HashChainVerifier`                                    | ✅     | Reports mismatches + link breaks            |
| Celery beat: audit verifier daily, expiry every minute | ✅     | Crontab at 03:17 UTC                        |
| `ExecutionConnector` framework + registry              | ✅     |                                             |
| `MicrosoftGraphConnector` (`revoke_user_sessions`)     | ✅     | Dry-run default; live behind env flag       |
| `StubExecutionConnector` for tests                     | ✅     |                                             |
| `Notifier` abstraction                                 | ✅     |                                             |
| `SlackNotifier` (Block Kit approval messages)          | ✅     | Dry-run default                             |
| `POST /slack/interact` webhook                         | ✅     | v0 HMAC signed; maps Slack email → User     |
| `ApprovalService` state machine                        | ✅     | request/approve/reject/expire               |
| `RemediationExecutor` (execute + rollback)             | ✅     |                                             |
| IncidentService policy-effect routing                  | ✅     | ALLOW/no-approval → autonomous              |
| REST: approvals, remediations, policies                | ✅     |                                             |
| Frontend approval inbox                                | ✅     | 5s refresh; approve/reject with note        |
| Rollback control on incident detail                    | ✅     | Audited; requires reason                    |
| Prompt disclosure on AI reasoning panel                | ✅     | Closes OQ-11; data already persisted        |
| Tests: policy DSL                                      | ✅     | 10 cases                                    |
| Tests: PII redaction                                   | ✅     | 6 cases including salt isolation            |
| Tests: audit verifier                                  | ✅     | Clean + tamper-detection + link-break       |
| Tests: e2e closed-loop                                 | ✅     | request → approve → execute → rollback      |

### FILES CREATED (32)

Backend — policy (3):
- `app/core/policy/dsl.py`, `json_engine.py`
- `app/scripts/seed_policies.py`

Backend — redaction (2):
- `app/core/redaction/__init__.py`, `pii.py`

Backend — audit (1):
- `app/core/audit/verifier.py`

Backend — execution (4):
- `app/core/execution/__init__.py`, `base.py`, `microsoft_graph.py`, `stub.py`

Backend — notifications (3):
- `app/core/notifications/__init__.py`, `base.py`, `slack.py`

Backend — services + workers (4):
- `app/services/approval_service.py`, `remediation_executor.py`
- `app/workers/tasks/audit_verifier.py`, `remediation.py`

Backend — API + schemas (7):
- `app/api/v1/approvals.py`, `remediations.py`, `policies.py`, `slack.py`
- `app/schemas/approval.py`, `policy.py`, `remediation.py`

Backend — migration (1):
- `alembic/versions/0002_audit_writer_role.py`

Backend — tests (4):
- `tests/test_policy_dsl.py`, `test_pii_redaction.py`, `test_audit_verifier.py`,
  `test_approval_executor_e2e.py`

Frontend (3):
- `src/lib/approvals.ts`
- `src/components/approvals/ApprovalCard.tsx`
- `src/pages/ApprovalInboxPage.tsx`

### FILES MODIFIED (16)

- `Makefile` — `seed` now also seeds policies; new `seed-policies` target
- `.env.example` — Slack, MS Graph, audit-writer DSN, policy lockdown
- `backend/app/config.py` — added approval / Slack / Graph / policy /
  audit-writer settings
- `backend/app/core/policy/__init__.py` — `JSONPolicyEngine` is now default
- `backend/app/core/audit/__init__.py` — export verifier
- `backend/app/core/ai/triage.py` — redact before provider call
- `backend/app/services/incident_service.py` — policy-effect routing
- `backend/app/api/v1/router.py` — include 4 new routers
- `backend/app/workers/celery_app.py` — beat schedule
- `backend/app/workers/tasks/__init__.py` — register new task modules
- `backend/app/schemas/ai_reasoning.py` — surface `prompt` field
- `frontend/src/App.tsx` — `/approvals` route
- `frontend/src/components/layout/AppShell.tsx` — approvals nav link
- `frontend/src/components/incidents/AIReasoningPanel.tsx` — prompt disclosure
- `frontend/src/lib/incidents.ts` — `prompt: string | null`
- `frontend/src/pages/IncidentDetailPage.tsx` — rollback control

### DATABASE CHANGES

Migration `0002_audit_writer_role`:

- `CREATE ROLE aegis_audit_writer LOGIN PASSWORD '<placeholder>' NOINHERIT NOCREATEDB NOCREATEROLE` (idempotent — guarded by `IF NOT EXISTS`).
- `GRANT CONNECT, USAGE ON SCHEMA public, INSERT ON audit_logs` to that role.
- Downgrade revokes grants but leaves the role itself (avoids destroying customizations).

### API CHANGES

| Method | Path                                        | Auth        | Description                                      |
| ------ | ------------------------------------------- | ----------- | ------------------------------------------------ |
| GET    | `/api/v1/approvals`                         | bearer      | List approvals; `pending_only` filter            |
| POST   | `/api/v1/approvals/{id}/decision`           | bearer      | Approve/reject with optional note                |
| POST   | `/api/v1/remediations/{id}/rollback`        | bearer      | Trigger rollback; requires reason                |
| GET    | `/api/v1/policies`                          | bearer/admin| List policies (admin only)                       |
| POST   | `/api/v1/policies`                          | bearer/admin| Create policy; DSL validated at write time       |
| POST   | `/api/v1/slack/interact`                    | Slack HMAC  | Slack interactive component callback             |

### TECHNICAL DEBT INTRODUCED

| ID   | Item                                                                                                | Owed-by Sprint |
| ---- | --------------------------------------------------------------------------------------------------- | -------------- |
| D-17 | Engine-initiated rollback is wired but no-op (only user-initiated rollback live)                   | Sprint 3       |
| D-18 | Connection pool to `aegis_audit_writer` not yet plumbed — env var read but pool not built          | Sprint 3       |
| D-19 | Policy CRUD update + delete endpoints + UI                                                          | Sprint 3       |
| D-20 | Slack-email → Aegis-user mapping is by exact email match; needs SSO link in Phase 3                | Sprint 3       |
| D-21 | Rollback authorization is "any authenticated user" — needs role gating                              | Sprint 3       |
| D-22 | PII redaction allowlist (e.g., customer's own domain stays unredacted for model context)            | Sprint 3       |
| D-23 | Cost / latency metrics for the executor (per-action-class p95)                                      | Sprint 3       |
| D-24 | Microsoft Graph token caching (currently fetch-per-call)                                            | Sprint 3       |
| D-25 | The IncidentService `_winning_policy_requires_approval` re-queries the DB — surface `constraints`   | Sprint 3       |

(Open from prior sprints: D-3, D-6, D-7, D-8, D-9, D-10, D-12, D-13, D-14, D-15, D-16.)

### RISKS IDENTIFIED

| ID   | Risk                                                                                                  | Likelihood | Impact   | Mitigation                                                                |
| ---- | ----------------------------------------------------------------------------------------------------- | ---------- | -------- | ------------------------------------------------------------------------- |
| R-13 | DSL too restrictive — first customer rule we can't write triggers a costly refactor                    | Medium     | Medium   | Migration triggers documented in ADR-011 — switch to CEL/Cedar at first miss |
| R-14 | Slack signing-secret rotation breaks the inbound webhook silently                                      | Medium     | High     | Boot-time check verifies the signing secret is set in prod; alarms on 401  |
| R-15 | MS Graph dry-run mode confuses operators into thinking action ran — incident shows EXECUTED but nothing happened | High       | Medium   | Status panel shows `dry_run=true`; UI labels "no-op" badges (Sprint 3 D-23 closes the gap with metrics) |
| R-16 | Audit verifier finds a mismatch and pages on a false positive (canonicalization changes silently)      | Low        | Medium   | Canonicalization is one function (`_compute_entry_hash`); any change there bumps a verifier version pin |
| R-17 | Approval expiry race: approver clicks Approve at minute 59:59 while beat task fires                    | Low        | Low      | The state machine's "not PENDING" guard catches it — approval fails fast    |
| R-18 | Token tokens (`<user:8e2f>`) collide across snapshots and confuse the model                            | Low        | Low      | Salt is per-snapshot; collisions cross-snapshot are not semantic (model never sees both) |

### ROLLBACK STRATEGY

- **Schema:** migration `0002_audit_writer_role` is reversible; downgrade
  revokes grants but leaves the role.
- **Policy:** set `AEGIS_POLICY_ENGINE_FORCE_STUB=true` to revert to
  Phase 1 always-escalate behavior in a hot lockdown.
- **Slack / Graph:** both are env-flag gated (`AEGIS_SLACK_ENABLED`,
  `AEGIS_MS_GRAPH_LIVE`); flipping false reverts to dry-run instantly.
- **Frontend:** routes are additive; removing `/approvals` doesn't
  affect incidents flow.

### KNOWN LIMITATIONS

1. **MS Graph dry-run is the default.** A demo shows everything working
   end-to-end without actually revoking sessions — clearly labelled
   `dry_run=true` in the execution result and audit chain.
2. **Slack dry-run is the default.** Approval requests render in logs
   only when `AEGIS_SLACK_ENABLED=false`.
3. **Engine-initiated rollback** (`workflows.execute_remediation__rollback`)
   is plumbed but no-op in Phase 2. Real triggers (failed mid-batch
   execution, policy revocation) ship in Phase 3.
4. **Audit-writer connection pool** is plumbed in env / migration but
   the audit logger doesn't yet open a second pool. D-18.
5. **Connectors for non-Microsoft platforms** (Okta, CrowdStrike, AWS
   IAM) are not yet present. Coming in Phase 3.

### OBSERVABILITY (current state)

- **Logs:** new structured events: `policy.match`, `policy.eval_skipped`,
  `slack.dry_run`, `ms_graph.dry_run.revoke_user_sessions`,
  `approval.requested`, `approval.decided`, `approval.expired_batch`,
  `remediation.executed`, `remediation.rollback`,
  `audit.verifier.ok` / `audit.verifier.MISMATCH`.
- **Audit chain:** every state transition writes an entry — see e2e test
  for the canonical list.
- **Metrics / traces:** still not wired (D-3, planned Phase 3).

### NEXT STEPS — Sprint 03 candidate scope

Working title: **"Production posture."**

Proposed objective: take the closed loop from "demoable" to "shippable
to a design partner." OTel collector wiring, real audit-writer
connection pool, multi-channel notifications, role-gated rollback,
Microsoft Graph token caching, and the first non-Microsoft connector
(Okta or CrowdStrike — pick one).

Specifically:

1. **OTel collector + traces + metrics + Grafana dashboards (D-3).**
2. **Audit-writer connection pool actually used (D-18).**
3. **Role-gated rollback + policy CRUD update/delete (D-19, D-21).**
4. **Multi-channel notifications:** Email + Web (D-23).
5. **PII allowlist + reasoning quality eval (D-22).**
6. **MS Graph token caching (D-24).**
7. **Pick one: Okta connector or CrowdStrike isolate_host connector**
   — depends on Q3 (design-partner ICP).
8. **Per-tenant AI budget cap + cost surfacing.**
9. **Frontend: policy editor UI, audit-chain explorer.**

Carry-over: every prior-sprint D-item not closed above.

### OPEN QUESTIONS

| ID    | Question                                                                                                | Needed by |
| ----- | ------------------------------------------------------------------------------------------------------- | --------- |
| OQ-13 | Phase 3 second execution connector — Okta or CrowdStrike?                                              | Sprint 3  |
| OQ-14 | Audit-chain export format — JSONL signed receipt? PDF for compliance officers?                          | Sprint 3  |
| OQ-15 | Should `requires_approval=false` ALLOW rules need a "training period" with shadow runs first?           | Sprint 3  |
| OQ-16 | Policy editor UX — JSON editor with schema validation, or a visual rule builder?                        | Sprint 3  |
| OQ-17 | Per-tenant AI budget cap — hard stop, soft warning + escalate, or both with separate thresholds?        | Sprint 3  |

---

## STRATEGIC PRODUCT QUESTIONS — Sprint 02 closeout

> Sprint 00 + 01 strategy questions still stand. New ones surfaced by the
> closed-loop work:

### 1. The "first real action" demo moment

The product is now demoable end-to-end. Q17 picked Microsoft Graph
`revoke_user_sessions` — non-reversible by design. The first prospect
demo will trigger it.

  - **Q19.** Do we lead the demo with the non-reversible action (revoke)
    or with a fully-reversible one (notify_slack, open_jira_ticket)? The
    former is the dramatic moment; the latter is the trust posture. My
    recommendation is **lead reversible, escalate to non-reversible at
    Q&A** — proves "rollback-first" before forcing the prospect to
    grapple with "the AI did the thing."

### 2. The MITRE provenance question (OQ-10 redux)

We now have both source-provided MITRE techniques (Defender's
`mitreTechniques` field) and LLM-derived ones (in the structured
output). The product currently stores them separately.

  - **Q20.** Surface both in the UI side-by-side, or merge into one
    "Aegis-attested" list with provenance metadata per technique? The
    latter is cleaner for an analyst but obscures disagreement which is
    itself a useful signal.

### 3. The compliance-export wedge

The audit chain is hash-verified, tamper-evident, append-only, and
attributable to a specific AI model + prompt version. That's
unusually rare in the SOC tool stack.

  - **Q21.** Should Sprint 3 ship an **audit export endpoint** that
    produces a signed JSONL receipt suitable for SOC 2 / ISO 27001
    evidence collection? It's a Phase 3 wedge that doesn't show up on
    most competitor checklists.

### 4. The "approval inbox vs. ChatOps" question

We built a web-based approval inbox. Slack also has approve/reject
buttons inline. Most operators will live in Slack.

  - **Q22.** Do we invest Sprint 3 effort in making the web inbox
    feature-complete (filters, mobile, search) or push hard on
    **Slack-first UX** — bringing the *incident detail* and *AI
    reasoning panel* into Slack via modals + threads? The latter
    reduces context-switching for the analyst, which IS the operational
    pain point.

### 5. Self-hosted vs. SaaS again (Q7 redux)

Sprint 2 added MS Graph + Slack as outbound integrations. Both have
self-hosted-friendly patterns (private workspace, customer's own AAD).

  - **Q23.** With the closed loop working, the **on-prem demo for
    regulated FinServ / Healthcare** is now feasible. Does that change
    the design-partner conversation? Specifically: is the **first paid
    customer** more likely to be a mid-market SaaS SOC (Slack-native,
    SaaS-comfortable) or a regulated enterprise running on-prem?

### 6. Pricing for autonomous actions specifically

Sprint 1 raised pricing questions (per-alert, per-seat, per-action,
flat). Sprint 2 makes the per-action axis concrete.

  - **Q24.** Should an *autonomously-executed* action cost more than an
    *approved-by-human* one? Pricing-wise the AI value is in the
    autonomous path; operationally, the customer is paying for
    governance trust whether the AI ran or a human did. Pick a frame.

---

> End of Sprint 02. Next entry: **Sprint 03 — Production posture.**

---

## SPRINT 03 — PRODUCTION POSTURE

- **DATE:** 2026-05-28
- **STATUS:** Delivered. Awaiting review before Sprint 4 kickoff.
- **DURATION:** 1 day
- **OWNER:** Principal Architect (claude-opus-4-7)

### SPRINT OBJECTIVE

Harden the demo loop toward a production posture by: using the dedicated
audit-writer role for insert-only audit writes, providing a compliance-
grade audit export, completing policy CRUD endpoints, gating rollback on
role, and improving connector token behaviour (MS Graph token cache).

### TECHNICAL SCOPE

In scope:

- Use the `AEGIS_AUDIT_WRITER_DATABASE_URL` when present so audit INSERTs
  use the `aegis_audit_writer` role / pool instead of the main DB pool.
- `GET /api/v1/audit/export` — NDJSON (JSONL) export endpoint for
  compliance receipts (admin-only, optional `since` filter).
- Policy CRUD: `GET/PUT/DELETE /api/v1/policies/{id}` (admin-only) and
  server-side DSL validation at write-time.
- Role-gated rollback: only `operator` or `admin` may POST
  `/api/v1/remediations/{id}/rollback` (prevents unauthorised rollbacks).
- Microsoft Graph connector: simple in-process access-token caching to
  reduce client-credentials churn.
- Regression tests: `tests/test_audit_export.py` plus related test
  adjustments for approval/rollback flows.

Out of scope:

- Full OTel collector + traces/metrics dashboards (still Sprint 3 target
  item D-3 to be completed in follow-up).
- Policy editor UI and multi-channel approval delivery (Phase 3).

### SECURITY CONSIDERATIONS

- Audit exports are admin-only and should be requested only by
  authorized compliance processes.
- Operators must rotate the `aegis_audit_writer` password after running
  the migration; the app will use the DSN only when `AEGIS_AUDIT_WRITER_DATABASE_URL`
  is configured.
- Rollback endpoint now requires `operator` or `admin` role.

### FEATURES IMPLEMENTED

- Audit-writer pool wiring + commit path when `AEGIS_AUDIT_WRITER_DATABASE_URL` set
- `GET /api/v1/audit/export` (NDJSON) — admin-only
- Policy CRUD: get / put / delete endpoints added with DSL validation
- Role-gated rollback on remediations
- MS Graph token caching (in-process) to reduce token fetches
- Test: `backend/tests/test_audit_export.py`

### FILES CREATED / MODIFIED (selection)

- Created: `backend/app/api/v1/audit.py`, `backend/tests/test_audit_export.py`
- Modified: `backend/app/db.py`, `backend/app/core/audit/logger.py`,
  `backend/app/api/v1/policies.py`, `backend/app/api/v1/remediations.py`,
  `backend/app/api/v1/approvals.py`, `backend/app/logging.py`,
  `backend/app/core/execution/microsoft_graph.py`

### DATABASE CHANGES

No new migrations required for Sprint 3 — Alembic `0002_audit_writer_role`
already created the `aegis_audit_writer` role and grants in Sprint 2.

### TECHNICAL DEBT (updates)

- **D-18 (done):** audit-writer connection pool now plumbed and used when configured.
- **D-19 (partial):** Policy CRUD update/delete endpoints added; UI still required.
- **D-21 (done):** Rollback authorization tightened to `operator|admin`.
- **D-24 (done):** MS Graph token caching implemented (in-process). 
- Remaining debt: D-3, D-7, D-23, D-24 (further improvements), D-25, and others from prior sprints.

### RISKS IDENTIFIED

- Audit export must be used with care — the endpoint bypasses UI-level
  paging and can produce large payloads; operator training and limits
  should be applied before enabling broadly.
- In-process token cache is adequate for low-volume demo traffic but
  will need a resilient shared cache (Redis) before high-volume
  operation.

### NEXT STEPS — Sprint 04 candidate scope

1. OTel collector + traces + metrics + Grafana dashboards (complete D-3).
2. Policy editor UI + policy CRUD UX polish.
3. Audit export signing and JSONL receipt (signed export for compliance).
4. Move token cache to shared cache (D-24 follow-up).
5. Role-gated rollback policies (fine-grained RBAC and audit reviewer).

---

> End of Sprint 03. Next entry: **Sprint 04 — Compliance posture.**

---

## SPRINT 04 — COMPLIANCE POSTURE

- **DATE:** 2026-05-29
- **STATUS:** Delivered. Awaiting review before Sprint 5 kickoff.
- **DURATION:** 1 day
- **OWNER:** Principal Architect (claude-opus-4-7)

### SPRINT OBJECTIVE

Turn the audit trail into something an external compliance officer can
verify offline, give them an account that can only do what they need,
and tighten the rollback gate so the most consequential undo actions
require a senior actor on record.

This is the **compliance wedge** from Sprint 02's Q21 — the bet is that
"give me a signed, verifiable transcript of every AI decision" is the
single capability incumbents can't trivially match without rebuilding
their audit pipeline.

### TECHNICAL SCOPE

In scope:

- **Signed audit-export receipts** (ADR-015). Each NDJSON export now
  ends with a `{"receipt": true, ..., "signature": "<hex>"}` line. The
  signature is Ed25519 over the canonical JSON of the receipt minus
  the `signature` field, using a key configured via
  `AEGIS_AUDIT_EXPORT_SIGNING_KEY`. The receipt carries `head_entry_hash`
  (last exported entry), `tip_entry_hash` (chain tip at snapshot time),
  `content_hash` (SHA-256 over the ordered entry hashes), exporter
  identity, `signing_key_id`, and ISO timestamps.
- **Standalone verifier** (`python -m app.scripts.verify_audit_export
  --file ... --public-key ...`) that re-derives every check from the
  file alone — no DB access.
- **REVIEWER user role** (ADR-016) with read access to audit export,
  policies, incidents, approvals; no mutation rights.
- **Fine-grained rollback RBAC** (ADR-017): reversible classes →
  `operator|admin`, non-reversible (REVOKE_USER_SESSIONS,
  FORCE_PASSWORD_RESET, NOTIFY_SLACK, CUSTOM) → `admin` only.
- **`RemediationActionClass.is_reversible`** property + private
  `_NON_REVERSIBLE_ACTIONS` frozenset as the single source of truth.
- **Reusable role deps** (`AdminDep`, `AdminOrOperatorDep`,
  `AdminOrReviewerDep`) in `app.api.deps`.
- **Export endpoint records itself.** Every `/audit/export` call writes
  an `audit.exported` entry to the chain (captured AFTER the export's
  tip snapshot, so it's visible to the *next* export, not this one).

Explicitly out of scope:

- Policy editor UI / audit-chain explorer UI (frontend Sprint 5).
- Multi-channel notifications (Email + Web) — deferred.
- Per-tenant signing keys / KMS integration — single key for now.
- OTel observability (still owed; D-3).

### SECURITY CONSIDERATIONS

- **Default require_signature=true.** Hitting `/audit/export` in
  production without a signing key configured returns `503` rather than
  emitting an unsigned export. Local dev can pass
  `?require_signature=false` to get an explicitly-unsigned receipt
  (`"signature": null`).
- **No HMAC for receipts.** The verifier needs only the public key —
  the auditor cannot forge a receipt even if they hold their own copy.
- **Snapshot-before-record.** The receipt's `tip_entry_hash` is captured
  before the export is itself audited. The "audit.exported" entry lives
  on the chain but does not appear in *this* export (preventing
  circularity).
- **`CUSTOM` defaults to non-reversible.** Unknown blast radius = fail
  closed.
- **Reviewer can read everything compliance needs**, and nothing else.
  They cannot decide approvals (still gated by `approval_required_role`)
  or trigger rollbacks (`UserRole.ADMIN`/`OPERATOR` only at the API
  edge).

### ARCHITECTURAL DECISIONS

- **ADR-015** Signed audit-export receipts via Ed25519
- **ADR-016** REVIEWER role for compliance read-only access
- **ADR-017** Rollback authorization scales with action reversibility

### FEATURES IMPLEMENTED

| Feature                                            | Status | Notes                                              |
| -------------------------------------------------- | ------ | -------------------------------------------------- |
| Ed25519 signed export receipts                     | ✅     | `app/core/audit/export_signer.py`                  |
| Standalone verifier CLI                            | ✅     | `app/scripts/verify_audit_export.py`               |
| `REVIEWER` user role                               | ✅     | `UserRole.REVIEWER`                                |
| `AdminDep` / `AdminOrOperatorDep` / `AdminOrReviewerDep` | ✅ | Single-line role gating at endpoint signature    |
| Reviewer access on `/audit/export`                 | ✅     | `AdminOrReviewerDep`                               |
| Reviewer access on `GET /policies(/{id})`          | ✅     |                                                    |
| Reviewer access on `GET /incidents(/{id})`         | ✅     | Already authenticated-only; reviewer included      |
| `RemediationActionClass.is_reversible` classifier  | ✅     | Single source of truth for the rollback gate       |
| Rollback fine-grained RBAC                         | ✅     | Non-reversible classes require admin               |
| `audit.exported` entry on every export             | ✅     | Captured after tip snapshot                        |
| `?require_signature=` toggle                       | ✅     | Default true; false yields explicitly-null sig     |
| Tests: signer unit                                 | ✅     | 8 cases                                            |
| Tests: signed export e2e                           | ✅     | Includes tampering & reviewer-access cases         |
| Tests: rollback RBAC matrix                        | ✅     | Operator/admin × reversible/non-reversible         |
| Tests: reviewer role access matrix                 | ✅     |                                                    |

### FILES CREATED (5)

- `backend/app/core/audit/export_signer.py`
- `backend/app/scripts/verify_audit_export.py`
- `backend/tests/test_export_signer.py`
- `backend/tests/test_rollback_rbac.py`
- `backend/tests/test_reviewer_role.py`

### FILES MODIFIED (9)

- `backend/app/api/deps.py` — three named role deps
- `backend/app/api/v1/audit.py` — signed receipt + reviewer access +
  snapshot semantics
- `backend/app/api/v1/policies.py` — reviewer access on GETs
- `backend/app/api/v1/remediations.py` — reversibility-aware RBAC
- `backend/app/config.py` — `audit_export_signing_key` +
  `audit_export_signing_key_id`
- `backend/app/models/user.py` — `UserRole.REVIEWER`
- `backend/app/models/remediation_action.py` — `is_reversible` property
- `backend/tests/test_audit_export.py` — rewritten for new receipt
  format + reviewer-allowed + signing key paths
- `docs/DECISIONS.md` — ADRs 015–017

### DATABASE CHANGES

**None.** `UserRole` is stored as a `VARCHAR` with non-native-enum
SQLAlchemy mapping, so adding `REVIEWER` does not require a migration.

### API CHANGES

| Method | Path                                | Auth                | Description                                  |
| ------ | ----------------------------------- | ------------------- | -------------------------------------------- |
| GET    | `/api/v1/audit/export`              | admin or reviewer   | Now ends with a signed receipt line          |
| GET    | `/api/v1/policies`                  | admin or reviewer   | Was admin-only; reviewer added               |
| GET    | `/api/v1/policies/{id}`             | admin or reviewer   | Was admin-only; reviewer added               |
| POST   | `/api/v1/remediations/{id}/rollback`| operator/admin (rev.); admin (non-rev.) | Authorization now action-class-sensitive |

New query params on `/audit/export`:

- `require_signature` (bool, default `true`): when false and no key is
  configured, returns an unsigned receipt with `"signature": null`
  instead of `503`.

### TECHNICAL DEBT INTRODUCED

| ID   | Item                                                                                                  | Owed-by Sprint |
| ---- | ----------------------------------------------------------------------------------------------------- | -------------- |
| D-26 | Single signing key — no rotation / KMS. Move to envelope encryption + per-env keys.                   | Sprint 5       |
| D-27 | `signing_key_id` is a free-form string; no registry / metadata file mapping id → public key.          | Sprint 5       |
| D-28 | Verifier CLI is offline-only — no helper to fetch the public key from a `/.well-known/...` endpoint. | Sprint 5       |
| D-29 | Reviewer cannot read `/audit/{entry_id}` because that endpoint does not exist yet — only export.     | Sprint 5       |
| D-30 | `entries_digest` is custom (not RFC 8785 JCS). Document or migrate before any external interop.       | Sprint 6       |
| D-31 | Approval-channel role mapping still string-compared (`approval_required_role`) — reviewer noise risk. | Sprint 5       |

(Open from prior sprints: D-3, D-7, D-22, D-23, D-25, plus partially-closed Sprint 03 items.)

### RISKS IDENTIFIED

| ID   | Risk                                                                                                        | Likelihood | Impact   | Mitigation                                                                       |
| ---- | ----------------------------------------------------------------------------------------------------------- | ---------- | -------- | -------------------------------------------------------------------------------- |
| R-19 | Signing key leak from env → forged exports are indistinguishable from genuine                                | Low        | High     | D-26 (rotation + KMS). For now: vault the env, alarm on key reads.               |
| R-20 | Receipt canonicalization drift between writer and verifier produces false-negative verifications              | Low        | Medium   | Single `_canonical_bytes()` reused on both sides; ADR pins the rule              |
| R-21 | Reviewer accidentally granted write privileges by future endpoint that uses `CurrentUserDep` instead of `AdminDep` | Medium | Medium   | Lint rule / review checklist; consider an `AnyAuthenticatedNonReviewerDep` later |
| R-22 | Non-reversible classification becomes outdated when a new action class is added without an `is_reversible` opinion | Medium | Medium | Default for `CUSTOM` is non-reversible (fail-closed); future ADR adds a `is_reversible=False` test invariant |
| R-23 | `?require_signature=false` in prod (operator error) produces unsigned exports with `"signature": null`        | Medium | High     | Server should refuse `require_signature=false` when `env in {staging,prod}` — follow-up |

### ROLLBACK STRATEGY

- **Schema:** no migrations.
- **Signing key:** unset `AEGIS_AUDIT_EXPORT_SIGNING_KEY` to revert
  exports to unsigned-with-null-signature (callers must also pass
  `?require_signature=false`).
- **Reviewer role:** revoking the role from a user via the seed/SSO
  mapping immediately removes access. The enum value can stay even if
  no user has it.
- **Rollback RBAC:** to revert to Sprint 03's blanket
  `operator|admin`, remove the `is_reversible` check at the API edge
  (keep the property itself — it has no other callers yet).

### KNOWN LIMITATIONS

1. **One signing key, hand-managed.** No rotation, no KMS integration
   (D-26).
2. **No bulk auditor onboarding flow.** Creating a reviewer is the
   same admin DB write as creating any other user.
3. **Verifier CLI is online-key only.** If you want to verify an
   export from yesterday with last week's key, you need both PEMs at
   hand (D-27/D-28).
4. **R-23 not yet mitigated.** Production should refuse the
   `require_signature=false` escape hatch — current implementation
   honors it regardless of env.

### OBSERVABILITY (current state)

- **Logs:** new structured events: `audit.export.completed` (with
  signed/unsigned flag), `rollback.denied.non_reversible`,
  `audit.exported` (audit-chain entry).
- **Audit chain:** every export request appears as `audit.exported` in
  the next export. Rollback denials due to non-reversibility do NOT
  hit the audit chain (they're 403s at the API edge before the
  executor sees them); R-21 makes this slightly load-bearing —
  consider auditing denials in Sprint 5.

### NEXT STEPS — Sprint 05 candidate scope

Working title: **"Operational visibility + observability."**

The compliance bones are now solid. Sprint 5 should turn the system
inside-out for operators:

1. **OTel collector + traces + metrics + Grafana dashboards (D-3 —
   carried for the third sprint running; needs to land).**
2. **Signing-key rotation + key registry (D-26, D-27).**
3. **`/.well-known/aegis-audit-public-key` endpoint (D-28).**
4. **Audit-chain explorer UI** — let an analyst (or reviewer) browse
   the chain in the app rather than via a downloaded NDJSON.
5. **Production guardrail: refuse `require_signature=false` in
   non-local env (R-23).**
6. **Approval-channel reviewer-noise fix (D-31).**
7. **Audit denial events** for rollback 403s (R-21 mitigation).

Carry-over: prior open D-items (D-3, D-7, D-22, D-23, D-25, plus
freshly-introduced D-26 through D-31).

### OPEN QUESTIONS

| ID    | Question                                                                                                | Needed by |
| ----- | ------------------------------------------------------------------------------------------------------- | --------- |
| OQ-18 | KMS choice — AWS KMS, GCP KMS, HashiCorp Vault, or self-managed?                                       | Sprint 5  |
| OQ-19 | Should the public-key endpoint be unauthenticated (truly well-known) or scoped to authenticated users?  | Sprint 5  |
| OQ-20 | Audit chain UI — read-only view, or read + "request export of this range" inline?                       | Sprint 5  |
| OQ-21 | Do we need a tenant-scoped signing key from day one, or is single-key acceptable for the first design partner? | Sprint 5  |

---

## STRATEGIC PRODUCT QUESTIONS — Sprint 04 closeout

> Prior sprints' strategy questions still stand. New ones surfaced by
> the compliance wedge:

### 1. The signed-receipt as a sales artifact

We now produce an artifact that's directly relevant to SOC 2 / ISO 27001
evidence collection. Auditors get a downloadable transcript they can
verify offline against a published public key. No incumbent SOAR / SIEM
currently ships this.

- **Q25.** Do we lead the next round of buyer conversations with the
  signed receipt as the *primary* differentiator (governance-first
  pitch), or does it stay in the "and by the way…" portion of the demo?
  My recommendation: **lead with it for regulated-industry buyers (Q3
  option c), keep it as a closer for SaaS SOCs**. Different buyers
  weight it differently.

### 2. KMS-or-self-managed choice for the signing key

We currently load the private key from `AEGIS_AUDIT_EXPORT_SIGNING_KEY`
(PEM in env). Production rotation needs a real story.

- **Q26.** Is the signing key something *we* manage (managed-service
  cost, simpler customer story) or something the **customer's KMS**
  signs with (no Anthropic-side liability if a customer's auditor
  contests authenticity)? The latter is the harder build but it's the
  posture that matches "your audit, your key, your auditor's trust."

### 3. The reviewer-role go-to-market

We can hand a reviewer login to a prospect's compliance officer during
a pilot. They can verify the system from their side without operator
access.

- **Q27.** Is the **"compliance pilot"** a sales motion we want to
  formalize — i.e., during the design-partner phase, we explicitly
  offer the buyer's compliance org a reviewer account and walk them
  through running the verifier CLI? This makes them an *ally* during
  procurement.

### 4. Where the wedge points next

Sprint 02 raised Q19 (lead-with-reversible vs non-reversible demo).
Sprint 04 makes a related question concrete: when a non-reversible
action gets rolled back, an admin had to make that call. That's a
*great* discussion artifact.

- **Q28.** Should we surface the "non-reversible rollback decisions
  this week" as a dedicated weekly digest for CISOs? It's a small
  feature with outsized signal value — it tells the buyer exactly the
  kind of decisions their senior staff are making, in a format that
  reads like a board-deck slide.

---

> End of Sprint 04. Next entry: **Sprint 05 — Operational visibility + observability.**
