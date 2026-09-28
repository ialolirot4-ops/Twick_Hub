PROJECT_NAME: Twick Hub
MASTER_PLAN_VERSION: 3.0
CURRENT_PHASE: FASE 21b — qml_bridge real para Favorites, Downloads, History (PASS) — ver FASE_21_INTEGRACION_FINAL.md
PHASE_STATUS: CERRADA — PASS. `FavoritesPage.qml`, `DownloadsPage.qml` y `HistoryPage.qml` dejaron de usar `property var mock*`: leen de `favoritesModel`/`downloadsModel`/`historyModel`, bridges Python inyectados por motor en el `rootContext` (AD-100) sobre los repositorios/servicios reales del `Container`. Progreso en vivo por sondeo de 1 Hz solo con la página visible y descargas activas (AD-101). Con Twitch/Kick sin adapters (21c), Favorites degrada a "Status unknown" en lugar de fallar.
HALLAZGO_FASE_21b: (1) `DownloadExecutor` solo persiste `progress_percent` al completar: el avance en vivo se lee de `DownloadEngine.progress_of` (memoria). (2) `Favorite` no guarda nombre de canal y `AddFavoriteUseCase` no persiste el `Channel`: la tarjeta muestra el `external_id` (RISK-UI-03). (3) Bug de cierre detectado y corregido en el smoke test real: modelos destruidos antes que el QML que los enlaza -> se parentan al motor. (4) Sin adapters de plataforma no hay forma de crear favoritos ni descargas desde la UI: en una corrida real las tres páginas muestran su estado vacío hasta 21c/21d; los datos reales se verificaron sembrando SQLite.
LIMITACION_DE_ENTORNO_FASE_21b: Ninguna relevante (sin red a twitch.tv/kick.com, no necesaria). Suite re-ejecutada de cero con PySide6 6.11.2 en venv. Verificación visual real (ventana con pantalla) no disponible: todo corrió con QT_QPA_PLATFORM=offscreen; el render se verificó por árbol de items QML, no por captura de pantalla.
LAST_COMPLETED_PHASE: FASE 21b (PASS). Antes: FASE 21a (PASS) + fix RISK-PKG-02 (AD-98/AD-99), ambos aún sin commit en el working tree recibido. FASE 20 sigue BLOCKED como veredicto propio.
SOURCE_BASELINE: Mismo working tree recibido (Twick_Hub.zip): HEAD 9e96ad5 + cambios sin commitear de 21a/RISK-PKG-02. Sin commit nuevo — el usuario decide cuándo commitear.
PROJECT_VERSION: 0.1.0 (sin cambios)
TEST_STATUS: pytest 1056/1056 passed (1039 + 17 nuevos en tests/test_qml_bridge_data.py; tests/test_qml_shell.py adaptado, mismo número de tests). ruff: 8 errores conocidos, sin cambios (E501 en migrations/versions/). pyright: 0 errors, 0 warnings, 0 informations. Todo re-ejecutado de cero.
STATIC_ANALYSIS_STATUS: ruff/pyright limpios sobre archivos nuevos/modificados y el repo completo (salvo los 8 conocidos).
RUNTIME_VALIDATION_STATUS: smoke real fuera de la suite (no comiteado): `Application.run()` con qasync, `QT_QPA_PLATFORM=offscreen`, SQLite con 2 favoritos, 1 descarga activa y 1 completada; navegando por las 3 páginas los bridges quedaron con 2/1/1 filas correctas, 0 warnings QML y cierre con código 0 sin ruido de teardown.
KNOWN_BLOCKERS:
  - El artefacto Windows x64 real sigue sin poder producirse en este entorno — sin cambios, no es competencia de FASE 21.
KNOWN_RISKS:
  - NUEVOS en 21b: RISK-UI-03 (favoritos sin nombre de canal), RISK-PERF-05 (historial sin paginar), RISK-ARCH-06 (ciclo de vida del motor de descargas fuera del cierre de `Application`).
  - AVANZADO en 21b: RISK-UI-01 (3 de 6 páginas con mock ya son reales). RISK-UI-02 sin cerrar (capabilities aún no expuestas a QML).
  - Sin cambio de estado: RISK-ARCH-01/02/04/05, RISK-DATA-01/02, RISK-RESUME-01, RISK-UX-01, RISK-CONCURRENCY-01, RISK-PERF-01..04, RISK-LIVE-01..05, RISK-KICK-01..03, RISK-TWITCH-01..04, RISK-SEC-01/02, RISK-MIGRATION-01, RISK-PROD-01/02, RISK-TEST-01, RISK-BUILD-01/02, RISK-PKG-02 (hueco del bundle congelado).
IMPORTANT_DECISIONS: docs/architecture-decisions.md AD-100 (bridges por `rootContext`, `RowListModel`, `TaskRunner`, padre = motor, casos de uso nuevos, degradación de Favorites) y AD-101 (sondeo 1 Hz condicionado).
FILES_CHANGED:
  - src/twick_hub/application/downloads.py (2 casos de uso nuevos, aditivo)
  - src/twick_hub/bootstrap/application.py (instala bridges antes de cargar el QML)
  - src/twick_hub/presentation/qml_bridge/{context,row_model,tasks,favorites_model,downloads_model,history_model}.py (nuevos)
  - src/twick_hub/presentation/qml/pages/{FavoritesPage,DownloadsPage,HistoryPage}.qml (mock -> bridge, con estado vacío)
  - tests/test_qml_bridge_data.py (nuevo, 17 tests), tests/test_qml_shell.py (adaptado)
  - docs/architecture-decisions.md, docs/risk-register.md, docs/phase-state.md
NEXT_PHASE: FASE 21e checkpoint intermedio (app funcional sin red) según el orden recomendado 21a -> 21b -> 21e -> 21c -> 21d -> 21e; o directamente FASE 21c si el usuario prefiere.
NEXT_PHASE_PREREQUISITES:
  (1) 21e (checkpoint) no necesita nada más: correr la app real y confirmar qué páginas son reales (Favorites/Downloads/History) y cuáles mock (Search/Live/Account).
  (2) 21c debe ejecutarse en la máquina del usuario (red a twitch.tv/kick.com) — aclararlo al abrir ese chat.
  (3) Antes de que 21d permita encolar descargas desde la UI: resolver RISK-ARCH-06 y RISK-UI-03.
DATE_UTC: 2026-09-27
