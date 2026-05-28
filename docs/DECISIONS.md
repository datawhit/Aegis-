# Aegis — Architectural Decision Records

> Append-only. Each ADR is dated. Never edit a `Status: Accepted` ADR
> in place — supersede it with a new one.

---

## ADR-001 — Lean MVP foundation over enterprise stack day 1

- **Date:** 2026-05-27
- **Status:** Accepted
- **Context:** The master prompt frames Aegis as enterprise-grade. The
  pull is strong to add Temporal, LocalStack, OTel collector, Vault,
  service mesh on day 1. Doing so pushes first feature delivery (alert
  ingestion + AI triage) 2–3 sprints out with no user-facing value.
- **Decision:** Phase 0 ships the **lean foundation**: Postgres + pgvector,
  Redis, FastAPI, Celery, Vite frontend. All other infra is **deferred but
  designed-for** via abstractions (see ADR-002, ADR-003).
- **Consequences:**
  - + Sprint 1 starts with real product work, not infra
  - + Smaller blast radius for early changes
  - – We will pay a one-time migration cost when we add Temporal / OTel /
    Vault. Acceptable because the abstractions keep the migration
    mechanical, not architectural.

---

## ADR-002 — Celery first, Temporal-ready (workflow engine abstraction)

- **Date:** 2026-05-27
- **Status:** Accepted
- **Context:** Temporal is the right long-term answer for durable, replayable,
  rollback-safe security workflows. Adding it on day 1 means running Temporal
  Server locally + a learning curve before any value ships.
- **Decision:** Define `WorkflowEngine` as a protocol. Ship
  `CeleryWorkflowEngine` in Phase 0. Stub `TemporalWorkflowEngine` so the
  migration is plug-and-play.
- **Migration triggers (any one is sufficient):**
  1. We need cross-step retry with strict state durability
  2. Any single workflow exceeds ~15 min wall-clock
  3. We need historical workflow replay for audit/debugging
  4. Multi-step rollback orchestration becomes load-bearing
- **Consequences:**
  - + Faster path to Sprint 1
  - – Some Celery patterns (e.g., chord/group) won't have 1:1 Temporal
    equivalents; we'll need to keep workflow definitions in terms of the
    abstraction, not Celery primitives. The `WorkflowEngine` interface
    deliberately constrains us to `submit / status / cancel / rollback`.

---

## ADR-003 — Local JWT now, Okta-ready (identity abstraction)

- **Date:** 2026-05-27
- **Status:** Accepted
- **Context:** Audit log entries reference actor IDs. Without auth scaffolding
  in Phase 0, every entry would be `actor=system`, polluting the chain and
  forcing a retrofit.
- **Decision:** `IdentityProvider` protocol. `LocalJWTIdentityProvider` for
  Phase 0 (HS256, users table). `OktaIdentityProvider` stub present.
- **Consequences:**
  - + Audit log has real actor identities from day 1
  - + SSO swap is a single line in DI wiring
  - – We carry a local users table even after SSO lands; we'll keep it for
    service accounts and break-glass admin.

---

## ADR-004 — Tamper-evident audit log via SHA-256 hash chain

- **Date:** 2026-05-27
- **Status:** Accepted
- **Context:** "Append-only audit log" is the product's trust spine. We
  need detection of after-the-fact tampering, not just absence of
  application-level update paths.
- **Decision:** Each `audit_logs` row stores `prev_hash` and `entry_hash`.
  `entry_hash = SHA256(canonical_json(prev_hash || actor || action || resource || payload || timestamp))`.
  Background job re-walks the chain on a schedule (Sprint 2+) and alerts
  on mismatch.
- **Alternatives considered:**
  - External log (e.g., AWS QLDB): heavier dependency, less control,
    AWS-coupled.
  - Merkle tree with periodic anchoring: better for very-high-volume
    auditing; overkill at our expected volume. Revisit at 1M+ entries/day.
- **Consequences:**
  - + Lightweight, self-contained, portable
  - – Insert path costs one extra SELECT for the tip hash. Mitigated by
    keeping a cached `chain_tip` row.

---

## ADR-005 — Default-deny + escalate-on-uncertainty for the policy engine

- **Date:** 2026-05-27
- **Status:** Accepted
- **Context:** The PolicyEngine is the trust boundary. Its failure modes
  must be safe.
- **Decision:**
  - If no policy matches → `ESCALATE`
  - If policies conflict → `ESCALATE` (do not silently pick most permissive)
  - If evaluation raises → `ESCALATE` (never `ALLOW`)
  - `ALLOW` requires explicit match AND confidence ≥ threshold AND blast
    radius ≤ cap AND rollback plan defined
- **Consequences:**
  - + Failure mode is "ask a human", not "act anyway"
  - – Higher escalation volume early on; expected, and the analytics layer
    surfaces it as a tuning signal.

---

## ADR-006 — Defer DB-role-level audit log immutability to Sprint 2

- **Date:** 2026-05-27
- **Status:** Accepted (with follow-up)
- **Context:** True immutability requires a Postgres role that has only
  INSERT on `audit_logs`. Setting this up means two DB users in
  docker-compose, two connection pools in the app, and migration tooling
  for role grants.
- **Decision:** Phase 0 enforces append-only at the application layer only
  (no UPDATE/DELETE code paths exist). Sprint 2 introduces the
  `aegis_audit_writer` role and connection pool.
- **Risk:** Until Sprint 2 lands, a compromised app process could
  technically run arbitrary SQL. Mitigation: hash chain still catches
  tampering on re-walk; this is detection, not prevention.

---

## ADR-007 — AIProvider abstraction, Claude Sonnet 4.6 default

- **Date:** 2026-05-27 (Sprint 01)
- **Status:** Accepted
- **Context:** The triage engine needs LLM access; the master prompt says
  "Claude/OpenAI APIs" without picking one. Hardcoding either ties the
  audit chain's `ai_reasoning_snapshots.provider` field to a specific
  vendor's lifecycle (deprecations, pricing, rate-limit policies).
- **Decision:** Define `AIProvider` as a protocol with a single method
  (`triage_alert`) that returns a validated `TriageOutput`. Ship
  `AnthropicAIProvider` using `claude-sonnet-4-6` + tool_use for
  structured output. Stub `OpenAIAIProvider` so the provider selector
  fails-loud on misconfig.
- **Why Sonnet 4.6, not Opus:** Triage is high-volume per-alert
  classification. Sonnet's cost profile is right for that workload at
  the expected 1k–10k alerts/day; Opus is over-spec. We can route
  *specific* low-volume / high-stakes flows (Sprint 3+ remediation
  decision review) to Opus selectively without changing the abstraction.
- **Provider failure modes:** schema-violating tool_use, refusals, network.
  All three collapse to `AIProviderError` → TriageService synthesizes a
  conservative fallback (severity=MEDIUM, confidence=NULL,
  suggested_action_class=null). The policy engine ESCALATEs the result by
  the ADR-005 invariants. No alert is ever silently dropped.
- **Consequences:**
  - + Provider swap is a one-line DI change; reasoning chain stays intact.
  - + No alert is dropped on AI failure — we degrade to "ask a human".
  - – We pay one Anthropic-SDK dependency. Acceptable; the SDK is small.

---

## ADR-008 — Aegis-canonical HMAC for webhook ingestion, replay-window 5 min

- **Date:** 2026-05-27 (Sprint 01)
- **Status:** Accepted (Phase 1 scope)
- **Context:** Each source system (Defender, Okta, Slack…) has its own
  webhook signing scheme. Supporting the native scheme for each source
  means N implementations on day 1, and most of our customers will be
  self-deployed in Phase 1 — they configure both ends.
- **Decision:** Use an **Aegis-canonical** HMAC scheme for all sources in
  Phase 1: SHA-256 over `f"{ts}." || raw_body` with a 5-minute replay
  window. Per-source secret in env (`AEGIS_INGEST_SECRET_<SOURCE>`);
  moves to DB / Vault in Phase 3 once we have multi-tenant + key rotation
  pressure (D-10).
- **Failure-mode policy:** All HMAC failures collapse to a single 401
  without distinguishing reason in the response — log specifics
  internally; do not leak which check failed. Rejections still produce an
  audit-log entry so brute-force attempts show up in the chain.
- **Alternatives considered:**
  - **Native per-source schemes** (Defender JWTs, Okta HMAC, Slack v0
    signing). Right answer at scale; wrong cost in Phase 1.
  - **mTLS-only.** Strongest, but most of our pilot customers won't have
    the cert ops chops. Revisit for enterprise contracts.
- **Consequences:**
  - + One implementation; testable; rotatable.
  - – Adapter work needed in Phase 2 to accept native source schemes for
    customers who can't have us in front of their webhooks.

---

## ADR-009 — Alert→Incident correlation via `correlation_key` + sliding window

- **Date:** 2026-05-27 (Sprint 01)
- **Status:** Accepted (Phase 1 cut)
- **Context:** Once alerts ingest at scale, we need to cluster related
  alerts into a single incident. The temptation is to build an
  embeddings-based correlation engine on day 1; the cost is high and the
  payoff is unclear before we see real customer data.
- **Decision:** Phase 1 correlates by **`correlation_key`** (set by the
  normalizer; e.g. `defender:incident:<id>`, or fallback hash of
  `category + primary affected entity`) with a **sliding window** (default
  30 min, configurable). New alerts whose `correlation_key` matches an
  open incident in the window roll into that incident; otherwise create
  new.
- **Why this works for Phase 1:**
  - Defender already does its own grouping via `incidentId` — we ride on
    it where present and only fall back to our hash otherwise.
  - The 30-minute window matches the duration of most real account-takeover
    + lateral-movement chains in the public threat intel data.
  - It's a *deterministic* rule, which makes it auditable and replay-safe.
- **Migration path:** Phase 4 adds **embeddings-based correlation**
  (pgvector index already enabled in Phase 0). The interface — "give the
  service a new alert, get back an incident" — does not change. Internal
  implementation does.
- **Consequences:**
  - + Trivial to understand, debug, and tune via one knob.
  - – False splits when distinct campaigns share a primary entity (a
    user). Acceptable in Phase 1; analytics in Phase 3 surface this rate.

---

## ADR-010 — Triage runs async via the WorkflowEngine, not inline on ingest

- **Date:** 2026-05-27 (Sprint 01)
- **Status:** Accepted
- **Context:** The ingest endpoint receives webhooks. Sources expect
  fast 2xx responses (Defender retries on >5s); running an LLM call
  inline can blow the timeout, and a webhook-time LLM cost is also a DoS
  vector (an attacker pumping crafted webhooks).
- **Decision:** Ingest persists the alert + audit entry + submits a
  `triage_alert` workflow run via `WorkflowEngine.submit()` — which is
  **idempotent on `idempotency_key`**, so webhook redeliveries can't
  double-charge AI. The actual triage happens in a Celery worker.
- **Consequences:**
  - + Ingest latency is bounded by DB + broker enqueue (~10ms).
  - + DoS exposure on AI cost is bounded by Celery worker concurrency
    (configurable per env).
  - – Adds latency between "alert arrives" and "incident visible in UI".
    Acceptable — operationally, MTTR is measured from human action, not
    from row-creation timestamp.
  - – Validates our `WorkflowEngine` abstraction end-to-end. This is the
    first real workflow shipped. If pain shows up here, we revisit ADR-002.

---

## ADR template (for future ADRs)

```
## ADR-NNN — <decision in one line>

- **Date:** YYYY-MM-DD
- **Status:** Proposed | Accepted | Superseded by ADR-XXX | Deprecated
- **Context:** Why this decision is being made now.
- **Decision:** What we're going to do.
- **Alternatives considered:** Briefly, with why-not.
- **Consequences:** + and – effects of the decision.
```
