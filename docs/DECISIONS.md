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

## ADR-011 — JSON-rule policy DSL with opt-in autonomy per action class

- **Date:** 2026-05-27 (Sprint 02)
- **Status:** Accepted (Phase 2 cut; CEL / Cedar spike Phase 3+)
- **Context:** The Sprint 1 stub engine escalated everything (ADR-005 was
  the right starting posture). To close the loop with humans, we need a
  DSL that's both **expressive enough** for real rules and **trivial
  enough** to audit by inspection.
- **Decision:** Ship a tiny JSON DSL — `and/or/not/eq/in/gte/lte/matches`
  — evaluated against a flat context (action_class, blast_radius,
  ai_confidence, incident_severity, has_rollback_plan). Combined with a
  `constraints` blob on each policy that carries metadata like
  `requires_approval: true|false` — the **per-action-class shadow-mode
  lever** (Q13). Default shipped policies set `requires_approval: true`
  on ALLOW rules; operators flip it to `false` per action class as
  trust accumulates.
- **Conflict + failure modes:**
  - No policy matches → ESCALATE (no-rule = ask a human).
  - Equal-priority ALLOW + ESCALATE → ESCALATE (no silent permissive
    merge).
  - DENY at any priority wins over equal-or-lower ALLOW.
  - DSL evaluation error → policy skipped (treated as no-match).
- **Why not CEL / OPA / Cedar yet:** all are more expressive, all are
  another deployable. Phase 2 needs to ship; the DSL is intentionally
  the smallest thing that demonstrates the trust posture. A Phase 3
  spike compares the three against the same rule set.
- **Consequences:**
  - + Operators can read policies as-is. No DSL training required.
  - + The DSL evaluator is ~100 LOC; verified by direct unit tests.
  - – Limited expressiveness (no joins across DB tables, no time-of-day
    rules). When we hit a real customer rule we can't write, that's
    the migration signal.

---

## ADR-012 — Slack as the Sprint 2 approval channel; dry-run by default

- **Date:** 2026-05-27 (Sprint 02)
- **Status:** Accepted (Phase 2 scope; Email + Web UI in Phase 3)
- **Context:** OQ-9 — approval channel breadth. Slack is where SecOps
  teams already live; building three channels in Sprint 2 spreads the
  surface too thin.
- **Decision:**
  - Sprint 2 ships **Slack only**, behind a `Notifier` abstraction so
    Phase 3 channels are additive, not migrational.
  - **Dry-run posture by default**: `AEGIS_SLACK_ENABLED=false` logs the
    rendered Block Kit payload at INFO and skips the HTTP call. The
    end-to-end demo loop is exercisable from `make up` with no real
    Slack workspace.
  - Inbound `POST /api/v1/slack/interact` verifies Slack's v0 HMAC
    signature; signing secret must be configured to accept signed
    callbacks in non-prod, and is required in prod.
- **Consequences:**
  - + One channel ships in 1 sprint, end-to-end including the inbound
    callback contract.
  - – Customers without Slack will block on Phase 3. Acceptable for
    our target ICP (Q3 still open; mid-market SaaS SOCs all run Slack).

---

## ADR-013 — PII redaction in AI prompts; per-snapshot lookup table

- **Date:** 2026-05-27 (Sprint 02)
- **Status:** Accepted
- **Context:** D-11. The Sprint 1 pipeline shipped raw entity values
  (UPNs, IPs, hostnames, file hashes) into the LLM prompt. That's a
  data-residency liability for any GDPR/SOC2-conscious customer.
- **Decision:** A `PIIRedactor` walks the normalized payload and
  replaces matches against known PII shapes with **salted, stable
  tokens** (`<user:8e2f>`, `<ip:b14a>`, `<file:cd09>`, `<host:ff03>`).
  The redaction is performed in `TriageService` **before** the provider
  call. The lookup table (token → original) is persisted on the
  reasoning snapshot's `evidence` field so the analyst UI can
  de-redact for display, but the model only ever sees tokens.
  Determinism within a single redaction call preserves co-reference
  (the same email appearing twice gets the same token). Per-call salt
  ensures tokens cannot be correlated across snapshots.
- **Trade-off:** the model may classify slightly less accurately
  without raw identifiers (e.g., it can't recognize internal naming
  conventions like `svc-` prefixes). Acceptable. Bigger downside is
  raw PII flowing to third-party LLMs.
- **Future work:** allowlist for known-non-PII tokens (e.g., the
  customer's own corporate domain stays unredacted for context);
  optionally local-LLM proxy that handles PII without redaction at all.

---

## ADR-014 — DB-role-level audit immutability via `aegis_audit_writer`

- **Date:** 2026-05-27 (Sprint 02)
- **Status:** Accepted; closes ADR-006 follow-up
- **Context:** ADR-006 deferred true DB-role enforcement to Sprint 2.
- **Decision:** Migration `0002_audit_writer_role` creates a Postgres role
  with `INSERT`-only on `audit_logs`. The application reads
  `AEGIS_AUDIT_WRITER_DATABASE_URL`; when set, audit-log inserts use a
  separate connection pool bound to that role. When unset (e.g., local
  dev), the audit logger continues to use the regular pool — convenient
  for development, but **production deployments must set it.**
- **Belt-and-braces:** The hash-chain verifier (`workflows.verify_audit_chain`)
  runs daily and posts a P0 Slack alert on mismatch. Even if the role
  separation is somehow bypassed, tampering is detected.
- **Consequences:**
  - + A compromised app process running arbitrary SQL still can't
    `UPDATE` or `DELETE` historical audit rows.
  - + Verifier provides defense-in-depth.
  - – Two connection pools means two sets of pool metrics; cost is small
    relative to the trust gain.

---

## ADR-015 — Signed audit-export receipts via Ed25519

- **Date:** 2026-05-29 (Sprint 04)
- **Status:** Accepted
- **Context:** Sprint 3 shipped `GET /audit/export` as plain NDJSON. A
  compliance officer who downloads such a file cannot prove later that
  it was the un-tampered server output without a separate chain-of-custody
  story. The hash chain inside each row protects against in-DB tampering
  but says nothing about what was *handed to the auditor.*
- **Decision:** Each export ends with a final `{"receipt": true, ...}`
  line carrying: the requested range + count, the last entry's
  `entry_hash` (`head_entry_hash`), the chain tip at snapshot time
  (`tip_entry_hash`), a SHA-256 over the ordered list of entry hashes
  (`content_hash`), the exporter identity, a `signing_key_id`, and an
  Ed25519 `signature` over the canonical JSON of the receipt minus
  `signature`. A standalone `app.scripts.verify_audit_export` CLI lets a
  recipient verify without touching the database.
- **Why Ed25519 over RSA or HMAC:**
  - HMAC requires sharing the verification secret with the auditor —
    they could then *forge* a receipt, defeating non-repudiation.
  - Ed25519: small (64-byte sig), modern, no parameter choices, fast.
- **Key management:** Private key in `AEGIS_AUDIT_EXPORT_SIGNING_KEY`
  (PEM). `signing_key_id` is stable so verifiers can pin the right public
  key after rotation. By default the export endpoint **refuses** to run
  without a key (`require_signature=true`); local dev can pass
  `?require_signature=false` to get an unsigned receipt with explicit
  `"signature": null`.
- **Snapshot semantics:** The endpoint captures the chain tip BEFORE
  recording the "audit.exported" entry. The export's own request entry
  therefore does NOT appear in this export — it appears in any future
  export, which is the point.
- **Consequences:**
  - + Exports are independently verifiable: anyone with the public key
    can prove (a) the file wasn't truncated, (b) the chain links
    correctly, (c) the receipt was signed by the production server.
  - + A leaked export is still an export — there's no secret to rotate
    other than the signing key itself.
  - – Adds a `cryptography` dependency (already transitively present
    via `python-jose[cryptography]`).
  - – Key rotation requires an out-of-band channel to distribute the
    new public key + `signing_key_id` to verifiers.

---

## ADR-016 — REVIEWER role for compliance read-only access

- **Date:** 2026-05-29 (Sprint 04)
- **Status:** Accepted
- **Context:** The audit export and policy snapshot are exactly the
  artifacts a compliance officer / external auditor will want to read.
  Granting them `ADMIN` to fetch a receipt is the worst possible posture
  — they also gain policy-write, rollback, and seed-script access.
- **Decision:** Introduce `UserRole.REVIEWER`. Reviewer can `GET`:
  `/audit/export`, `/policies`, `/policies/{id}`, `/incidents`,
  `/incidents/{id}`, `/approvals`. Reviewer **cannot** create/update/
  delete policies, decide approvals, or trigger rollbacks. Three named
  dependency injectors live in `app.api.deps` (`AdminDep`,
  `AdminOrOperatorDep`, `AdminOrReviewerDep`) so role policy at endpoint
  level is one line of annotation.
- **Why a fifth role rather than overloading VIEWER:** VIEWER is
  defined as default-zero-privilege (e.g. a fresh SSO user before role
  mapping). Reviewer carries explicit compliance-export rights that we
  do NOT want a new user to inherit by accident.
- **Consequences:**
  - + Compliance reviewers can do their job with a single-purpose
    credential. Audit log records the reviewer's identity on every
    export request.
  - + Future fine-grained RBAC (D-26) extends this pattern without a
    schema migration — `UserRole` is a string-backed enum.
  - – One more role for the seed/SSO-mapping conversation; documented
    in `seed_dev_admin.py` and the role enum.

---

## ADR-017 — Rollback authorization scales with action reversibility

- **Date:** 2026-05-29 (Sprint 04)
- **Status:** Accepted; refines ADR-014/Sprint 03's blanket `operator|admin` gate
- **Context:** Sprint 3 made rollback `operator|admin`. But "rollback" of
  `REVOKE_USER_SESSIONS` is not really an undo — the sessions are already
  destroyed; calling rollback at best records that a human concluded the
  revoke was unwarranted. The audit weight of that signal is much higher
  than the audit weight of un-isolating a host (truly reversible).
- **Decision:** `RemediationActionClass.is_reversible` classifies each
  action class. The rollback endpoint requires:
  - Reversible classes (ISOLATE_HOST, DISABLE_USER, BLOCK_IP,
    BLOCK_DOMAIN, QUARANTINE_FILE, OPEN_JIRA_TICKET) → `operator|admin`.
  - Non-reversible classes (REVOKE_USER_SESSIONS, FORCE_PASSWORD_RESET,
    NOTIFY_SLACK, CUSTOM) → `admin` only.
- **Why the conservative split for `CUSTOM`:** unknown reversibility =
  fail-closed. A future "we know how to undo this" custom action would
  need to either declare itself reversible explicitly or get its own
  enum value.
- **Consequences:**
  - + The "did a human knowingly accept the irreversible action?" signal
    is now attributable to a senior actor.
  - + No state-machine change: the gate is purely at the API edge; the
    executor stays role-agnostic.
  - – Operators lose the ability to "rollback" non-reversible actions
    autonomously; in practice this matches the operational reality
    (a compensating control like forcing re-MFA still requires admin
    or out-of-band action).

---

## ADR-018 — Multi-key signing registry with file-based storage

- **Date:** 2026-05-29 (Sprint 06)
- **Status:** Accepted; supersedes the single-key shape introduced in ADR-015
- **Context:** ADR-015 shipped one private key in `AEGIS_AUDIT_EXPORT_SIGNING_KEY`.
  Rotation under that scheme silently breaks past exports: once the
  active key changes, the only public PEM the system can publish is
  the new one, but every receipt signed before the switch refers to
  the old key by `signing_key_id`. Auditors have to track those PEMs
  out-of-band, defeating the verifier's "ask the server for the public
  key" story.
- **Decision:** Introduce a registry of keys. Exactly one entry has
  `status: "active"` (the signer uses it); any number have
  `status: "retired"` (public_pem retained so verification of old
  exports keeps working). Storage is a JSON file at
  `AEGIS_AUDIT_KEY_REGISTRY_PATH` so operators can rotate without an
  env var redeploy — point at a new file, restart, done. Single-key
  mode from Sprint 4 is preserved as a fallback when the registry path
  is unset.
- **Why file over env / KMS:**
  - Env: PEMs are bulky and embedding multiple entries as JSON in an
    env var is painful to maintain.
  - KMS (AWS/GCP/Vault): the right answer eventually, but requires a
    KMS-specific adapter — explicitly deferred (D-37) in favor of
    landing rotation mechanics today.
  - File: each environment owns its own file in its secrets layer
    (mounted secret, K8s projected volume, etc.).
- **Consequences:**
  - + Rotation is a file edit + restart — no code change.
  - + Verifiers can pin by `signing_key_id` and the well-known endpoint
    will publish the matching public PEM forever (until that entry is
    explicitly removed from the registry).
  - + Backward-compatible with Sprint 4 single-key deployments.
  - – One more thing for operators to forget — boot-time validation
    (which we don't yet have) would catch a missing/malformed file.

---

## ADR-019 — `/.well-known/aegis-audit-public-key` for verifier bootstrap

- **Date:** 2026-05-29 (Sprint 06)
- **Status:** Accepted
- **Context:** The signed-receipt verifier needs the active server's
  public key (and any retired keys still in scope) to validate exports.
  Until now the only distribution channel was "ask the operator to send
  you the PEM." That doesn't scale for a compliance officer doing
  spot-checks, and it leaves room for impersonation if a bad PEM gets
  sent.
- **Decision:** Serve the registry's public view at
  `/.well-known/aegis-audit-public-key` — unauthenticated, JSON shape
  `{"keys":[{"key_id":"...","status":"...","public_pem":"..."}]}`,
  always reads from the same registry that backs the signer. The
  verifier CLI (Sprint 4) will be extended to fetch this URL when run
  with a `--server-url` flag instead of `--public-key` (deferred to
  Sprint 7).
- **Why root path + unauthenticated:**
  - RFC 5785 convention: `/.well-known/` is reserved for site-wide
    metadata that's safe to expose without auth.
  - An auditor with no credentials still needs to verify — gating this
    would defeat the purpose.
  - Public key material is, by definition, public.
- **Consequences:**
  - + Verification works end-to-end without out-of-band coordination.
  - + The endpoint is intentionally cacheable by reverse proxies.
  - – Anyone can discover the operating org's key_ids, which is a tiny
    fingerprinting signal — accepted given the public-by-design nature.

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
