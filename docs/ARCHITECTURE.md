# Aegis — System Architecture

> Phase 0 snapshot. Updated at the end of every sprint.

---

## 1. Product framing

Aegis is a **governance layer** that sits between security signal sources
(SIEMs, EDRs, identity providers) and the response actions a SOC takes.

It is *not*:

- a SIEM
- an EDR
- a SOAR replacement
- an AI chatbot

It *is*:

- a trust + policy layer for AI-assisted incident response
- a system that decides *whether* and *how* the AI is allowed to act
- the source of truth for **what was done, when, by whom (or what), and why**

## 2. Logical layers

```
┌──────────────────────────────────────────────────────────────────────┐
│                   1. Alert Ingestion Layer                           │
│   Webhooks / pull connectors (Defender, Okta, Slack-via-Jira, ...)   │
└──────────────────────────────────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   2. Normalization Layer                             │
│   Source-specific → canonical Alert schema; dedup; correlation key   │
└──────────────────────────────────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│           3. AI Triage Engine   ──►   AI Reasoning Snapshot          │
│   Classification • confidence • MITRE mapping • severity             │
└──────────────────────────────────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   4. Policy Governance Engine                        │
│   Evaluates: action class × blast radius × confidence × scope        │
│   Output: ALLOW / ESCALATE / DENY  + matching policy IDs             │
└──────────────────────────────────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   5. Remediation Decision Engine                     │
│   Selects bounded remediation w/ rollback plan; idempotency key       │
└──────────────────────────────────────────────────────────────────────┘
                                  ▼
┌────────────────────────────┐   if ESCALATE   ┌──────────────────────┐
│ 6. Workflow Execution      │   ◄──────────► │ 7. Human Approval     │
│    Engine (Celery → Temporal)               │    Slack / Web UI     │
└────────────────────────────┘                └──────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   8. Audit & Forensics Layer                         │
│   Append-only • SHA-256 hash chain • AI reasoning attached           │
└──────────────────────────────────────────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│             9. Observability     +    10. Analytics                  │
│   Logs / metrics / traces           MTTR, false-positive %, etc.     │
└──────────────────────────────────────────────────────────────────────┘
```

## 3. Component view

| Component             | Phase 0 status          | Technology                          |
| --------------------- | ----------------------- | ----------------------------------- |
| API service           | scaffolded              | FastAPI + Uvicorn                   |
| Worker                | scaffolded              | Celery + Redis                      |
| Workflow engine iface | implemented (Celery)    | `WorkflowEngine` protocol           |
| Identity provider     | implemented (local JWT) | `IdentityProvider` protocol         |
| Audit logger          | implemented             | Postgres + SHA-256 hash chain       |
| Policy engine         | stubbed (eval contract) | Python (CEL-like DSL planned)       |
| Frontend              | scaffolded              | Vite + React + TS + Tailwind        |
| Database              | implemented             | Postgres 16 + pgvector              |
| Cache + broker        | implemented             | Redis 7                             |
| AI triage             | not started             | Claude (default) / OpenAI fallback  |
| Connectors            | not started             | Defender, Okta, Slack, Jira         |

## 4. Foundational data model (Phase 0)

All tables ship in the initial Alembic revision. See
[`backend/app/models/`](../backend/app/models/).

- **users** — actor identity for human operators
- **alerts** — raw ingested signal, normalized
- **incidents** — correlated alert clusters (one or more alerts)
- **policies** — declarative rules; what AI may/may not do, when, where
- **remediation_actions** — proposed/executed actions w/ rollback metadata
- **approvals** — human-in-the-loop approval state machine
- **workflow_runs** — engine-agnostic workflow execution state
- **audit_logs** — append-only hash-chained event log
- **ai_reasoning_snapshots** — model, prompt, evidence, confidence

### Audit log integrity

Each `audit_logs` row stores:

- `prev_hash`: SHA-256 of the previous row's `entry_hash` (NULL for genesis)
- `entry_hash`: SHA-256 of canonicalized `(prev_hash || payload)`

Tamper detection = re-walk the chain. Application role has `INSERT` only;
`UPDATE` / `DELETE` revoked. (DB-level enforcement scheduled for Sprint 2 —
see [DECISIONS.md](DECISIONS.md) ADR-006.)

## 5. Key abstractions

### `IdentityProvider`

```python
class IdentityProvider(Protocol):
    async def authenticate(self, credentials: Credentials) -> User | None: ...
    async def issue_token(self, user: User) -> Token: ...
    async def verify_token(self, token: str) -> TokenClaims: ...
```

- Phase 0 impl: `LocalJWTIdentityProvider` (HS256, users table)
- Phase 2 impl: `OktaIdentityProvider` (OIDC code flow, stub present)

### `WorkflowEngine`

```python
class WorkflowEngine(Protocol):
    async def submit(self, workflow_name: str, payload: dict, *,
                     idempotency_key: str, actor_id: UUID | None = None) -> UUID: ...
    async def get_status(self, run_id: UUID) -> WorkflowRunSnapshot: ...
    async def cancel(self, run_id: UUID, reason: str) -> None: ...
    async def request_rollback(self, run_id: UUID, reason: str,
                               actor_id: UUID) -> UUID: ...
```

- Phase 0 impl: `CeleryWorkflowEngine` — Redis broker, Postgres-tracked state
- Future impl: `TemporalWorkflowEngine` — durable execution, native rollback
  semantics. Migration triggers when (a) we need cross-step retries with
  guaranteed state durability, or (b) we need long-running workflows
  (>15 min) with replay. See [DECISIONS.md](DECISIONS.md) ADR-002.

### `AuditLogger`

```python
class AuditLogger(Protocol):
    async def record(self, *, actor: Actor, action: str,
                     resource_type: str, resource_id: UUID | None,
                     payload: dict, reasoning: dict | None = None) -> AuditEntry: ...
```

- Phase 0 impl: `HashChainAuditLogger` — Postgres-backed, SHA-256 chained

### `PolicyEngine`

```python
class PolicyEngine(Protocol):
    async def evaluate(self, request: PolicyEvalRequest) -> PolicyDecision: ...
```

- Phase 0: contract + stub impl returning `ESCALATE` for everything (safe
  default). Real rules ship Sprint 2.

## 6. Trust model

- **Default-deny.** Anything the policy engine doesn't explicitly allow
  becomes an `ESCALATE`.
- **Confidence gates.** Each action class has a minimum AI confidence
  threshold. Below threshold → escalate, no exceptions.
- **Blast-radius caps.** Each action class has a max blast radius
  (e.g., "lock at most 5 user sessions"). Exceeding → escalate.
- **Reversibility requirement.** Any action selected for autonomous
  execution must have a defined rollback. No rollback = no autonomy.
- **Reasoning is persisted before action.** The audit log records the AI's
  decision *before* the workflow engine submits it. If the workflow never
  runs (e.g., approval times out), the reasoning is still on the chain.

## 7. Deferred infrastructure (deliberate)

The following are intentionally out of Phase 0. See
[DECISIONS.md](DECISIONS.md) ADR-001 for rationale.

- Temporal (Celery first; abstraction lets us swap)
- LocalStack (no AWS calls in Phase 0)
- OpenTelemetry collector + Grafana / Loki stack (structlog now;
  OTel-compatible naming so wiring is mechanical later)
- HashiCorp Vault (env vars + `.env` for Phase 0)
- Service mesh / Istio
- Multi-tenancy
- Advanced RBAC (single admin role for Phase 0)
