"""Domain layer: entities, value objects, enums, and protocols.

No PySide6, no SQLAlchemy, no httpx — nothing that ties this code to a
UI toolkit, a database, or a specific platform's API client. Application
(``twick_hub.application``) orchestrates these through the
protocols in ``domain/protocols.py``; Infrastructure (FASE 4+) is what
actually implements them.
"""
