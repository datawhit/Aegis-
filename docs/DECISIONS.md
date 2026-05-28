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
