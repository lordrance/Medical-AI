"""Repository layer — thin async wrappers around SQLAlchemy queries.

Each repo receives an `AsyncSession` at construction time so callers
stay agnostic about the underlying ORM. This is the only package in the
app that imports `sqlalchemy` names directly.
"""
