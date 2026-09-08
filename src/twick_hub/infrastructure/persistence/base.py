"""Declarative base for ORM models.

No models are defined yet — FASE 8 (Persistence) adds ``accounts``,
``favorites``, ``downloads``, and the rest of the entities listed in
docs/architecture-decisions.md. FASE 1 only has to prove that SQLAlchemy
and Alembic are wired correctly end to end against an empty schema.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
