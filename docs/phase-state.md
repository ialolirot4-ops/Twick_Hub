PROJECT_NAME: Twick Hub
MASTER_PLAN_VERSION: 3.0
CURRENT_PHASE: FASE 22.1 — Ciclo de vida y fin de las "mentiras" de la UI (sobre 22.0 y la base funcional de FASE 21c)
PHASE_STATUS: 22.1 PASS (ver su sección al final; falta el commit del usuario y una comprobación manual en Windows, ver PENDIENTE_DEL_USUARIO_22_1). 22.0 PASS. Base 21c, sin cambios: CERRADA — PASS, con alcance declarado. Adapters reales de Twitch y Kick cableados al `Container` y verificados en vivo en Windows 11: Kick 3/3, Twitch `twitch-channel` y `twitch-integrity`. **Sin verificar** (no es un fallo, no se probó): `twitch-account` y `twitch-playback` (el import de sesión solo soporta Firefox y el usuario no lo usa; ver RISK-TWITCH-05), `kick-disconnect` (revocación real) y Kick sin sesión iniciada.
MATRIZ_REAL_VS_MOCK (22.1 solo cambia lo marcado "22.1"; el resto, igual que en 21c):
  - REAL: Favorites, Downloads, History, y los dos contadores de Home.
  - MOCK: Search, Live, Account (21d); Home en "Live now" y "Recent activity"; Settings.
  - PLACEHOLDER: Scheduled y Playlists. ESTÁTICA: About.
  - 22.1: el botón Refresh de Home relee de verdad los dos contadores reales. Account, Scheduled, Playlists y el Reset de Settings siguen siendo mock/placeholder, pero ya no afirman nada: responden "Not available yet." (Account muestra todavía su estado literal `your_twitch_login`, hasta 22.2).
  - Backend, nuevo en 21c: `Container.platform_registry` tiene los adapters reales de Twitch y Kick cuando `main()` los construye (AD-102). Ninguna página los consume todavía (21d).
METODO: auditoría del repo recibido antes de escribir; baseline 1057/1057 confirmado. Cada corrección se probó primero con un test que falla. Comparado el `IntegrityToken.getHeaders()` y `getChannel` de TwitchLink 3.5.6 para no inventar formatos.
CAMBIOS_21c:
  - `bootstrap/platforms.py` (nuevo): `build_platform_adapters()`. Twitch: account, channel_directory, live_stream_provider, video_provider, clip_provider, playback_resolver. Kick (solo con credenciales): account, channel_directory, live_stream_provider.
  - `bootstrap/dependencies.py`: `build_container(platform_adapters=None)` (aditivo, sin argumento = comportamiento 21a). `main.py`: Qt antes que los adapters.
  - `IntegrityHeaderSource` (nuevo, `integrity_adapter.py`); `AppConfig.kick_client_id/kick_client_secret` (`SecretStr`).
  - Fix `KickAccountService.current_account()`: refresca un token vencido en vez de borrar la sesión (confirmado en vivo).
  - Fix `migrations/env.py`: `fileConfig` solo en la CLI de Alembic; la migración en proceso ya no apaga los loggers de la app.
  - Fix `TwitchChannelDirectory._lookup`: manda solo `id` o solo `login` (el otro null), como `getChannel` de TwitchLink 3.5.6. Encontrado en la verificación en vivo (`find_channel` devolvía None); los tests con `MockTransport` no lo veían porque solo miraban que el login estuviera en el cuerpo.
  - `scripts/verify_21c_live.py` (nuevo): verificación en vivo, no forma parte de pytest.
VERIFICACION_EN_VIVO (máquina del usuario: Windows 11, Python 3.12.10, PySide6 6.11.2, 2026-09-28):
  - PASS `kick-connect`: OAuth 2.1 + PKCE completo (navegador, listener local en :51823, intercambio de token contra id.kick.com, lectura del usuario); tokens guardados en el Credential Manager de Windows.
  - PASS `kick-refresh`: con `expires_at` forzado a 0, `current_account()` renovó el token en vez de borrar la sesión.
  - PASS `kick-channel`: búsqueda de un canal con su estado en vivo por la API real.
  - PASS `twitch-channel` (tras el fix): canal, estado en vivo y seguidores por GQL real con el Client-ID web.
  - PASS `twitch-integrity`: la página oculta de QtWebEngine capturó el token de Integrity y Twitch lo aceptó (30 videos listados). **Sin sesión de Twitch iniciada**: no dice nada sobre el caso con sesión. La consola de esa página imprime líneas `js:` (WebGPU, bluetooth): son mensajes del JavaScript de Twitch dentro de Chromium, inocuos, no errores del proyecto.
  - NO PROBADOS: `twitch-account`, `twitch-playback` (requieren Firefox con sesión de Twitch), `kick-disconnect`, Kick sin sesión.
LIMITACION_DE_ENTORNO: el sandbox de desarrollo no tiene red a twitch.tv/kick.com ni Secret Service ni Windows; por eso lo de arriba se verificó en la máquina del usuario.
LAST_COMPLETED_PHASE: 22.1 (PASS, pendiente de commit). Antes: 22.0 (PASS); antes de esa: 21c (PASS con alcance declarado); antes de esa, fix post-21e de Home (PASS), 21e checkpoint (PASS), 21b (AD-100/101), 21a (AD-98) + RISK-PKG-02 (AD-99). FASE 20 sigue BLOCKED.
SOURCE_BASELINE: 22.0 aplicado (HEAD 1313779 "22" + `git rm` de `benchmarks/{src,docs,tests,FASE21b.diff}` + phase-state de 22.0) + los cambios de 22.1.
PROJECT_VERSION: 0.1.0 (sin cambios)
TEST_STATUS: pytest 1108/1108 passed (1074 de 22.0 + 34 nuevos de 22.1: 7 de cierre, 1 de ffmpeg, 1 de Home/Refresh, 25 del escaneo QML, uno por archivo; venv nuevo, `QT_QPA_PLATFORM=offscreen`). El ruido `RuntimeError: Signal source has been deleted` del final de la suite desapareció. `ruff check src/twick_hub tests`: 0 errores. `pyright`: 0/0/0. El script de verificación pasa ruff y pyright, pero no lo ejecuta pytest.
KNOWN_BLOCKERS:
  - Windows x64 real sigue sin poder producirse aquí — no es competencia de FASE 21.
KNOWN_RISKS:
  - RISK-TWITCH-05 (NUEVO): el único login de Twitch soportado es importar la sesión de Firefox; sin sesión no hay playback (descargas de Twitch). Decisión pendiente antes de 21d.
  - RISK-ARCH-01: CERRADO en lo que 21c cubría (wiring); lo que queda de ese riesgo es `live_monitor` (21d).
  - RISK-ARCH-09: CERRADO en 22.1 (AD-103). RISK-PKG-04: CERRADO en 22.1. RISK-UI-05: el texto engañoso CERRADO en 22.1, la conexión real sigue ABIERTA (22.9/22.10/22.15).
  - RISK-RESUME-02 (NUEVO, LOW): cerrar a mitad del remux puede dejar un archivo parcial en el destino; se resuelve en 22.6. RISK-ARCH-10 (NUEVO, LOW, informativo): Ctrl+C no cierra la app desde la terminal.
  - Sin cambio: RISK-UI-03, RISK-UI-04, RISK-PERF-05, RISK-PKG-03 (tamaño del bundle), RISK-TWITCH-04 (Integrity: ahora con una verificación en vivo a favor), demás heredados.
IMPORTANT_DECISIONS:
  - AD-102 (ver docs/architecture-decisions.md).
  - RISK-UI-03 NO se hizo en 21c: requiere tocar `AddFavoriteUseCase` o `FavoritesModel`; pendiente de confirmación del usuario.
  - Kick sin `TWICK_HUB_KICK_CLIENT_ID/SECRET` queda con adapters vacíos (no anuncia una cuenta que no puede conectar).
FILES_CHANGED: ver los ZIP de entrega de 21c (FASE21c.zip, FASE21c_fix1.zip y el de cierre).
NEXT_PHASE: 22.2 — Account real + login de Twitch + Kick (cierra RISK-TWITCH-05 y RISK-ARCH-08; requiere Windows real para verificar `twitch-account`, `twitch-playback`, `kick-disconnect`).
NEXT_PHASE_PREREQUISITES:
  22.2: **decisión D1** del plan (login de Twitch sin Firefox): (a) exigir Firefox una vez, (b) login dentro de la app con QtWebEngine capturando la sesión [recomendada], (c) importar de Chromium [descartable]. Sin D1 no se empieza.
  Después: D2 antes de 22.5; D3/D4/D5/D6 según sub-fase (plan §1).
DATE_UTC: 2026-09-28

---
## FASE 22.0 — Higiene — PASS (falta el commit del usuario)
- FASE 22 (`PLAN_FASE_22_HACIA_APP_FUNCIONAL.md`) REEMPLAZA a `FASE_21_INTEGRACION_FINAL.md` en lo pendiente: 21d, 21e-final y 21f pasan a las sub-fases 22.2–22.15.
- IDs de riesgo duplicados corregidos (verificado: `grep '^## RISK-' | uniq -d` vacío): ciclo de vida del motor → RISK-ARCH-09 (RISK-ARCH-06 sigue siendo "Settings sin conectar"); falta de `__main__.py` → RISK-PKG-04 (RISK-PKG-03 sigue siendo el tamaño del bundle).
- Catch-up 21a–21c: ya commiteado como `1313779` ("22"). Ese commit arrastró por error las copias sueltas de `benchmarks/` (17 archivos).
- Copias sueltas: verificado con `diff` que las de `docs/` y `tests/test_qml_bridge_data.py` reales son las más nuevas (las de `benchmarks/` no tienen AD-102, RISK-UI-04/05, RISK-PKG-04, RISK-TWITCH-05 ni `test_home_page_shows_real_favorites_and_downloads_counts`) y que las 11 de `src/` y `tests/test_qml_shell.py` son idénticas. Nada del repo (CI, spec de PyInstaller, tests) referencia esas rutas.
- Aplicado en el sandbox: `git rm -r benchmarks/src benchmarks/docs benchmarks/tests benchmarks/FASE21b.diff` (17 archivos). `benchmarks/` queda con sus 4 archivos propios. pytest 1074 passed, `ruff check src/twick_hub tests` 0 errores, `pyright` 0/0/0, antes y después.
- Pendiente del usuario: ejecutar ese `git rm` en su repo, aplicar este `docs/phase-state.md` y commitear (un commit para 22.0).
- Observación para 22.1 (no es un fallo): al terminar la suite aparece `RuntimeError: Signal source has been deleted` en `qasync.close()` desde `BaseEventLoop.__del__`; es ruido de teardown de un loop qasync y posiblemente relacionado con el ciclo de vida que 22.1 aborda.

## FASE 22.1 — Ciclo de vida y fin de las "mentiras" de la UI — PASS (falta el commit del usuario)
- Cierre ordenado (AD-103, RISK-ARCH-09): `Container.closers` (aditivo) + `Application` paran workers y cierran los dos `httpx.AsyncClient` dentro del loop, antes de `engine.dispose()`; un closer que falla no detiene al siguiente; `TaskRunner.cancel_all()` para las tareas de la UI. Misma secuencia si QML no carga (antes `return 1` sin cerrar nada).
- Bug real encontrado al auditar, con test que falló primero: cancelar `AsyncioProcessRunner.run` dejaba ffmpeg huérfano (solo el timeout lo mataba). Corregido.
- `twick_hub/__main__.py` (RISK-PKG-04). Log de arranque sin "skeleton".
- UI sin afirmaciones falsas: 4 toasts obsoletos → "Not available yet."; Reset de Settings ya no anuncia un éxito; Home/Refresh relee los contadores reales. Guardia: `tests/test_qml_no_false_claims.py`.
- Verificado (sandbox Linux, offscreen): pytest 1108 passed; `ruff check src/twick_hub tests` 0 errores; `pyright` 0/0/0. Arranque real con `python -m twick_hub`: vivo tras 6 s, log `Twick Hub started.` Pruebas de mutación: quitar `download_service.stop` o el `kill` de ffmpeg hace fallar su test.
- `ruff format --check` marca 8 archivos preexistentes (ya en `HEAD`, no tocados); los archivos de 22.1 están formateados.
- Observado, no arreglado: Ctrl+C no cierra la app desde la terminal (RISK-ARCH-10); archivo parcial tras cerrar a mitad de remux (RISK-RESUME-02); la fila queda `DOWNLOADING` hasta 22.6.
- PENDIENTE_DEL_USUARIO_22_1: (1) aplicar el ZIP y commitear (un commit para 22.1); (2) **2 minutos en Windows**: `python -m twick_hub`, cerrar la ventana y comprobar que el log termina en `Shutting down.` y el proceso sale (el segundo `exec()` de Qt solo está probado en Linux offscreen); (3) decidir D1 para poder empezar 22.2.

