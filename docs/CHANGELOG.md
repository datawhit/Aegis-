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
