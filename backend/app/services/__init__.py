"""Service layer — orchestrators that compose models + core abstractions.

Services are the right place for business logic that touches multiple
models or cross-cutting concerns (audit logger, policy engine). Endpoints
should delegate to services, not embed orchestration inline.
"""
