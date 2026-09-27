"""Declarative base for ORM models.

FASE 1 only had to prove that SQLAlchemy and Alembic were wired
correctly end to end against an empty schema. FASE 8 adds the real
tables — see infrastructure/persistence/models.py.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
