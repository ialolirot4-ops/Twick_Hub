# Twick Hub

Reescritura desde cero de TwitchLink con soporte de Twitch + Kick como
plataformas de primera clase (Master Plan v3.0). Este README cubre cómo
instalar, correr, testear y empaquetar el proyecto tal como está hoy
(FASE 19 — Packaging); para el histórico completo de decisiones y el
estado fase por fase, ver `docs/phase-state.md` y
`docs/architecture-decisions.md`.

Lee primero `docs/architecture-decisions.md`, `docs/migration-map.md`,
`docs/risk-register.md`, `docs/kick-audit.md` y `docs/functional-baseline.md`
(entregados en FASE 0), tal como pide el propio Master Plan al abrir cada fase.

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

## Empaquetar (Windows x64)

```bash
pip install pyinstaller
pyinstaller packaging/pyinstaller/twick_hub.spec --noconfirm
```

Produce `dist/TwickHub/` (bundle `--onedir`, distribuible como zip
portátil). Ver `docs/packaging.md` para las decisiones de empaquetado,
qué se verificó y con qué evidencia, y qué sigue pendiente — en
particular, el build real de Windows x64 solo puede producirse
ejecutando PyInstaller en Windows (o vía
`.github/workflows/build-windows.yml`), no desde este repositorio en un
entorno Linux.

## Migraciones (Alembic)

```bash
.venv/bin/alembic upgrade head
```

El esquema real (FASE 8 en adelante) vive en `migrations/versions/`. Nota
importante (RISK-PKG-02, FASE 19): la app en sí **no** corre este comando
automáticamente al arrancar — hay que correrlo a mano contra cualquier
base de datos nueva antes de que la app pueda leer/escribir de verdad.

## Estructura

Ver `src/twick_hub/{domain,application,infrastructure,presentation}/`
para el árbol completo — crece con cada fase, así que el detalle
completo vive en `docs/migration-map.md` y `docs/phase-state.md`, no
aquí. A nivel de capa:

```
src/twick_hub/
├── main.py, bootstrap/          # entry point + DI explícita (AD-03)
├── config/settings.py           # AppConfig (pydantic-settings)
├── domain/                      # entidades/value objects, sin PySide6 ni framework
├── application/                 # casos de uso, scheduling, live_monitor, updates
├── infrastructure/              # twitch/, kick/, downloads/, persistence/, migration/, updates/
└── presentation/qml/, qml_bridge/ # shell QML + puente Python↔QML (AD-11)
```
