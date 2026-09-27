# Twick Hub — Packaging (FASE 19)

Este documento es el artefacto de continuidad de FASE 19 (Master Plan
§56/§30) — cómo se construye un bundle distribuible de Twick Hub, qué se
verificó realmente en qué entorno, y qué queda pendiente para quien
continúe.

## Decisiones (ver docs/architecture-decisions.md para el detalle completo)

- **AD-93** — Windows x64 es el único target de este release. macOS
  pospuesto (no eliminado); Linux preparado arquitectónicamente, sin
  build.
- **AD-94** — Distribución como directorio (`--onedir` de PyInstaller)
  + zip portátil. Sin instalador de asistente (NSIS/Inno/MSIX) todavía.
- **AD-95** — FFmpeg: no embebido en esta sesión (sin origen de red
  verificado disponible); mecanismo de resolución de ruta documentado
  para cuando RISK-ARCH-03 cablee `FFmpegProcessor` de verdad.
- **AD-96** — Selenium/navegador: sin cambios respecto de AD-08 (carga
  bajo demanda, navegador no embebido).
- **AD-97** — `bootstrap/runtime_paths.py` nuevo, reemplaza el cálculo
  de ruta QML basado en `Path(__file__)` (roto bajo PyInstaller) por uno
  consciente de `sys._MEIPASS`.

## Cómo construir el bundle

Desde la raíz del repositorio, con el entorno de desarrollo ya instalado
(`pip install -e ".[dev]"`) más `pyinstaller`:

```bash
pip install pyinstaller
pyinstaller packaging/pyinstaller/twick_hub.spec --noconfirm
```

Produce `dist/TwickHub/` (bundle `--onedir` completo) y
`build/twick_hub/` (artefactos intermedios de PyInstaller, no
distribuibles). Ambos ya están en `.gitignore` desde antes de esta fase.

`packaging/pyinstaller/entrypoint.py` es el script mínimo que
`Analysis()` necesita como punto de entrada (PyInstaller no puede
apuntar directamente a `python -m twick_hub.main`) — no contiene lógica
propia, solo llama a `twick_hub.main.main()`.

## Qué se verificó realmente en este sandbox (Linux) — y qué NO

Este entorno de desarrollo es Linux y no tiene acceso a un runner
Windows. Eso importa porque **PyInstaller no hace cross-compilation**:
un `.exe` de Windows x64 real solo puede producirse ejecutando
PyInstaller *en* Windows. Dos cosas distintas, ambas con evidencia real
pero de naturaleza diferente:

### 1. Verificado aquí, con evidencia real (Linux, smoke test)

- `pyinstaller packaging/pyinstaller/twick_hub.spec` corre limpio y
  produce un bundle `--onedir` completo.
- El binario resultante (ELF de Linux, no el `.exe` de Windows) se
  ejecutó de verdad en modo headless (`QT_QPA_PLATFORM=offscreen`) y
  cargó el shell QML correctamente — confirmado por la línea de log
  `"Twick Hub skeleton started."`, que solo se alcanza si
  `QQmlApplicationEngine.load()` tuvo éxito y `rootObjects()` no está
  vacío (ver `bootstrap/application.py::Application.run()`).
- Esto confirma que el mecanismo de `datas` (QML) + `runtime_paths.py`
  (AD-97) + `entrypoint.py` + `hiddenimports` de `keyring.backends.*`
  funciona correctamente bajo un build congelado real — no solo en
  teoría.
- Tests unitarios reales (`tests/test_runtime_paths.py`) prueban la
  rama "congelado" de `package_root()` simulando `sys._MEIPASS` con
  `monkeypatch`, sin necesitar el build real para esa parte.
- Tamaño medido del bundle sin podar: 516 MB (420 MB PySide6, de los
  cuales 359 MB son `Qt/lib`) — ver RISK-PKG-03 en
  `docs/risk-register.md` para el desglose completo y el plan de poda
  (no implementado esta fase).

### 2. NO se pudo verificar aquí — requiere Windows real

- El `.exe` de Windows x64 en sí. `.github/workflows/build-windows.yml`
  (nuevo, esta fase) es el mecanismo para producirlo: corre en
  `windows-latest`, instala el proyecto, corre `pytest`/`ruff`/`pyright`
  como gate previo, construye con el mismo `.spec`, hace un smoke test
  del `.exe` real (arranca, espera 5s, confirma que no se cerró solo, lo
  detiene) y sube el zip como artefacto. **Este workflow no se ha
  ejecutado todavía** — existe, está listo para dispararse
  (`workflow_dispatch` o un tag `v*`), pero correrlo requiere un push a
  GitHub y un runner real de Actions, ninguno de los dos disponible
  desde este sandbox.
- El hidden-import `keyring.backends.Windows` — el `.spec` lo añade
  condicionalmente (`sys.platform == "win32"`), pero solo es
  *importable* en Windows (depende de `pywin32`), así que nunca se
  ejercitó en este dry-run Linux.
- El plugin de plataforma Qt para Windows (`qwindows.dll` y el
  mecanismo de estilo nativo) — el dry-run Linux usó el plugin `xcb`
  (con `QT_QPA_PLATFORM=offscreen` para evitar necesitar un display
  real); el equivalente Windows es una ruta de código Qt distinta,
  nunca antes ejercitada por este proyecto.
- Firma de código / notarización — no aplica a Windows en este release
  (sin certificado), y no aplica a macOS porque macOS está pospuesto
  (AD-93).

## Limitaciones conocidas heredadas de otras fases (no de esta)

- RISK-ARCH-03: el motor de descargas real (incluido `FFmpegProcessor`)
  no está cableado a `bootstrap/dependencies.py` todavía — el bundle
  arranca y muestra el shell, pero ninguna descarga real corre dentro de
  él hoy. Sin cambios en esta fase.
- RISK-PKG-02 (nuevo, esta fase): una instalación nueva no tiene ningún
  mecanismo que corra las migraciones de Alembic — la base de datos
  quedaría sin tablas. Documentado, no corregido (toca el arranque real
  de la app, no el empaquetado de lo que ya existe).

## Siguiente paso concreto para quien continúe

1. Push a GitHub, disparar `.github/workflows/build-windows.yml`
   (`workflow_dispatch`) y confirmar que el `.exe` real arranca en el
   smoke test del propio workflow.
2. Abrir manualmente el `.exe` al menos una vez en un Windows real antes
   de considerar el artefacto listo para distribuir — ni el smoke test
   headless de CI ni el dry-run Linux de esta fase sustituyen eso.
