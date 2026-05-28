# Aegis — Autonomous Security Operations Governance Platform

> AI-governed, bounded autonomous remediation for security operations.
> Trust-first. Explainable. Reversible. Audited.

Aegis ingests security alerts, classifies and scores them with AI, evaluates
governance policies, recommends remediation, and — when policy and confidence
allow — executes **bounded, reversible** actions while keeping a human in the
loop for high-blast-radius decisions. Every action is logged to a
tamper-evident audit chain.

This is not "an AI security bot." It is a **trust layer for autonomous
security operations**: an AI that knows what it is and is not allowed to do,
and that can prove what it did and why.

---

## Phase 0 — Foundation (this commit)

Phase 0 establishes the monorepo, infra, schemas, and the **abstraction
interfaces** that all later sprints plug into. No business logic yet — by
design.

What's wired:

- **Monorepo** (`backend/`, `frontend/`, `docs/`)
- **Docker Compose**: Postgres 16 + pgvector, Redis 7, FastAPI backend,
  Celery worker, Vite/React frontend
- **Backend**: FastAPI + SQLAlchemy 2.0 (async) + Alembic + structlog
- **Database**: Foundational schemas (users, alerts, incidents, remediation
  actions, audit log with hash chain, policies, approvals, workflow runs, AI
  reasoning snapshots)
- **Identity**: `IdentityProvider` interface, local JWT implementation, Okta
  adapter stub
- **Workflow**: `WorkflowEngine` interface, Celery implementation, Temporal
  stub (migration path documented in [docs/DECISIONS.md](docs/DECISIONS.md))
- **Audit**: Append-only audit log with SHA-256 hash chain
- **Policy**: `PolicyEngine` stub with eval contract
- **Frontend**: Vite + React + TypeScript + Tailwind + React Query + Zustand;
  proves wiring by calling `/api/v1/health`
- **CI**: GitHub Actions running ruff + mypy + pytest on backend,
  eslint + tsc on frontend

## Quick start

```bash
cp .env.example .env
make up         # docker compose up --build
make migrate    # apply Alembic migrations
make seed       # create a default admin user (dev only)
```

Then:

- Backend: <http://localhost:8000/api/v1/health>
- API docs: <http://localhost:8000/docs>
- Frontend: <http://localhost:5173>

## Repo layout

```
aegis/
├── backend/                FastAPI service + Celery worker
│   ├── app/
│   │   ├── api/v1/         HTTP routes
│   │   ├── core/           Cross-cutting abstractions
│   │   │   ├── identity/   IdentityProvider interface + impls
│   │   │   ├── workflow/   WorkflowEngine interface + impls
│   │   │   ├── audit/      Tamper-evident audit logger
│   │   │   └── policy/     Policy evaluation engine
│   │   ├── models/         SQLAlchemy ORM models
│   │   ├── schemas/        Pydantic request/response schemas
│   │   └── workers/        Celery app + task registry
│   ├── alembic/            Migrations
│   └── tests/
├── frontend/               Vite + React + TS + Tailwind
├── docs/
│   ├── ARCHITECTURE.md     System architecture overview
│   ├── DECISIONS.md        ADR log
│   └── CHANGELOG.md        Sprint audit trail (immutable, append-only)
├── docker-compose.yml
├── Makefile
└── .env.example
```

## Engineering principles

These are load-bearing. Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for
the full version.

1. **The AI never has unrestricted authority.** Every action passes through
   the policy engine and (above a blast-radius threshold) a human approval.
2. **Every action is reversible or it doesn't ship.** Remediation actions
   without a defined rollback path do not execute autonomously — they
   escalate.
3. **Every action is explainable.** AI decisions persist a reasoning
   snapshot: model, prompt, evidence, confidence, policy match.
4. **The audit log is append-only and tamper-evident.** SHA-256 hash chain;
   no application-level UPDATE or DELETE.
5. **Abstractions are interfaces first.** Workflow engine, identity
   provider, integrations — all behind protocols so we can swap implementations
   (Celery → Temporal; local JWT → Okta) without rewriting callers.

## Status

Phase 0 ships infrastructure only. Sprint 1 begins alert ingestion + AI
triage. See [docs/CHANGELOG.md](docs/CHANGELOG.md).
