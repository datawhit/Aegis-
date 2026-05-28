"""Cross-cutting abstractions: identity, workflow, audit, policy.

Everything in `app.core` is interface-first. Concrete implementations sit
beside the interface in the same subpackage so the dependency surface is
obvious at a glance.
"""
