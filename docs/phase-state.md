PROJECT_NAME: Twick Hub
MASTER_PLAN_VERSION: 3.0
CURRENT_PHASE: FASE 22.0 — Higiene del repo (sobre la base funcional de FASE 21c)
PHASE_STATUS: 22.0 PASS (ver sección al final; falta solo el commit del usuario). Base 21c, sin cambios: CERRADA — PASS, con alcance declarado. Adapters reales de Twitch y Kick cableados al `Container` y verificados en vivo en Windows 11: Kick 3/3, Twitch `twitch-channel` y `twitch-integrity`. **Sin verificar** (no es un fallo, no se probó): `twitch-account` y `twitch-playback` (el import de sesión solo soporta Firefox y el usuario no lo usa; ver RISK-TWITCH-05), `kick-disconnect` (revocación real) y Kick sin sesión iniciada.
MATRIZ_REAL_VS_MOCK (sin cambio; 21c no toca QML):
  - REAL: Favorites, Downloads, History, y los dos contadores de Home.
  - MOCK: Search, Live, Account (21d); Home en "Live now" y "Recent activity"; Settings.
  - PLACEHOLDER: Scheduled y Playlists. ESTÁTICA: About.
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
LAST_COMPLETED_PHASE: 22.0 (PASS, pendiente de commit). Antes: 21c (PASS con alcance declarado); antes de esa, fix post-21e de Home (PASS), 21e checkpoint (PASS), 21b (AD-100/101), 21a (AD-98) + RISK-PKG-02 (AD-99). FASE 20 sigue BLOCKED.
SOURCE_BASELINE: HEAD 1313779 (commit "22": catch-up de 21a, RISK-PKG-02, 21b, fix de Home y 21c; sobre 9e96ad5) + el borrado de `benchmarks/{src,docs,tests,FASE21b.diff}` de 22.0.
PROJECT_VERSION: 0.1.0 (sin cambios)
TEST_STATUS: pytest 1074/1074 passed (1057 heredados + 17 nuevos; reverificado en 22.0, venv nuevo, `QT_QPA_PLATFORM=offscreen`, antes y después del borrado). `ruff check src/twick_hub tests`: 0 errores. `pyright`: 0/0/0. El script de verificación pasa ruff y pyright, pero no lo ejecuta pytest.
KNOWN_BLOCKERS:
  - Windows x64 real sigue sin poder producirse aquí — no es competencia de FASE 21.
KNOWN_RISKS:
  - RISK-TWITCH-05 (NUEVO): el único login de Twitch soportado es importar la sesión de Firefox; sin sesión no hay playback (descargas de Twitch). Decisión pendiente antes de 21d.
  - RISK-ARCH-01: CERRADO en lo que 21c cubría (wiring); lo que queda de ese riesgo es `live_monitor` (21d).
  - RISK-ARCH-09 (antes RISK-ARCH-06 duplicado): ampliado — el `httpx.AsyncClient` de `build_platform_adapters()` tampoco se cierra en el cierre de `Application`.
  - Sin cambio: RISK-UI-03, RISK-UI-04, RISK-UI-05, RISK-PERF-05, RISK-PKG-03 (tamaño del bundle), RISK-PKG-04 (antes RISK-PKG-03 duplicado: sin `__main__.py`), RISK-TWITCH-04 (Integrity: ahora con una verificación en vivo a favor), demás heredados.
IMPORTANT_DECISIONS:
  - AD-102 (ver docs/architecture-decisions.md).
  - RISK-UI-03 NO se hizo en 21c: requiere tocar `AddFavoriteUseCase` o `FavoritesModel`; pendiente de confirmación del usuario.
  - Kick sin `TWICK_HUB_KICK_CLIENT_ID/SECRET` queda con adapters vacíos (no anuncia una cuenta que no puede conectar).
FILES_CHANGED: ver los ZIP de entrega de 21c (FASE21c.zip, FASE21c_fix1.zip y el de cierre).
NEXT_PHASE: 22.1 — Ciclo de vida y fin de las "mentiras" de la UI (RISK-ARCH-09, parte de RISK-UI-05, RISK-PKG-04). Sin decisiones pendientes. El resto de 21d/21f vive en 22.2–22.15 (`PLAN_FASE_22_HACIA_APP_FUNCIONAL.md`).
NEXT_PHASE_PREREQUISITES:
  22.1: ninguno. Decisiones del plan §1 que se necesitan más adelante: D1 (login de Twitch sin Firefox) antes de 22.2; D2 (nombre de canal en Favoritos) antes de 22.5; D3/D4/D5/D6 según sub-fase.
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
