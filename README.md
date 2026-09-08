# Twick Hub — FASE 1 (Skeleton)

Skeleton mínimo: abre, cierra, inicializa dependencias por DI explícita
(sin servicios globales), corre tests. Sin funcionalidad real de
Twitch/Kick todavía — eso empieza en FASE 4/5.

Lee primero `docs/architecture-decisions.md`, `docs/migration-map.md`,
`docs/risk-register.md`, `docs/kick-audit.md` y `docs/functional-baseline.md`
(entregados en FASE 0), tal como pide el propio Master Plan al abrir FASE 1.

## Instalar

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Correr

```bash
.venv/bin/python -m twick_hub.main
```

En un entorno sin display (CI, contenedores): `QT_QPA_PLATFORM=offscreen`.

## Tests / lint / tipos

```bash
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pyright
```

Los 10 tests, ruff y pyright pasan limpio en este entregable (ver el
gate de FASE 1 para el detalle de qué prueba cada uno).

## Migraciones (Alembic)

```bash
.venv/bin/alembic upgrade head
```

No hay modelos todavía (llegan en FASE 8) — este comando solo confirma
que Alembic resuelve la configuración real de la app (`AppConfig`) y
`Base.metadata`, no un valor de plantilla.

## Estructura

```
src/twick_hub/
├── main.py                    # entry point
├── bootstrap/                 # DI explícita — reemplaza App.Instance (AD-03)
│   ├── container.py           # contenedor de dependencias (dataclass, no service locator)
│   ├── dependencies.py        # construye el Container una sola vez
│   └── application.py         # ciclo de vida: Qt + asyncio (qasync) + motor QML
├── config/settings.py         # AppConfig (pydantic-settings)
├── logging_setup.py
├── infrastructure/persistence/ # engine + Base declarativa (sin modelos aún)
├── domain/                    # vacío — FASE 3
├── application/                # vacío — FASE 3
└── presentation/qml/Main.qml   # shell mínimo — FASE 2 lo reemplaza
```
