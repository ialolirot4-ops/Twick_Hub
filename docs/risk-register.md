# Twick Hub — Risk Register (FASE 0)

Severidad: CRITICAL / HIGH / MEDIUM / LOW.

## RISK-TWITCH-01 — Presupuesto de coste de EventSub limita favoritos monitoreables en tiempo real
**Severidad:** HIGH (bajada de CRITICAL — ver Estado)
**Evidencia:** `max_total_cost=10` por token de usuario; suscribirse a un canal ajeno cuesta 1 por tipo de suscripción → con 2 tipos por canal (`stream.online`, `stream.offline`), el techo real confirmado es de exactamente 5 canales monitoreados en tiempo real por token de usuario. FASE 4d confirmó (corrección a AD-04) que el transporte WebSocket exige token de usuario — los tokens de aplicación son el camino de Webhooks, no aplican acá.
**Impacto:** Sin mitigación, Twick Hub tiene un límite de 5 favoritos con notificación en tiempo real vía EventSub — muy por debajo de lo que un usuario espera hoy.
**Mitigación implementada:** `CapacityGovernor` (AD-23) aplica el límite explícitamente — nunca se excede en silencio. Respaldo pendiente de implementar (FASE 10): Helix `Get Streams` en polling de bajo coste (no consume presupuesto EventSub) para favoritos que excedan el presupuesto disponible.
**Estado (FASE 10):** El límite está CONFIRMADO y APLICADO. La mitigación de respaldo **quedó implementada**: los favoritos que exceden las 5 plazas se sondean por lotes con Helix `GET /streams` (`TwitchBatchLiveStatusProvider`, ≤100 ids por request) desde `HybridLiveMonitor` (AD-51). Riesgo residual: que Helix acepte el par `WEB_CLIENT_ID` + token de sesión no está validado con una cuenta real — ver RISK-LIVE-01. Severidad efectiva: MEDIUM hasta esa validación.

## RISK-TWITCH-02 — Server-Side Ad Insertion (SSAI) puede afectar la limpieza de las descargas
**Severidad:** HIGH
**Evidencia:** Fuentes de 2026 confirman que Twitch inserta anuncios directamente en el mismo stream de video, no desde una fuente separada bloqueable como antes. FASE 4c portó `hideAds` (campo real del token de playback de 3.5.5): revela cuándo un viewer específico no recibe anuncios en absoluto (Turbo, o suscripción con beneficio ad-free) — respuesta parcial, verificada, no la pregunta completa: no dice qué hay en los segmentos para un viewer sin ninguno de los dos.
**Impacto:** Si los anuncios quedan incrustados en los segmentos HLS descargados, las grabaciones podrían contener anuncios que antes se evitaban a nivel de manifest/segmento — afecta "Stream downloads" y "Video unmuting", ambas de compatibilidad obligatoria.
**Mitigación propuesta:** No se pudo verificar empíricamente contra un stream real ni en FASE 4c ni antes — Twitch no es alcanzable desde el sandbox de este proyecto. FASE 7 (Download Engine) es quien procesa segmentos de verdad y debe hacer esa verificación antes de declarar paridad de "Stream downloads" — con una cuenta real, decidir qué hacer según `hideAds`.
**Estado:** ABIERTO — parcialmente informado (AD-22), no resuelto. Pasa a ser bloqueante para FASE 7, no para FASE 4c (que solo resuelve URLs, no descarga bytes).

## RISK-SEC-01 — Tokens OAuth en JSON plano (confirmado en 3.5.5)
**Severidad:** HIGH en 3.5.5 / mitigado en Next si AD-07 se implementa correctamente
**Evidencia:** `AppData/Preferences.py` serializa `Account.__save__()` (incluye `OAuthToken`) dentro del árbol que `json.dump()` vuelca completo a `settings.json`, sin cifrado visible en `EncoderDecoder.py`. Confirmado literalmente en FASE 15 al leer un `settings.json` legacy real: el campo `account._accountData` contiene el token de sesión de Twitch en texto plano, exactamente como se predijo aquí.
**Mitigación:** AD-07 (keyring, FASE 4a) — implementada. FASE 15 (AD-83) migra ese valor al credential store de Twick Hub vía `LegacyMigrationService`, verificado de punta a punta en `tests/application/test_legacy_migration.py`. **No** purga el valor del `settings.json` legacy original — ver AD-83 para el razonamiento (conflicto con la regla permanente "no romper datos del usuario": el archivo podría pertenecer a una instalación de TwitchLink que el usuario sigue usando) y RISK-MIGRATION-01 para el hallazgo nuevo de que el propio backup de esta fase también queda con el secreto en texto plano.
**Estado:** Implementado (FASE 4a: no escribir más el secreto en JSON; FASE 15: migrar el existente al credential store). Purga del original: decisión consciente de no implementarla — ver RISK-MIGRATION-01.

## RISK-TWITCH-03 — Dependencia de la API GQL privada de Twitch
**Severidad:** MEDIUM (riesgo aceptado, no evitable con la información disponible hoy)
**Evidencia:** El propio foro de desarrolladores de Twitch confirma que GraphQL "no está pensado para uso de terceros, no está documentado oficialmente, no tiene soporte oficial" y que el uso conlleva riesgo de funcionalidad y de baneo. Requiere el Client-ID propio del sitio web de Twitch y un token extraído de sesión de navegador real.
**Impacto:** Es la única vía conocida para VOD/clips/metadata y reproducción — sin ella, Next pierde paridad funcional con Twitch casi por completo.
**Mitigación:** Aislar completamente detrás de interfaces (`VideoProvider`, `ClipProvider`, ya previsto por Master Plan §8). No es evitable — es el mismo riesgo que ya asume TwitchLink hoy.
**Estado:** Aceptado, mitigado por aislamiento arquitectónico, no por eliminación.

## RISK-TWITCH-04 — Client-Integrity token en endurecimiento activo
**Severidad:** MEDIUM
**Evidencia:** Herramientas de terceros para generar el token de integridad reportan que Twitch despliega actualizaciones de seguridad que invalidan generadores existentes de forma recurrente.
**Impacto:** Mantenimiento continuo, no un costo de una sola vez.
**Mitigación:** Aislar en `Infrastructure/Twitch/Integrity`, con manejo de error explícito si Integrity falla — nunca fallo silencioso.
**Estado:** Aceptado, sin mitigación estructural posible más allá del aislamiento. Actualización FASE 21c: la captura de Integrity con QtWebEngine se verificó en vivo en Windows 11 (2026-09-28), sin sesión de Twitch: el token se capturó y Twitch lo aceptó para listar videos. No cubre el caso con sesión iniciada.

## RISK-KICK-01 — VOD/Clips de Kick sin cobertura oficial confirmada
**Severidad:** MEDIUM · **Evidencia/mitigación:** ver `kick-audit.md` y AD-05. **Estado:** decisión tomada; implementación en FASE 5.

## RISK-KICK-02 — Webhook oficial de Kick exige endpoint público
**Severidad:** MEDIUM · **Evidencia/mitigación:** ver `kick-audit.md` y AD-06. **Estado:** decisión tomada.

## RISK-KICK-03 — Estabilidad operativa actual de la API oficial de Kick
**Severidad:** LOW por ahora, revisar antes de FASE 5 · **Evidencia:** bug reportado en agosto de 2026 sobre `invalid_scope` y reconocimiento de webhooks (ver `kick-audit.md`). **Estado:** informativo.

## RISK-UI-01 — Costo de reescritura completa de la capa de presentación
**Severidad:** MEDIUM
**Evidencia:** 49 archivos `Ui/*.py` + 28 `.ui` de Qt Designer en 3.5.5, todos QtWidgets — cero reutilizables como implementación bajo QML (AD-02).
**Impacto:** FASE 2 es, en volumen, la fase de mayor superficie de reescritura de todo el proyecto.
**Mitigación:** Preservar comportamiento/flujo documentado (no el código) al construir cada pantalla QML; usar `Ui/*.py` solo como referencia de UX.
**Estado:** Aceptado, es el costo conocido de AD-02. FASE 21b: 3 de las 6 páginas con mock (Favorites, Downloads, History) pasaron a datos reales; quedan Search, Live y Account (21d). FASE 21e añade que Home también es mock (RISK-UI-04) y que Settings/Scheduled/Playlists no están conectadas (RISK-UI-05).

## RISK-PKG-01 — Selenium/Patchright + PyQt6-WebEngine en tamaño y estabilidad del paquete
**Severidad:** MEDIUM
**Evidencia:** `requirements.txt` de 3.5.5 incluye `PyQt6-WebEngine`, `selenium==4.40.0`, `patchright==1.60.1` — dependencias pesadas para una funcionalidad acotada (importar cookies del navegador).
**Impacto:** Tamaño de instalador (FASE 19) y superficie de fallo (versiones de navegador cambiantes).
**Mitigación:** AD-08 — carga bajo demanda, no en el arranque; evaluar en FASE 4a si `PyQt6-WebEngine` es realmente necesario.
**Estado:** Actualizado en FASE 19 — `PyQt6-WebEngine`/`patchright` nunca se adoptaron (Twick Hub usa PySide6, no PyQt6, y solo `selenium` como dependencia real de `pyproject.toml`; `grep` de `patchright` en todo el proyecto no devuelve nada). El riesgo de tamaño persiste pero por una causa distinta a la registrada originalmente: no es `PyQt6-WebEngine` — es que el propio hook de PyInstaller para PySide6 empaqueta el `Qt/lib` completo (~359 MB) incluyendo módulos que la app no usa (WebEngine, Multimedia, Charts, Qt3D, etc.), independientemente de si `QtWebEngine` se usa o no. Ver RISK-PKG-03 (nuevo, FASE 19) para la medición y el plan de mitigación concreto. El propio `selenium` (sin WebEngine) sigue cumpliendo AD-08 (carga bajo demanda) — no aporta peso al arranque, solo al tamaño en disco del bundle.

## RISK-PROD-01 — PartnerContent sin decisión final
**Severidad:** LOW · **Estado:** pospuesto (AD-09), decidir antes de FASE 2.

## RISK-PROD-02 — Alcance de macOS/Linux sin decidir
**Severidad:** LOW · **Estado:** DECIDIDO EN FASE 19 (ver AD-93) — Windows x64 es el único target empaquetado de este release; macOS queda pospuesto explícitamente (no eliminado); Linux queda preparado arquitectónicamente sin build, tal como permitía el propio Master Plan §30.

## RISK-BUILD-01 — `src/twitchlink_next/` obsoleto se empaqueta junto a `twick_hub` (hallazgo FASE 6)
**Severidad:** MEDIUM
**Evidencia:** El ZIP recibido para FASE 6 contiene `src/twick_hub/` (vigente, importado por todos los tests y por `pyproject.toml`'s `twick-hub = "twick_hub.main:main"`) Y `src/twitchlink_next/` (copia obsoleta previa al rename de FASE 4d, sin `infrastructure/kick/`, sin `infrastructure/twitch/eventsub/`). `[tool.setuptools.packages.find] where = ["src"]` no tiene `include`/`exclude`, así que `pip install -e ".[dev]"` deja **ambos** paquetes importables (`import twitchlink_next` funciona igual que `import twick_hub`) y cualquier build real (FASE 19) empaquetaría el código obsoleto también.
**Impacto:** No rompe tests/ruff/pyright hoy (nadie importa `twitchlink_next`), pero viola Master Plan §0.9 ("No introducir nombres nuevos como 'TwitchLink Next'... salvo razón de compatibilidad legacy explícita y documentada") en el artefacto final, e infla el paquete distribuido con código muerto y potencialmente confuso.
**Mitigación:** Fuera del alcance de FASE 6 (no es un defecto de esta fase ni bloquea su cierre — Master Plan §0.5/§0.13: se registra, no se corrige de paso). Corrección mínima sugerida para quien la aborde: borrar `src/twitchlink_next/` del repositorio (ya no lo usa nada) o, si se prefiere no borrar código sin entender su cobertura (regla permanente #28), añadir `include = ["twick_hub*"]` a `[tool.setuptools.packages.find]` como mitigación inmediata sin tocar el árbol de archivos.
**Estado:** CORREGIDO EN FASE 20 (el cierre de FASE 19 afirmaba "CERRADO — eliminado del repositorio"; auditoría estática de FASE 20 confirmó que `src/twitchlink_next/` sigue presente en el artefacto recibido, 392 KB, 8 subcarpetas — el borrado descrito nunca se aplicó). El diagnóstico original y la mitigación efectiva sí son correctos: `diff -rq` contra `src/twick_hub` confirma que es la copia obsoleta pre-rename, `grep` confirma cero referencias fuera de sí misma, y `include = ["twick_hub*"]` en `[tool.setuptools.packages.find]` de `pyproject.toml` SÍ está presente — un build empaquetado con ese `pyproject.toml` no incluye `twitchlink_next`, así que el riesgo de empaquetado (razón de ser de esta entrada) está mitigado en la práctica. Pendiente, no bloqueante: borrar físicamente `src/twitchlink_next/` del árbol (acción de limpieza, no de empaquetado) — ver `docs/final-architecture-review.md` §1 para el detalle completo del hallazgo de continuidad. `pytest` 1029/1029, `ruff` 8/8 conocidos, `pyright` 0/0/0 citados en el cierre de FASE 19 no fueron reproducidos en FASE 20 (sandbox sin red/deps — ver `docs/final-architecture-review.md` §0).

## RISK-BUILD-02 — El historial de `git` está muy por detrás del estado real del código en disco (hallazgo FASE 18)
**Severidad:** LOW — no afecta al código en sí, pero sí a la trazabilidad fase-por-fase.
**Evidencia:** `git log --oneline` en el repositorio recibido para FASE 18 muestra solo 4 commits (`F4c`, `fase 4d`, `Fase5`, `Fase7`) — nada posterior a FASE 7. El código en disco, sin embargo, ya refleja el trabajo hasta FASE 17 completo (persistencia, migración, scheduling, live monitor, updates, etc., todos presentes y con tests en verde). `git status --short` al empezar FASE 18 mostraba decenas de archivos nuevos/modificados sin commitear, acumulados a lo largo de al menos 10 fases.
**Impacto:** Ninguno funcional — `pytest`/`ruff`/`pyright` no dependen de `git`. El impacto real es de trazabilidad: no es posible usar `git diff`/`git log` para aislar qué cambió en una fase concreta frente a las anteriores, que es precisamente para lo que el Master Plan pide "continuidad entre fases vía docs/ actualizados" como red de seguridad independiente de git.
**Mitigación:** Esta fase no reescribe el historial (no es su mandato, y "squashear" 10 fases en un commit retroactivo perdería más trazabilidad de la que arreglaría). En su lugar, el propio commit de cierre de FASE 18 documenta explícitamente en su mensaje que agrupa el catch-up de todo el trabajo previo no commiteado más los cambios reales de esta fase, para que quede constancia del corte. Recomendación para quien retome el proyecto: commitear al final de cada fase a partir de ahora (ideal: un commit por fase, como ya hacían los primeros 4).
**Estado:** RECURRIÓ en FASE 19 pese a la recomendación de este mismo riesgo (el cierre de FASE 19 quedó sin commitear otra vez, y además afirmó incorrectamente que sí existía un commit real — ver `docs/final-architecture-review.md` §1). Commiteado en FASE 20 (`git log` ahora incluye FASE 19+20 en un solo commit de catch-up, mismo patrón que FASE 18). ABIERTO como riesgo de proceso, informativo — no bloqueante — porque nada garantiza que no vuelva a recurrir en una fase futura si quien la ejecuta no commitea al cerrar.

## RISK-ARCH-01 — `PlatformRegistry` sin wirear a `bootstrap/container.py` (FASE 6)
**Severidad:** LOW por ahora, bloqueante para quien primero necesite adapters reales
**Evidencia:** Ver AD-31. `Container` sigue sin ningún campo de plataforma; `PlatformRegistry` (FASE 6) existe y está testeado con fakes, pero nada en `bootstrap/dependencies.py` construye un `PlatformAdapters` real con las clases de `infrastructure/twitch/`/`infrastructure/kick/`.
**Impacto:** Ninguno todavía — FASE 6 no lo necesitaba. Sí bloquea a la primera fase que necesite un `PlatformRegistry` con datos reales corriendo dentro de la app (candidata: FASE 7 Download Engine o una fase de feature real, FASE 9+).
**Mitigación:** Ensamblar `PlatformAdapters` reales en `bootstrap/dependencies.py` cuando esa fase lo requiera — requiere decidir ahí mismo cómo resolver las dependencias de cada adapter concreto (keyring, cliente HTTP, Integrity, etc.), no antes.
**Estado:** ABIERTO — parcialmente avanzado en FASE 21a: `Container.platform_registry` ya existe y es un `PlatformRegistry` real (no un fake de test), pero registrado con `PlatformAdapters()` vacío para Twitch y Kick (ningún adapter real, cero credenciales) — decisión deliberada de 21a, ver bootstrap/dependencies.py. El riesgo real que esta entrada describe (adapters reales con keyring/HTTP/Integrity) sigue sin resolver y sigue siendo FASE 21c, no bloquea FASE 6/7 ni 21a en sí.
**Actualización FASE 21c (parte offline):** PARCIALMENTE CERRADO. `bootstrap/platforms.py::build_platform_adapters()` arma los adapters reales de Twitch (account, channel_directory, live_stream_provider, video_provider, clip_provider, playback_resolver) y de Kick (account, channel_directory, live_stream_provider; sin video/clip/playback, ver AD-05), y `main()` los pasa a `build_container(platform_adapters=...)` (AD-102). Verificado con `httpx.MockTransport`; **Verificado en vivo** (Windows 11, 2026-09-28): Kick (OAuth + PKCE, refresh, búsqueda de canal) y Twitch (búsqueda de canal, captura de Integrity); la primera corrida encontró y se corrigió un bug de variables GQL (AD-102 (c)). **Sin verificar**: `twitch-account` y `twitch-playback` (requieren Firefox, ver RISK-TWITCH-05). El wiring que este riesgo describía queda CERRADO; lo que sigue abierto aquí es solo `live_monitor` (21d). Sigue abierto: `live_monitor` de Twitch y Kick (21d).

## RISK-UI-02 — `PlatformCapabilities` aún no llega a la UI (FASE 6)
**Severidad:** LOW
**Evidencia:** Master Plan §43: "La UI debe ocultar/deshabilitar funciones no soportadas." `presentation/qml` sigue siendo mock puro (decisión explícita de FASE 2, RISK-UI-01) — no hay ningún bridge QML que exponga `PlatformCapabilities.as_dict()` todavía.
**Impacto:** Ninguno hoy — ninguna página real consume datos de plataforma aún. Si una fase de feature real (FASE 9+) conecta datos sin antes conectar capabilities, podría mostrar controles para funciones que la plataforma activa no soporta (p. ej. "Clips" en Kick).
**Mitigación:** `PlatformCapabilities.as_dict()` ya deja el mapeo bool camelCase listo (ver AD-31) para que la primera fase que conecte una página real a datos de plataforma agregue el bridge QML correspondiente antes o junto con esa conexión.
**Estado:** ABIERTO, informativo — recordar explícitamente en el `docs/phase-state.md` de FASE 9+ antes de cerrar cualquiera de esas fases como PASS. FASE 21b: Favorites/Downloads/History ya leen datos reales, pero ningún bridge expone todavía `PlatformCapabilities.as_dict()` a QML (`FavoritesModel` la consulta internamente solo para decidir `unknown` vs. `live`/`offline`); sigue abierto para 21d (Search/Live/Account).

## RISK-ARCH-02 — `EnqueueDownloadUseCase` sigue con un `PlaybackResolver` único, no `PlatformRegistry`-aware (hallazgo FASE 7)
**Severidad:** LOW hoy (Kick no tiene `PlaybackResolver` de todas formas), potencialmente MEDIUM cuando Kick sí lo tenga.
**Evidencia:** `application/downloads.py::EnqueueDownloadUseCase` (FASE 3) toma `playback: PlaybackResolver` — un único adapter global — en vez de un `PlatformRegistry` (FASE 6) que enrute por `media.ref.platform`. `DownloadExecutor` (FASE 7, nuevo) sí usa `PlatformRegistry.resolve_playback()` correctamente para volver a resolver justo antes de descargar, pero la *validación de calidad al momento de encolar* sigue pasando por ese único resolver de FASE 3.
**Impacto:** Hoy, nulo — el único `PlaybackResolver` real es el de Twitch, y Kick no tiene uno (FASE 5/6). Si una fase futura le da Playback a Kick, encolar una descarga de Kick fallaría o validaría contra el resolver equivocado, a menos que quien conecte todo pase el resolver correcto según el caso de uso concreto (frágil).
**Mitigación:** Cuando aplique, refactorizar `EnqueueDownloadUseCase` para aceptar un `PlatformRegistry` en vez de un `PlaybackResolver` — cambio de constructor, no cosmético, pendiente de ese momento. `EnqueuePlaylistDownloadUseCase` (FASE 12, AD-71) es un caso de uso *nuevo* y separado que sí usa `PlatformRegistry` desde el diseño — no reemplaza a `EnqueueDownloadUseCase` ni cierra este riesgo, que sigue abierto para ese caso de uso específico.
**Estado:** ABIERTO, informativo — no bloqueante para FASE 7 ni para Kick hoy.

## RISK-ARCH-03 — Motor de descargas (FASE 7) sin wirear a `bootstrap/container.py`
**Severidad:** LOW por ahora, bloqueante para quien primero necesite el motor corriendo de verdad.
**Evidencia:** Ver AD-36. `DownloadService`/`DownloadCoordinator`/`DownloadExecutor` existen y están testeados con fakes, pero nada en `bootstrap/dependencies.py` los construye con dependencias reales (httpx real, ffmpeg real, `work_dir` real).
**Impacto:** Ninguno todavía. Bloquea a la primera fase que quiera descargar algo de verdad dentro de la app corriendo.
**Mitigación:** Ensamblar todo en `bootstrap/dependencies.py` cuando esa fase lo requiera.
**Estado:** RESUELTO en FASE 21a — ver docs/architecture-decisions.md's FASE 21a entry para las decisiones que AD-36 dejaba abiertas (worker count, `work_dir`, cliente httpx dedicado, ffmpeg por `PATH`). `Container.download_service` es ahora el `DownloadService` real con `DownloadCoordinator`/`DownloadExecutor`/`SegmentManager`/`FFmpegProcessor` cableados; `tests/test_container.py::test_container_download_service_runs_the_real_pipeline` prueba la tubería completa de punta a punta (sin red/ffmpeg reales, pero con `DownloadQueue`/`DownloadCoordinator`/`DownloadExecutor`/`JobControlStore` reales). Sigue sin poder descargar contenido real de verdad porque `platform_registry` no tiene adapters con credenciales — eso es RISK-ARCH-01, FASE 21c.

## RISK-DATA-01 — Sin bloqueo/concurrencia optimista en escrituras de `Download` (hallazgo FASE 7)
**Severidad:** LOW hoy (repositorio en memoria, un solo proceso), relevante para FASE 8.
**Evidencia:** `DownloadExecutor._transition()`/`_fail()` y `DownloadService.pause()`/`.resume()` hacen todos `downloads.get()` seguido de `downloads.save()` sin ningún control de concurrencia. Si una pausa llega exactamente entre el `get()` y el `save()` de una transición del executor, una de las dos escrituras se pierde silenciosamente (last-write-wins).
**Impacto:** Ninguno observado en los tests (las condiciones de carrera reales necesitan timing exacto entre coroutines), pero es una ventana real, no teórica.
**Mitigación:** Corresponde a "transactions" en el alcance explícito de FASE 8 (Persistence, §45) — no se introduce aquí ninguna solución ad-hoc para no anticipar esa fase.
**Estado:** ABIERTO, informativo — explícitamente delegado a FASE 8.

## RISK-RESUME-01 — Sin recuperación tras caída/reinicio para downloads `PAUSED`; reanudar un directo ya finalizado no puede funcionar
**Severidad:** LOW-MEDIUM.
**Evidencia:** Ver AD-35. `DownloadService.pause()`/`.resume()` solo funcionan mientras el worker en memoria sigue vivo (misma ejecución de la app). Si la app se cierra con un download en `PAUSED` y se reabre, nada vuelve a encolar automáticamente ese `download_id` — y si era un directo (`MediaKind.STREAM`) que mientras tanto terminó, reanudarlo manualmente fallaría de todas formas al volver a resolver playback (`ChannelOfflineError` o similar), porque la URL de reproducción de un directo ya finalizado deja de existir.
**Impacto:** Ninguno todavía (no hay persistencia real ni arranque/cierre de app real que probar en este entorno). Es una limitación inherente a la captura de directos por HLS, no un defecto introducido por FASE 7.
**Mitigación:** Fuera de alcance de FASE 7 (§44 no pide recuperación tras caída). Candidata natural: "safe shutdown" en FASE 8, o una fase de persistencia/lifecycle posterior — decidir ahí si se re-encolan automáticamente los `PAUSED` al arrancar, y documentar explícitamente que un directo finalizado no es reanudable.
**Estado:** ABIERTO, informativo.

## RISK-UX-01 — Pausar un directo no detiene el sondeo del manifiesto en vivo (hallazgo FASE 7)
**Severidad:** LOW (ineficiencia, no incorrección).
**Evidencia:** `DownloadExecutor` pasa `should_stop=is_cancelled` (no `is_paused`) a `HlsPlaylistReader.poll_until_complete`. Mientras un directo está `PAUSED`, el poll de la playlist en vivo sigue ocurriendo cada `poll_interval_seconds` — cada batch nuevo llega a `SegmentManager.download_all()`, que sí se bloquea correctamente sin descargar nada, pero la petición HTTP al manifiesto en sí no se detiene.
**Impacto:** Tráfico de red innecesario mientras está en pausa; ninguna descarga incorrecta (el "saltar si ya existe" de `SegmentManager` hace esto seguro incluso si se optimizara luego reiniciando el poll).
**Mitigación:** Pasar también `is_paused` a `should_stop` y reiniciar el poll al reanudar — la reanudación es segura gracias al skip-si-existe de `SegmentManager`, pero añade complejidad (perder y recrear el generador) no justificada sin datos de uso real (Master Plan §19: "medir antes de optimizar").
**Estado:** ABIERTO, informativo — optimización diferida, no un defecto funcional.

## RISK-DATA-02 — Entidades de §45 sin tabla propia todavía: accounts, platform_accounts, streams, videos, clips, download_segments, download_history, app_events
**Severidad:** LOW — informativo, no bloqueante.
**Evidencia:** Ver AD-39. Ninguna de estas nueve entidades tiene un protocolo de dominio (`domain/protocols.py`) que las consuma hoy, así que no se creó tabla para ellas. (`settings`, la décima, se implementó en FASE 13 — ver AD-75.) FASE 15 confirmó que dos de las nueve restantes **no hacían falta** para su propio alcance: `platform_accounts` no tiene ningún dato duradero que valga la pena persistir aparte del token (que va al credential store, no a una tabla — ver AD-83; `TwitchAccountService.current_account()` ya re-deriva usuario/login en vivo contra la API, sin caché local), y `download_history` no necesitaba ser una tabla separada — el historial legacy migrado se escribió directamente en la tabla `downloads` ya existente (FASE 8), como entradas con `status` terminal.
**Impacto:** Ninguno hoy. Sigue bloqueando a la primera fase que necesite persistir cuentas conectadas (más allá del token) o un log de eventos — `accounts`, `streams`, `videos`, `clips`, `download_segments`, `app_events` siguen sin tabla.
**Mitigación:** Esa fase futura define primero el protocolo de dominio correspondiente (p. ej. `AccountRepository`), y entonces agrega la tabla + migración — no al revés.
**Estado:** ABIERTO, informativo — reducido de nueve entidades a seis tras FASE 15.

## RISK-DATA-03 — Borrado de ítems de playlist vía re-guardado no está probado
**Severidad:** RESUELTO en FASE 12.
**Evidencia:** Ver AD-70. `Playlist.with_item_removed()` existe ahora, y `test_saving_a_playlist_with_an_item_removed_deletes_that_items_row` (persistencia) verifica con una consulta SQL directa que la fila huérfana realmente se borra, no solo se desconecta.
**Estado:** CERRADO.

## RISK-CONCURRENCY-01 — `asyncio.to_thread` sin límite de hilos concurrentes para trabajo de DB
**Severidad:** LOW.
**Evidencia:** Cada llamada a un repositorio lanza su propio `asyncio.to_thread(...)`, que usa el `ThreadPoolExecutor` por defecto de asyncio (tamaño basado en `os.cpu_count()`). No hay un límite explícito ni un pool dedicado para trabajo de DB, a diferencia del motor de descargas (FASE 7) que sí limita workers explícitamente (`DownloadCoordinator`, §19).
**Impacto:** Ninguno observado — el volumen de escrituras concurrentes a SQLite en el uso normal de la app es bajo, y SQLite en sí serializa escrituras a nivel de archivo de todas formas.
**Mitigación:** Si el uso real revela contención, considerar un executor dedicado con límite explícito para trabajo de DB — no se hace ahora sin evidencia (§19: "medir antes de optimizar").
**Estado:** ABIERTO, informativo.

## RISK-PERF-01 — `GetFavoritesLiveStateUseCase` consulta cada favorito de forma secuencial, no en paralelo
**Severidad:** LOW.
**Evidencia:** Ver AD-48. Un `await` por favorito, en un `for`/comprensión de lista — no `asyncio.gather`.
**Impacto:** Ninguno con listas de favoritos de tamaño normal (decenas). Podría notarse con cientos de favoritos y latencia de red real.
**Mitigación:** Paralelizar con `asyncio.gather` cuando haya evidencia real de que hace falta (§19: medir antes de optimizar) — candidata natural: FASE 16 (Performance).
**Estado:** ABIERTO, informativo.

## RISK-ARCH-04 — Solo `favorites` está wireado a `Container`; los otros 5 repositorios de FASE 8 siguen sin conectar
**Severidad:** LOW.
**Evidencia:** Ver AD-50. `Container` ahora tiene `favorites: FavoriteRepository` real, pero `channels`, `downloads`, `playlists`, `scheduled_downloads`, `notifications` siguen sin campo en `Container` — cada uno esperará a la fase que los necesite de verdad (FASE 10 Live Monitor probablemente pide `channels`/`notifications`; FASE 7's motor ya construido pide `downloads`; FASE 11 pide `scheduled_downloads`; FASE 12 pide `playlists`).
**Impacto:** Ninguno hoy.
**Mitigación:** Ninguna necesaria ahora — wirear bajo demanda, fase por fase, como se hizo aquí con favorites.
**Estado:** PARCIALMENTE RESUELTO en FASE 21a — `Container` ahora también tiene `downloads: DownloadRepository`, `notifications: NotificationRepository` y `scheduled_downloads: ScheduledDownloadRepository` reales (los tres que las páginas Downloads/Favorites/History de FASE 21b necesitan). `channels` y `playlists` siguen sin campo en `Container` — ninguno de los dos hace falta para 21b (confirmado contra `application/*.py` antes de agregarlos: nada en `application/favorites.py`/`application/downloads.py`/`application/notifications.py`/`application/scheduled_downloads.py` los requiere) — quedan para cuando FASE 21d (Search/Live/Account) o una fase de Playlists los necesite de verdad, mismo criterio de "wirear bajo demanda" de esta entrada.

## RISK-LIVE-01 — Helix con `WEB_CLIENT_ID` + token de sesión de navegador: sin validar con cuenta real
**Severidad:** MEDIUM.
**Evidencia:** `TwitchBatchLiveStatusProvider` (fallback y reconcile de Twitch) llama a Helix con el mismo par que `TwitchEventSubProvider` (FASE 4d) ya asumía. El endpoint, sus parámetros (`user_id` repetido, ≤100), los campos de respuesta y el manejo de 429 (`Ratelimit-Reset`) están contrastados con la guía oficial y dos librerías cliente; que Twitch acepte ese `Client-Id` con ese token en Helix no se pudo comprobar (Twitch no es alcanzable desde el sandbox).
**Impacto:** Si Helix lo rechaza, los favoritos más allá de las 5 plazas y el reconcile de los push quedan sin estado (los push siguen recibiendo transiciones). Los errores se cuentan (`MonitorStats.errors`) y el monitor hace backoff en vez de fallar.
**Mitigación:** Validar con una cuenta real. Alternativa ya prevista por diseño: otro `BatchLiveStatusProvider` (p. ej. sobre las consultas GQL ya portadas) sin tocar el monitor.
**Estado:** ABIERTO — PENDING validación externa.

## RISK-LIVE-02 — Intervalos por defecto y tamaño de lote de Kick sin medir contra endpoints reales
**Severidad:** MEDIUM.
**Evidencia:** Rate limits oficiales de Kick sin confirmar (kick-audit.md); el máximo de 50 ids proviene de un SDK, no de un texto oficial; 60/180/900 s son valores de partida (AD-54). El benchmark es sintético (transporte en proceso).
**Impacto:** Posible 429 sostenido (mitigado por backoff + `Retry-After`) o latencia de detección mayor a la deseada (hasta 180 s en calma).
**Mitigación:** `LiveMonitorMetrics` (requests, rate_limited, errores, intervalo actual) para ajustar tras una corrida real; `PollingConfig` y `MAX_IDS_PER_REQUEST` son constantes de una línea.
**Estado:** ABIERTO — PENDING medición real.

## RISK-ARCH-05 — Live Monitor y Scheduler sin cablear a `Container`, al ciclo de vida de la app ni entre sí
**Severidad:** LOW (hoy) / requerido antes de tener UI de directos o de scheduled downloads.
**Evidencia:** AD-59, AD-64, AD-68. `LiveMonitorService`, `ScheduledDownloadScheduler`, `AutoDownloadService` y `RecordingService` son construibles y probados de punta a punta con los adaptadores reales (tests de integración con transporte/sockets simulados), pero nadie los crea ni los conecta entre sí dentro de la aplicación real: no se llama `sync()` cuando un favorito cambia, no se corre `RecoverInterruptedDownloadsUseCase` antes de `scheduler.recover()` al arrancar, no se conecta `scheduler.watch_demand()` al `extra_demand` de `LiveMonitorService`, no se pasa el `event_bus` real al `DownloadExecutor`, y no se llama `start()`/`stop()` de cada pieza al abrir/cerrar la app.
**Impacto:** Ninguno hoy (sin UI conectada). Sin este cableado, nada de FASE 10 ni FASE 11 corre dentro de la aplicación real.
**Mitigación:** La fase que cablee adaptadores reales (RISK-ARCH-01/03) lo incluye; todas las piezas son idempotentes/reentrantes por diseño para facilitar ese cableado (`sync()`, `recover()`).
**Estado:** ABIERTO.

## RISK-LIVE-03 — `sync()` prioriza por `position` solo al suscribir; no re-prioriza plazas push
**Severidad:** LOW.
**Evidencia:** Las 5 plazas push las ocupan los primeros favoritos *en el momento de suscribir*. Reordenar favoritos después no mueve canales entre push y fallback; una plaza libre solo se rellena al quitar un canal push. Una suscripción revocada por Twitch degrada el canal a fallback y no se reintenta la promoción por sí sola.
**Impacto:** Un canal sondeado (latencia ≤ intervalo) en vez de push (segundos). No hay pérdida de eventos.
**Mitigación:** Re-promoción periódica o al reordenar, si la latencia importa en la práctica. Una revocación por `authorization_revoked` implica token inválido → el flujo de AUTH_EXPIRED (§22) es lo que corresponde.
**Estado:** ABIERTO, informativo.

## RISK-LIVE-04 — Stream reiniciado entre dos polls no genera offline+online; sin debounce en el monitor
**Severidad:** LOW–MEDIUM (afecta a auto-download en FASE 11).
**Evidencia:** AD-59. Si un streamer corta y reinicia entre dos polls, ambos ven "en directo" y el tracker no emite nada; `Stream.started_at` cambiaría, pero no se sintetizan eventos porque no se verificó que sea estable durante una sesión en Kick. El debounce de notificaciones es de `NotificationService` (§22).
**Impacto:** Auto-download podría seguir grabando la sesión vieja en vez de abrir una nueva; un flap corto puede producir offline→online seguidos (dos eventos legítimos).
**Mitigación:** FASE 11 puede comparar `started_at` del `Stream` que trae cada evento; decidir con datos reales si el monitor debe sintetizar el corte.
**Estado:** ABIERTO.

## RISK-LIVE-05 — Un `stream.online` cuyo detalle falla se recupera con retraso de hasta el intervalo de reconcile
**Severidad:** LOW.
**Evidencia:** AD-56 (2). El evento no se pierde para siempre pero no se reintenta: lo detecta el reconcile lento (base 900 s).
**Impacto:** Notificación de "en directo" retrasada hasta ~15 min en ese caso puntual.
**Mitigación:** Reintento acotado del detalle, o construir el `Stream` mínimo desde el payload del evento. Solo si el caso se observa en la práctica.
**Estado:** ABIERTO, informativo.

## RISK-LIVE-06 — Medición de RSS en Windows no verificada; CPU/RAM son del proceso, no del monitor
**Severidad:** LOW.
**Evidencia:** AD-58. `psutil` se probó contra un proceso real en Linux; el destino es Windows (AD-10) y no hay Windows disponible en el sandbox.
**Impacto:** Ninguno funcional; solo la métrica de memoria/CPU.
**Mitigación:** Ejecutar `benchmarks/live_monitor_bench.py` y el test `tests/infrastructure/monitoring` en Windows (FASE 16/19).
**Estado:** ABIERTO — PENDING validación en Windows.

## RISK-SCHED-01 — El bug de `RecordingService`/Kick (AD-60): ningún test unitario aislado lo habría detectado
**Severidad:** INFORMATIVA — ya corregido en esta misma fase, documentada como lección de proceso.
**Evidencia:** AD-60. El único test que lo detectó fue el de integración de punta a punta con los adaptadores reales de Kick. Los 89 tests unitarios de `tests/application/scheduling/` (con fakes de Twitch) pasaban igual con el bug presente, porque el fake de Twitch sí tenía un `LiveStreamProvider`.
**Impacto:** Ninguno remanente — corregido. Se deja registrado porque es la misma clase de riesgo que RISK-ARCH-05: cualquier componente nuevo de Application que se pruebe solo contra fakes de Twitch (la plataforma "completa") puede ocultar una dependencia que Kick no satisface.
**Mitigación aplicada:** El test de integración de punta a punta con adaptadores reales de Kick es ahora parte permanente de la suite (`tests/test_scheduling_integration.py`), igual que el de FASE 10 lo es para el Live Monitor.
**Estado:** CERRADO — mitigación en efecto.

## RISK-SCHED-02 — `AutoDownloadService`/`ScheduledDownloadScheduler` no persisten reintentos pendientes en memoria entre reinicios
**Severidad:** LOW.
**Evidencia:** `AutoDownloadService._retry_tasks` y `ScheduledDownloadScheduler._retry_at` viven solo en memoria de proceso. Si la app se cierra durante la espera de un backoff, ese reintento en curso se pierde; para `ScheduledDownload` esto se recupera igual en el próximo `recover()`/`tick()` (el estado persistido — `attempts`, `download_id` — es la fuente de verdad, la espera en memoria es solo una optimización de tiempo), pero para `AutoDownloadService` (sin persistencia propia — actúa directo sobre eventos) un reintento en curso simplemente no se reanuda tras un reinicio: hay que esperar el próximo `ChannelWentOnline` real.
**Impacto:** Una descarga automática que falló justo antes de cerrar la app no se reintenta hasta el próximo directo real del canal, en vez de en el backoff calculado.
**Mitigación:** Aceptable dado que el canal seguirá intentándose en cuanto vuelva a estar en vivo; podría persistirse si se observa que importa en la práctica.
**Estado:** ABIERTO, informativo.

## RISK-SCHED-03 — Reintentos de `AutoDownloadService`/`ScheduledDownloadScheduler`: sin límite de reintentos concurrentes entre sí
**Severidad:** LOW.
**Evidencia:** AD-67 evita que dos grabaciones simultáneas ocurran para el mismo canal, pero cada backoff (auto-download y scheduler) es independiente entre sí: si ambos están reintentando el mismo canal por fallos separados, el primero en despertar gana el `RecordingService.start()`, el otro recibe `AlreadyRecordingError` y lo sigue — comportamiento correcto (AD-67), solo se deja constancia de que no hay coordinación explícita de temporización entre ambos backoffs, cada uno calcula el suyo de forma independiente.
**Impacto:** Ninguno funcional — es solo redundancia de temporizadores, absorbida por el lock de canal.
**Mitigación:** Ninguna necesaria; informativo.
**Estado:** ABIERTO, informativo.

## RISK-SCHED-04 — `select_quality` para resoluciones bajo demanda: sin verificar contra el catálogo real de Kick
**Severidad:** LOW.
**Evidencia:** AD-65 se probó contra las etiquetas de calidad que devuelve el resolver de Twitch (ya verificadas en FASE 6); el formato exacto de las etiquetas que devuelve el `PlaybackResolver` de Kick para VOD/directos no se confirmó contra la API real en esta fase (Kick no es alcanzable desde el sandbox — mismo límite que RISK-LIVE-01/02 de FASE 10). Si Kick usa un formato de etiqueta distinto a `"720p60"`, `select_quality` seguiría funcionando (cae a `fell_back=True` con la mejor calidad) pero sin coincidencia exacta de resolución.
**Impacto:** Una preferencia de resolución específica en un favorito de Kick podría no aplicarse exactamente (graba en la mejor calidad igual, no falla).
**Mitigación:** Validar contra una cuenta real de Kick.
**Estado:** ABIERTO — PENDING validación externa.

## RISK-KICK-04 — `KickUnofficialAdapter` (VOD/Clips de Kick) nunca se construyó — confirmado en FASE 12
**Severidad:** MEDIUM.
**Evidencia:** AD-05 (FASE 5) decidió implementar VOD/Clips de Kick como un `KickUnofficialAdapter` aislado. `infrastructure/kick/` (revisado íntegramente en FASE 12) no tiene ningún `PlaybackResolver` — solo `KickChannelDirectory`, `KickAPIClient`, `KickBatchLiveStatusProvider` (FASE 10) y los servicios de cuenta/auth. Confirmado con un test de integración de punta a punta real (AD-73): un ítem de Kick en una playlist falla con "no playable qualities".
**Impacto:** Ninguna descarga de VOD/clip de Kick es posible hoy — ni desde una playlist (FASE 12) ni desde ningún otro flujo, porque el `PlaybackResolver` de Kick simplemente no existe. El directo de Kick (streaming en vivo) no se ve afectado — ese camino no pasa por `PlaybackResolver` para el monitoreo (FASE 10) aunque sí lo necesitaría para *grabar* un directo de Kick vía `RecordingService` (FASE 11) — **lo cual significa que el auto-download y los scheduled downloads de Kick de FASE 11 tienen esta misma dependencia sin resolver**: `RecordingService.start()` llama `registry.available_qualities(media)`, que para Kick devuelve `[]` sin un resolver, así que también fallaría con `RecordingUnavailableError` hoy. Esto no se detectó en FASE 11 porque el test de integración de esa fase no llegó a probar la resolución de calidad de un directo real de Kick de punta a punta (usaba un resolver falso para ese paso específico) — es una laguna de cobertura, distinta del bug de AD-60 (que sí se detectó).
**Mitigación:** Implementar `KickUnofficialAdapter` (Master Plan lo asignó a FASE 5; nunca se hizo). Hasta entonces, tanto la descarga de playlist como el auto-download/scheduled downloads de Kick degradan de forma elegante (reportan el fallo, no rompen nada más) pero no producen ninguna grabación real de contenido de Kick que no sea el propio directo monitoreado.
**Estado:** ABIERTO — bloqueante para cualquier funcionalidad real de descarga de Kick (playlist, auto-download, scheduled downloads), no solo para FASE 12.

## RISK-PLAYLIST-01 — Import/export de playlist: sin validación de tamaño ni límite de ítems
**Severidad:** LOW.
**Evidencia:** `Playlist.from_export_dict()` (AD-74) itera `data["items"]` sin límite. Un dict de import gigantesco (por ejemplo, pegado a mano o de un archivo corrupto) se procesaría entero antes de fallar, si es que falla.
**Impacto:** Ninguno explotado — es una entrada de la propia UI del usuario (exportó su propia playlist), no una superficie de red no confiable. Sigue siendo una función pura sin I/O.
**Mitigación:** Un límite de ítems, si se observa necesario en la práctica (una playlist de miles de ítems ya sería inusual por otras razones de UX).
**Estado:** ABIERTO, informativo.

## RISK-ARCH-06 — `Settings` persistida pero sin conectar a ningún consumidor real todavía
**Severidad:** LOW (hoy) / requerido antes de que la UI de Settings tenga efecto real.
**Evidencia:** AD-75/76/77. `GetSettingsUseCase`/`UpdateSettingsUseCase`/`ResetSettingsUseCase` funcionan y están probados de punta a punta contra la base de datos real, pero ningún componente construido en fases anteriores lee `Settings` todavía: `DownloadCoordinator` sigue tomando `worker_count` como parámetro fijo del llamador (no de `settings.max_concurrent_downloads`), `RetryPolicy` de descargas se construye con sus propios valores por defecto (no `settings.retry_*`), `PollingConfig.base_interval` (FASE 10) no lee `settings.live_monitor_poll_interval_seconds`, y `DownloadExecutor.work_dir` no lee `settings.temp_directory`.
**Impacto:** Ninguno hoy (sin UI conectada). Cambiar un valor en la futura pantalla de Settings no tendría ningún efecto real hasta que se cablee.
**Mitigación:** Mismo tratamiento que RISK-ARCH-05 — la fase que cablee el `Container` real debe leer `Settings` al construir cada componente que hoy toma esos valores como parámetro fijo, en vez de asumir que existir en la base de datos alcanza.
**Estado:** ABIERTO. Actualización 21c: el `httpx.AsyncClient` que crea `build_platform_adapters()` (compartido por Twitch y Kick) tampoco se cierra en el cierre; entra en el mismo arreglo de 21d.

## RISK-ARCH-07 — El `DirectoryBackupInstaller` es un instalador provisional; el instalador real depende de una decisión de FASE 19 que no existe
**Severidad:** MEDIUM — bloqueante para un release real, no para el desarrollo.
**Evidencia:** AD-78. Master Plan §51 lista "packaging strategy" como prerrequisito de FASE 14; FASE 19 (Packaging) sigue sin empezar. `DirectoryBackupInstaller` asume que la app se distribuye como "un directorio de archivos" reemplazable por un zip — funciona y está probado, pero no es necesariamente cómo la app termine empaquetándose de verdad (un instalador de Windows, un bundle firmado, etc. tendrían mecanismos de reemplazo/rollback completamente distintos, y probablemente necesiten cerrar la app antes de reemplazar sus propios archivos en ejecución — algo que este instalador tampoco maneja).
**Impacto:** Ninguno en desarrollo/pruebas. Un release real con este instalador tal cual podría fallar en Windows si la app está corriendo desde el mismo directorio que se intenta sobreescribir (archivos bloqueados por el propio proceso).
**Mitigación:** Cuando FASE 19 decida el empaquetado real, implementar el `UpdateInstaller` correspondiente — el protocolo ya existe y `UpdateService` no necesita cambios.
**Estado:** PARCIALMENTE MITIGADO EN FASE 19 — AD-94 decide explícitamente distribuir como directorio (`--onedir` de PyInstaller + zip portátil), lo que valida el supuesto de `DirectoryBackupInstaller` en vez de dejarlo como una suposición no confirmada: la forma de distribución real ya decidida SÍ es "un directorio de archivos reemplazable". Sigue sin resolverse la segunda mitad de este riesgo — `DirectoryBackupInstaller` todavía no maneja el caso de reemplazar archivos que el propio proceso en ejecución tiene abiertos/bloqueados en Windows (cerrar la app antes de sobreescribir) — eso sigue perteneciendo al `UpdateInstaller`/`UpdateService` (RISK-ARCH-05), no a esta fase de empaquetado. Bloqueante para un release real de auto-actualización, no para la existencia del bundle en sí.

## RISK-SEC-02 — La clave pública embebida para verificar manifiestos de actualización es una clave de desarrollo, no la clave de release
**Severidad:** ALTA si se ignora antes de un release real; NINGUNA hoy.
**Evidencia:** AD-79. `infrastructure/updates/config.py::PUBLIC_KEY_PEM` es un par de claves Ed25519 genuino, generado específicamente para este proyecto en esta fase — pero nadie controla su clave privada de forma operacional (no vive en ningún sistema de firmado de releases, es solo un artefacto de desarrollo). Servir un manifiesto firmado con esta clave nunca podría pasar por un canal de distribución real de todos modos (no hay ningún servidor real en `MANIFEST_URL`).
**Impacto:** Ninguno mientras el proyecto no tenga un pipeline de release real. Si `PUBLIC_KEY_PEM` se copiara a un release real sin reemplazarla, cualquiera con la clave privada (que está en el historial de este repositorio, generada en este mismo turno) podría firmar actualizaciones maliciosas válidas.
**Mitigación:** Antes de cualquier release real: generar un par de claves nuevo con la clave privada resguardada fuera de este repositorio (idealmente en un HSM o un secreto de CI), y reemplazar `PUBLIC_KEY_PEM`.
**Estado:** ABIERTO — acción de release, no de desarrollo.

## RISK-MIGRATION-01 — El backup de FASE 15 y (si el usuario no lo borra) el propio `settings.json` legacy quedan con el token de Twitch en texto plano, sin cifrar
**Severidad:** MEDIUM.
**Evidencia:** AD-83. `legacy_locator.backup()` copia el archivo legacy byte a byte — necesario para que el backup sirva como red de reversibilidad real (un backup redactado no permitiría auditar qué se migró exactamente) — pero eso significa que el secreto que `RISK-SEC-01` señalaba como problema en el JSON legacy ahora también existe, sin cifrar, en el directorio de datos de Twick Hub. El `settings.json` original tampoco se purga (decisión consciente, ver AD-83) — sigue con el secreto en texto plano donde siempre estuvo, sin cambio de esta fase.
**Impacto:** Cualquiera con acceso al sistema de archivos del usuario (otro proceso, un backup de disco completo, malware con permisos de usuario) podría leer el token de sesión de Twitch desde el backup de la migración, además de desde el `settings.json` legacy original si aún existe.
**Mitigación:** Ninguna implementada en esta fase. Opciones para una fase futura: cifrar el backup con una clave derivada del propio credential store del SO; ofrecer una acción explícita y opt-in ("purgar TwitchLink legacy") que redacte el token tanto del backup como del original tras confirmar que la migración fue exitosa; o simplemente documentar y dejar que el usuario borre ambos archivos manualmente una vez migrado.
**Estado:** ABIERTO, informativo — el riesgo ya existía antes de esta fase (el `settings.json` original); esta fase lo extiende a una segunda copia (el backup) sin resolver ninguna de las dos.

## RISK-MIGRATION-02 — `rollback()` no puede deshacer el historial de descargas migrado
**Severidad:** LOW.
**Evidencia:** AD-84. `DownloadRepository` no tiene operación `delete()` en ningún punto de la aplicación (el historial de descargas se trata como solo-append en todas las fases anteriores) — agregarla únicamente para esta fase habría sido una capacidad inventada fuera de alcance (Master Plan §0.5). `tests/application/test_legacy_migration.py::test_rollback_does_not_remove_migrated_download_history` deja esto como comportamiento esperado y probado, no como un olvido.
**Impacto:** Tras un `rollback()`, favoritos/scheduled-downloads/settings/token vuelven exactamente a como estaban antes de migrar, pero las filas de `downloads` creadas a partir del historial legacy permanecen. Un usuario que decida "deshacer la migración" seguiría viendo ese historial importado en su lista de descargas.
**Mitigación:** Si una fase futura agrega `DownloadRepository.delete()` por otra razón (p. ej. "borrar una descarga de mi historial" como función de UI), `rollback()` podría extenderse para usarla también. No se justifica agregarla solo por esto.
**Estado:** ABIERTO, informativo — "reversible" (Master Plan §52) se cumple para todo excepto el historial de descargas, documentado explícitamente en vez de asumido.

## RISK-MIGRATION-03 — Varios campos de preferencia legacy no tienen ningún destino en el modelo de datos actual de Twick Hub y se migran con pérdida de fidelidad documentada
**Severidad:** LOW.
**Evidencia:** AD-85, AD-87. Sin campo destino: plantillas de nombre de archivo por tipo de contenido (`Templates.*`), huso horario (`Localization._timezone`), el interruptor "buscar contenido externo" (`Advanced._searchExternalContent`), y la preferencia de frame-rate por scheduled-download (`preferredFrameRateIndex`). Con destino único pero legacy tenía varios: `default_directory`/`default_format` de `Settings` son globales; legacy los guardaba por separado para Stream/Video/Clip/Thumbnail/Scheduled — solo `StreamHistory` se usa como fuente (AD-85).
**Impacto:** Ninguno funcional (la app sigue operando con sus propios valores por defecto para lo que no se migró) — es una pérdida de *preferencia personalizada* del usuario, no de datos irrecuperables (el `settings.json` legacy y su backup conservan el valor original completo, sin tocar).
**Mitigación:** Si una fase futura agrega campos de `Settings`/`Favorite`/`ScheduledDownload` para plantilla de nombre configurable, huso horario, o directorio/formato por tipo de contenido, `legacy_transform.py` podría extenderse para migrarlos entonces — sin necesidad de releer el archivo legacy otra vez, ya que el backup de esta fase lo conserva íntegro.
**Estado:** ABIERTO, informativo.

## RISK-MIGRATION-04 — La resolución de canal (login → id numérico) para bookmarks y scheduled downloads no se validó contra la API real de Twitch
**Severidad:** MEDIUM (bloqueante para probar ese camino específico con una cuenta real; no bloqueante para el resto de la fase).
**Evidencia:** AD-86. `ChannelDirectory.find_channel(login)` se ejercitó completo en `tests/application/test_legacy_migration.py` contra un `FakeChannelDirectory` — nunca contra la API real de Twitch, porque este sandbox no tiene acceso a red (mismo límite que RISK-LIVE-01/RISK-TWITCH-02/RISK-KICK-03 de fases anteriores).
**Impacto:** El comportamiento de "canal no resuelto → se registra en skipped, no bloquea el resto" está probado; lo que no está confirmado es que `find_channel()` real, contra logins reales de una cuenta con bookmarks reales, se comporte exactamente como el fake asume (por ejemplo, ante un login renombrado o baneado desde que se guardó el bookmark).
**Mitigación:** Validar `LegacyMigrationService.run()` de punta a punta contra una cuenta de Twitch real con bookmarks/scheduled-downloads legacy reales, la primera vez que el proyecto tenga acceso a red para probarlo.
**Estado:** ABIERTO — PENDING validación externa, mismo patrón que los riesgos de red heredados.

## RISK-MIGRATION-05 — El sandbox de esta fase no tuvo acceso a red: SQLAlchemy/Alembic/pytest/ruff/pyright no se pudieron instalar ni ejecutar
**Severidad:** MEDIUM — bloqueante para declarar PASS con evidencia completa según Master Plan §0.7; no indica ningún defecto conocido.
**Evidencia:** `pip install sqlalchemy` (y alembic/pytest/pytest-asyncio) devolvió "No matching distribution found" — sin caché local ni índice alcanzable. Todo el código puro (domain, `infrastructure/migration/*`, `application/migration.py`) se verificó igual, ejecutándolo directamente con un fixture legacy sintético completo y un arnés mínimo compatible con pytest escrito para esta sesión (139 casos, 0 fallos) — ver `docs/phase-state.md` de esta fase para el detalle exacto. Lo que **no** se pudo ejecutar: los 10 tests de `tests/infrastructure/persistence/test_legacy_migration_run_repository.py`, los 3 tests nuevos/modificados de `tests/infrastructure/persistence/test_migrations.py` (necesitan SQLAlchemy/Alembic reales), ni `ruff`/`pyright` (sustituidos parcialmente por un chequeo manual de imports no usados vía `ast` y un chequeo de longitud de línea — ninguno de los dos es un sustituto completo de esas herramientas), ni la suite completa preexistente de 806 tests (para confirmar ausencia de regresión más allá de la revisión manual de que los cambios en `protocols.py`/`models.py`/`mappers.py`/`enums.py` son puramente aditivos).
**Impacto:** Ninguno conocido — el código de la capa de persistencia de esta fase sigue exactamente el patrón ya probado de `update_attempt_repository.py`/`e7a2b8c4f610_update_attempts_fase14.py` (FASE 14), campo por campo. Pero "sigue el patrón" es una verificación por inspección, no la evidencia automatizada que Master Plan §0.7 exige.
**Mitigación:** Ejecutar, en un entorno con acceso a red o con las dependencias ya instaladas: `pip install -e .[dev]` (o equivalente), luego `pytest`, `ruff check src/twick_hub tests`, y `pyright src/twick_hub tests`. Si algo falla, es responsabilidad de la primera sesión con ese acceso corregirlo antes de considerar esta fase verificada por completo.
**Estado:** CERRADO en FASE 16 — esta sesión sí tuvo acceso a red (`pip install` a PyPI funcionó). Se instaló el proyecto real en un venv (`pip install -e ".[dev]"`: SQLAlchemy 2.1.1, Alembic 1.20.0, pytest 9.1.1, PySide6 6.11.2, ruff 0.16.9, pyright 1.1.414) y se corrió todo lo que quedaba pendiente: `pytest` completo → 958/958 pasando (incluye los 10+3 tests de FASE 15 antes solo escritos); `alembic upgrade head` y `downgrade base` reales contra un SQLite fresco, cadena FASE 8→15 completa, ambos sentidos limpios; `ruff check .` encontró 46 errores reales nunca antes detectados (imports desordenados, líneas largas, 3 `assert pytest.raises(Exception)` demasiado amplios, todos en archivos propios de FASE 15) — los 38 corregibles se corrigieron, quedan 8 `E501` solo en `migrations/versions/*` autogenerado de FASE 8/11 (fuera de alcance de lint por la misma convención que ya existía para pyright); `pyright` bajó de 30 errores reales a 0 con fixes quirúrgicos (un `assert` de invariante ya garantizado, un `None`-check, y tipado de dos test-helpers). Ver AD-88.

## RISK-SEC-03 — (FASE 17, CERRADO en la misma fase) `KickOAuthFlow.revoke()` mandaba el token de acceso/refresh como query string
**Severidad:** MEDIUM al encontrarse — ninguna explotación conocida, pero exposición estructural innecesaria de un secreto (más propenso a log de proxy/httpx/excepción que el mismo valor en el cuerpo de una petición).
**Evidencia:** `oauth_flow.py::revoke()` usaba `params={"token": token, ...}`. Ver AD-90.
**Impacto:** Ninguno explotado — `KickOAuthFlow` no está cableado a `bootstrap/dependencies.py` todavía (mismo patrón que RISK-ARCH-01: Kick OAuth no conectado a UI real), así que este camino no corría en producción hoy. El riesgo era para el momento en que sí se conecte.
**Mitigación:** Implementada en FASE 17 — token movido a `data=` (cuerpo del POST), alineado con RFC 7009. Ver AD-90.
**Estado:** CERRADO en FASE 17.

## RISK-SEC-04 — (FASE 17, CERRADO en la misma fase) `IntegrityAdapter._begin_capture`: carrera timeout-vs-señal-tardía podía duplicar la petición de Integrity con el token del usuario
**Severidad:** MEDIUM al encontrarse — mismo patrón de "aceptado, sin mitigación estructural" que ya cubría RISK-TWITCH-04, pero esto era un defecto de implementación concreto (una carrera real), no solo el riesgo de mantenimiento ya documentado ahí.
**Evidencia:** Ver AD-91. La señal `intercepted` del interceptor de Chromium cruza de su propio hilo IO a la GUI vía conexión en cola; sin guard, podía entregarse después de que un timeout ya hubiera resuelto la captura, disparando una segunda petición POST real a `INTEGRITY_URL` con `Authorization: OAuth <token>` adjunto, y potencialmente invocando el callback dos veces.
**Impacto:** Ninguno explotado — no se pudo verificar contra un Chromium/Twitch reales en ningún sandbox de este proyecto hasta ahora (mismo límite de RISK-TWITCH-04). El riesgo era teórico pero real por construcción (no depende de comportamiento anómalo de Twitch, solo del propio scheduling de Qt entre hilos).
**Mitigación:** Implementada en FASE 17 — guard `_SettleOnce` + desconexión explícita de señales en `_cleanup()`. Ver AD-91. **Verificación parcial:** el guard en sí (`_SettleOnce`) se probó aislado y en verde; su conexión efectiva dentro de `_begin_capture` en las tres rutas se verificó por inspección de código, no por un test Qt real (bloqueado por la misma falta de Chromium-sandboxeado-como-no-root/red-hacia-Twitch que ya documentaba este módulo antes de esta fase) — ver `docs/phase-state.md` de esta fase.
**Estado:** CERRADO en FASE 17 en cuanto a la corrección de código; la verificación end-to-end contra Qt/Chromium reales queda PENDING, mismo patrón heredado que RISK-TWITCH-04.

## RISK-ARCH-08 — (FASE 17, informativo) `LocalHttpRedirectListener` (Kick OAuth) sigue sin cablearse a `bootstrap/dependencies.py`
**Severidad:** LOW — mismo patrón que RISK-ARCH-01, confirmado de nuevo durante la auditoría de FASE 17.
**Evidencia:** `grep` de `LocalHttpRedirectListener` en `src/twick_hub/bootstrap/` no devuelve ninguna construcción real — solo la clase y sus tests. El hardening de FASE 17 a este módulo (AD-92) es correcto pero no tiene ningún camino de ejecución real en la app hoy.
**Impacto:** Ninguno hoy. Bloquea a la primera fase que conecte el flujo de login de Kick a una UI real: esa fase debe construir `LocalHttpRedirectListener` con un host explícitamente loopback (`127.0.0.1`, no confiar en que "localhost" resuelva siempre así) y decidir qué componente posee su ciclo de vida.
**Mitigación:** Ninguna requerida en FASE 17 — informativo, mismo tratamiento que RISK-ARCH-01/RISK-UI-02 (recordar explícitamente en el `docs/phase-state.md` de la fase que finalmente conecte Kick OAuth a la UI).
**Estado:** ABIERTO, informativo.

## RISK-LINT-01 — (FASE 17, informativo) 3 hallazgos de `ruff` preexistentes, ajenos al alcance de esta fase — CERRADO EN FASE 18
**Severidad:** LOW — estilo únicamente (imports desordenados), no seguridad ni comportamiento.
**Evidencia:** `ruff check src/twick_hub tests` (venv de esta fase) encuentra 3 errores `I001` en `src/twick_hub/infrastructure/migration/legacy_codec.py`, `src/twick_hub/infrastructure/persistence/mappers.py`, y `tests/infrastructure/migration/test_legacy_codec.py` — ninguno en archivos tocados por FASE 17. `docs/phase-state.md` de FASE 16 no los mencionaba (reportaba 0 errores propios del proyecto, solo 8 `E501` aceptados en `migrations/versions/`), así que son un hallazgo nuevo para este linaje, no una regresión de esta fase.
**Impacto:** Ninguno — cosmético, `ruff --fix` los resuelve automáticamente.
**Mitigación:** Fuera de alcance de FASE 17 (Master Plan §0.5: no corregir lo que no pertenece a esta fase salvo que sea necesario para estabilidad/seguridad — no lo es). Candidata natural: FASE 18 (Testing), que ya tiene "ejecutar pytest/ruff/pyright" en su propio alcance.
**Estado:** CERRADO en FASE 18 — `ruff check . --fix` corrido sobre todo el proyecto (no solo los 3 archivos originales): 42 hallazgos autofixeados (I001 en los 3 archivos originales + 2 más tocados por esta fase — `tests/infrastructure/migration/test_legacy_codec.py` y `tests/infrastructure/twitch/test_browser_cookie_import.py` —, más `UP035`/`UP007` en `migrations/versions/*.py` y `UP017` en `legacy_codec.py`, ya presentes pero no descritos en el hallazgo original de FASE 17). `pytest` completo re-corrido después del fix: 1029/1029 en verde, sin regresiones. Quedan 8 `E501` en `migrations/versions/*.py` — el mismo conjunto ya aceptado explícitamente desde FASE 16 (DDL de Alembic autogenerado, líneas largas por definición de columnas/constraints; envolverlas perjudicaría la legibilidad sin beneficio real). `ruff check .` final: **8 errores, los 8 ya aceptados — 0 nuevos**.

## RISK-PERF-02 — El punto "thumbnail cache" del checklist de FASE 16 no tiene ningún código que medir
**Severidad:** LOW — informativo, no bloqueante.
**Evidencia:** `grep` en `src/twick_hub` de `thumbnail|image_cache` no devuelve ningún módulo de infraestructura o aplicación — solo el principio arquitectónico general mencionado en el Master Plan ("async + LRU-cached + resized thumbnails"). El wiring de UI real que lo necesitaría sigue diferido (RISK-ARCH-01, RISK-UI-02).
**Impacto:** Ninguno — no se puede medir el rendimiento de algo que no existe. Documentado explícitamente en vez de omitido en silencio o sustituido por una medición inventada.
**Mitigación:** Cuando una fase futura construya el thumbnail cache real (candidata natural: la fase que finalmente conecte `PlatformRegistry`/Container a la UI), medirlo entonces con el mismo arnés (`benchmarks/fase16_performance_audit.py` puede extenderse).
**Estado:** ABIERTO, informativo.

## RISK-PERF-03 — La medición de "visible vs. minimizado" de FASE 16 no se pudo diferenciar: no existe código que dependa de la visibilidad de la ventana
**Severidad:** LOW — informativo, no bloqueante.
**Evidencia:** `grep` de `minimiz|WindowState|isMinimized|visibility` en `src/twick_hub` solo encuentra el campo de configuración `Settings.minimize_to_tray` (persistido, nunca leído por ninguna lógica de reducir trabajo). El principio "reduced work when minimized" del Master Plan (stack y arquitectura) está declarado pero no implementado.
**Impacto:** Ninguno — medir "visible" y "minimizado" por separado hoy produciría el mismo número dos veces, no evidencia real de nada.
**Mitigación:** Cuando la UI real esté conectada (misma fase candidata que RISK-PERF-02), implementar la reducción de trabajo al minimizar y entonces sí medir la diferencia.
**Estado:** ABIERTO, informativo.

## RISK-PERF-04 — Las mediciones de EventSub (Twitch) y polling (Kick) de FASE 16 corrieron contra un servidor local, no contra la red real de la plataforma
**Severidad:** MEDIUM — mismo patrón heredado de RISK-LIVE-01/RISK-TWITCH-02/RISK-KICK-03/RISK-MIGRATION-04; no bloqueante para el resto de la fase.
**Evidencia:** Este sandbox tiene red hacia PyPI/GitHub/npm (confirmado en FASE 16, retiró RISK-MIGRATION-05) pero no hacia `twitch.tv`/`kick.com`. `measure_twitch_eventsub_local()` en `benchmarks/fase16_performance_audit.py` ejercita el `TwitchEventSubProvider` real contra un servidor `websockets` local (session_welcome + keepalives reales, mismo transporte) inyectando el conector; `measure_kick_polling()` reutiliza el bench real de FASE 10 (`live_monitor_bench.py`, `httpx.MockTransport`).
**Impacto:** Los números de CPU/RSS/latencia de conexión son reales para el código del proyecto, pero no confirman comportamiento bajo latencia de red real, límites de tasa reales, ni bajo un reconnect/resubscribe real contra Twitch/Kick.
**Mitigación:** Repetir ambas mediciones la primera vez que el proyecto tenga red hacia esas plataformas con una cuenta real.
**Estado:** ABIERTO — PENDING validación externa.

## RISK-TEST-01 — (FASE 18, informativo) `Version._sort_key` es código muerto: nunca se invoca
**Severidad:** LOW — informativo, cero impacto en comportamiento o seguridad.
**Evidencia:** `grep -rn "_sort_key" src/twick_hub tests` sólo devuelve la propia definición del método en `src/twick_hub/domain/version.py` — ningún llamador, ni en `__lt__`/`__le__`/`__gt__`/`__ge__` (que reimplementan la comparación directamente sin usarlo) ni en ningún otro módulo. Surgió al medir cobertura real para esta fase: la línea de su único `return` (línea 50) era la única de todo `domain/version.py` que ninguna de las dos rutas — código de producción o test — podía alcanzar nunca, a diferencia del resto de huecos de cobertura de esta fase, que sí eran alcanzables y se cerraron con tests reales (ver `docs/phase-state.md` de FASE 18).
**Impacto:** Ninguno hoy — el método no se ejecuta nunca, así que no puede estar mal. Es deuda menor: alguien podría asumir que participa en el ordenamiento y sorprenderse al modificarlo sin efecto.
**Mitigación:** Fuera de alcance de FASE 18 (mandato de la fase es Testing, no refactor/limpieza — Master Plan §0.5). Eliminar el método (o cablearlo de verdad a los operadores de comparación, si en algún momento se prefiere esa implementación sobre la actual) es una limpieza trivial y de riesgo cero para quien la aborde: no requiere entender nada que no esté ya documentado aquí.
**Estado:** ABIERTO, informativo.

## RISK-PKG-02 — (FASE 19) Una instalación nueva no tiene ningún mecanismo que cree el esquema de base de datos
**Severidad:** MEDIUM — bloqueante para que una instalación nueva real funcione, no para que el bundle se construya o arranque.
**Evidencia:** `bootstrap/dependencies.py::build_container()` llama a `build_engine(config)` → `create_engine(config.resolved_database_url(), future=True)` — solo abre la conexión, nunca crea tablas ni corre `alembic upgrade head`. `README.md` documenta ese comando como un paso manual (`.venv/bin/alembic upgrade head`) que un desarrollador corre en su propio checkout. Confirmado por `grep` en `src/twick_hub`: ningún módulo importa `alembic.command` ni llama `Base.metadata.create_all()`.
**Impacto:** El binario congelado que produce esta fase arranca correctamente (smoke test real, ver docs/packaging.md) y abre una conexión SQLite a un archivo nuevo, pero ese archivo queda sin ninguna tabla — cualquier caso de uso real que lea/escriba a través de `session_factory` fallaría contra una instalación limpia de un usuario final. Hoy no es observable porque ningún flujo real está cableado a la UI todavía (RISK-ARCH-01/03/04/05) — el problema se vuelve visible en cuanto la primera fase conecte de verdad `favorites`/`downloads`/etc. a una ventana real.
**Mitigación:** Ensamblar y correr `alembic.command.upgrade(cfg, "head")` mediante `alembic.config.Config` construido desde `AppConfig` (mismo patrón que ya usa `migrations/env.py`) como parte de `build_container()`, solo si la base de datos está en su versión inicial o vacía — no implementado en esta fase porque toca el arranque real de la app (fuera del alcance estricto de "empaquetar lo que ya existe", Master Plan §0.5) y merece sus propios tests de migración-en-frío, no una adición apurada al cierre de Packaging. Documentado aquí para que la fase que cablee el `Container` real (candidata: la misma que resuelva RISK-ARCH-01/03) no lo pase por alto.
**Estado:** RESUELTO para instalación fuente/editable (inmediatamente después de cerrar FASE 21a, antes de empezar 21b — este riesgo se había vuelto bloqueante para 21b, como la actualización anterior de esta entrada señalaba). `src/twick_hub/bootstrap/migrations.py::ensure_schema_migrated(engine)` corre `alembic upgrade head` en el mismo proceso, compartiendo la conexión del `Engine` real vía `config.attributes["connection"]` (idioma estándar de Alembic para uso programático — ver el nuevo branch en `migrations/env.py`) en vez de que `env.py` re-derive su propia URL con `load_config()` (lo cual habría ignorado el `AppConfig` real que `build_container()` ya construyó, y habría apuntado a una base de datos `:memory:` distinta e inalcanzable en el caso de un `AppConfig` de test). `main.py::main()` la llama una sola vez, justo después de `build_container()` — deliberadamente **no** dentro de `build_container()` mismo, porque esa función la llaman casi todos los tests de la suite, muchos contra `sqlite:///:memory:`, donde correr migraciones sería inútil o directamente incorrecto (ver el docstring del módulo nuevo). Verificado con un smoke test real (no solo tests unitarios): `main()` corrido de punta a punta contra un directorio de datos genuinamente vacío (`QT_QPA_PLATFORM=offscreen`, sin ningún `.db` preexistente) crea las 10 tablas esperadas + `alembic_version`, la app arranca y cierra con código 0. `tests/test_bootstrap_migrations.py` (nuevo) cubre además: creación desde cero, idempotencia (llamar dos veces no falla), y un `Container` usable sin ningún `Base.metadata.create_all()` manual — el escenario exacto que esta entrada describía.
**Hueco que queda, no resuelto por este fix:** el bundle congelado de PyInstaller (FASE 19) no empaqueta `alembic.ini`/`migrations/` (confirmado: `packaging/pyinstaller/twick_hub.spec`'s `datas` solo tiene el directorio QML) ni resuelve esas rutas vía `runtime_paths.package_root()` (el mecanismo que AD-97 ya resolvió para QML) — `ensure_schema_migrated()` solo funciona hoy en una instalación fuente/editable. Sin impacto inmediato porque el `.exe` real de FASE 19 sigue sin existir (ningún bundle congelado real para que esto rompa hoy) — pendiente para quien retome Packaging con una máquina Windows real.

## RISK-PKG-03 — (FASE 19) El bundle de PyInstaller pesa ~516 MB; ~420 MB son PySide6, dominado por `Qt/lib` con módulos Qt que la app no usa
**Severidad:** LOW/MEDIUM — no afecta corrección ni arranque (verificado), solo tamaño de descarga/instalación.
**Evidencia:** Build real con `packaging/pyinstaller/twick_hub.spec` en este sandbox (Linux, smoke test — ver docs/packaging.md): `dist/TwickHub` = 516 MB, de los cuales `_internal/PySide6` = 420 MB, y de eso `Qt/lib` = 359 MB, `Qt/qml` = 30 MB, `Qt/plugins` ≈ 6 MB, `Qt/translations` = 8.5 MB. La app solo usa `QtCore`/`QtGui`/`QtQml`/`QtQuick`/`QtQuick.Controls.Basic`/`QtQuick.Layouts`/`QtQuick.Window`/`QtNetwork` (uso indirecto vía Qt) — pero el hook oficial de PyInstaller para PySide6 (`PyInstaller/hooks/hook-PySide6.QtQml.py` → `pyside6_library_info.collect_qtqml_files()`, en `PyInstaller/utils/hooks/qt/__init__.py`) recorre con `rglob('**/qmldir')` el árbol QML **completo** de Qt sin ningún filtro configurable (no expone `hooksconfig` para excluir módulos), y el resto de `Qt/lib` se arrastra por el mismo patrón de "todo o nada" del empaquetado oficial de Qt — confirmado inspeccionando el código fuente del hook instalado, no supuesto. Resultado: `Qt3D*`, `QtWebEngine*`, `QtMultimedia*`, `QtCharts`, `QtDataVisualization`, `QtRemoteObjects`, `QtScxml`, `QtSensors`, `QtLocation`, `QtPositioning`, `QtTextToSpeech`, `QtTest`, `QtWebChannel`, `QtWebSockets`, `QtWebView`, `Qt5Compat`, entre otros, terminan en el bundle sin que ninguna línea de la app los importe.
**Impacto:** Descarga/instalación más pesada de lo necesario para el usuario final; no afecta funcionalidad (el smoke test offscreen real de FASE 19 arrancó correctamente con el bundle sin podar).
**Mitigación (no implementada esta fase — Master Plan §11 "la eficiencia debe medirse, no asumirse": la medición ya está hecha; el recorte queda como trabajo concreto y acotado para quien lo aborde):** un paso de poda posterior al build (script, no parte del `.spec` declarativo) que elimine de `dist/TwickHub/_internal/PySide6/Qt/lib/` y `Qt/qml/` los módulos listados arriba por nombre, seguido siempre de re-correr el mismo smoke test offscreen de `docs/packaging.md` antes de dar la poda por buena — nunca podar y asumir que sigue funcionando sin volver a arrancar el binario.
**Estado:** ABIERTO, informativo — no bloqueante para el cierre de FASE 19 (el bundle sin podar es correcto y arranca; esto es una optimización de tamaño, no un defecto).


## RISK-UI-03 — Favoritos muestran el id de plataforma, no el nombre del canal (hallazgo FASE 21b)
**Severidad:** MEDIUM
**Evidencia:** `Favorite` guarda solo `channel_ref` (por diseño, FASE 9) y `AddFavoriteUseCase` no persiste el `Channel` resuelto en `ChannelRepository`; además `Container` no expone `channels`. Para Twitch `external_id` es el id numérico de usuario (`gql/mappers.py`), no el login. `FavoritesModel` usa `external_id` como etiqueta.
**Impacto:** con datos reales, la tarjeta de un favorito de Twitch diría `12345`, no `northernlion`.
**Mitigación:** en 21c/21d, hacer que `AddFavoriteUseCase` guarde el `Channel` en `ChannelRepository`, cablear `channels` en `Container` y que `FavoritesModel` resuelva el nombre desde ahí (fallback a `external_id`).
**Estado:** ABIERTO.

## RISK-PERF-05 — El historial carga todos los registros terminales sin paginar (FASE 21b)
**Severidad:** LOW
**Evidencia:** `ListDownloadHistoryUseCase` usa `DownloadRepository.list_by_status`, que no admite `limit`/`offset` (FASE 8 paginó solo `list_all`); ampliar el Protocol es un cambio de API pública, fuera de 21b.
**Mitigación:** cuando el historial real crezca, añadir `limit`/`offset` opcionales a `list_by_status` (retrocompatible) y paginar en `HistoryModel`. No optimizar sin medir (Master Plan §11).
**Estado:** ABIERTO, informativo.

## RISK-ARCH-09 — El ciclo de vida del motor de descargas no participa en el cierre de `Application` (FASE 21b)
**Severidad:** LOW hoy, MEDIUM en cuanto 21d permita encolar descargas desde la UI
**Evidencia:** `Application._shutdown()` solo hace `engine.dispose()`. Nadie llama `DownloadService.stop()` ni `aclose()` del `httpx.AsyncClient` creado en `_build_download_service` (21a). El coordinador arranca de forma perezosa en el primer `enqueue`, y ninguna UI encola todavía, así que hoy no hay workers vivos al cerrar.
**Mitigación:** IMPLEMENTADA en 22.1 (AD-103): `Container.closers` + `Application` cierran workers y los dos clientes HTTP antes de `engine.dispose()`; una cancelación ahora también mata a ffmpeg. La página Downloads tampoco ofrece pausar/reanudar (el mock nunca lo tuvo; `DownloadService.pause/resume` existen): 22.4.
**Estado:** CERRADO en 22.1. Lo que queda de "cerrar a mitad de descarga" (fila en `DOWNLOADING`, archivo parcial) se sigue en 22.6 y RISK-RESUME-02.


## RISK-UI-04 — `HomePage.qml` (página de inicio) sigue 100 % mock y contradice a las páginas reales (hallazgo FASE 21e)
**Severidad:** MEDIUM al encontrarse; LOW para lo que queda abierto (ver Estado).
**Evidencia:** captura real con BD sembrada (2 favoritos, 1 descarga activa): Home mostraba "Live now 2 / Downloads in progress 3 / Favorites 12" y "Recent activity" con northernlion/xqc/hasanabi, todos literales en `HomePage.qml` (`model: [ ... ]`). FASE_21_INTEGRACION_FINAL.md listaba 6 páginas mock y omitía Home, que es la página por defecto (`NavigationController._current_page_id = "home"`).
**Impacto:** lo primero que veía el usuario eran números falsos que no coincidían con Favorites/Downloads, ya reales desde 21b. Con el fix de abajo, ese impacto queda acotado a "Live now" y "Recent activity" únicamente.
**Mitigación:** IMPLEMENTADA (parcial) — `HomePage.qml` ahora llama `favoritesModel.refresh()`/`downloadsModel.refresh()` en `Component.onCompleted` (mismo patrón que Favorites/Downloads/History) y el grid de stats lee `String(favoritesModel.count)`/`String(downloadsModel.count)` en vez de los literales `"12"`/`"3"`. Cubierto por `tests/test_qml_bridge_data.py::test_home_page_shows_real_favorites_and_downloads_counts` (Container real, SQLite real, página real). Pendiente, sin tocar en este fix: "Live now" (sigue literal "2", depende de adapters Twitch/Kick — 21c/21d) y "Recent activity" (sigue literal, necesita decidir su origen real: historial de descargas vs. `notifications`).
**Estado:** PARCIALMENTE MITIGADO — contadores de Favorites/Downloads cerrados; "Live now" y "Recent activity" quedan ABIERTOS bajo esta misma entrada, sin nuevo número de riesgo (mismo hallazgo, alcance reducido).

## RISK-UI-05 — Settings, Scheduled y Playlists no están conectadas a sus casos de uso, ya construidos y testeados (hallazgo FASE 21e)
**Severidad:** MEDIUM
**Evidencia:** `SettingsPage.qml` con `property var sections` literal ("Mock only"); `ScheduledPage.qml`/`PlaylistsPage.qml` son `EmptyState` fijos cuyo botón dice "that's FASE 11/12" (ambas fases ya cerradas). `application/settings.py`, `scheduled_downloads.py` y `playlists.py` existen; `Container` no expone `settings`/`playlists` (RISK-ARCH-04) y no hay bridge.
**Impacto:** la app no permite ni configurar, ni programar, ni crear listas; el texto de los toasts es obsoleto. FASE 21 no las contempla en ninguna sub-fase.
**Mitigación:** las tres se conectan en FASE 22 (Settings 22.9, Scheduled 22.10, Playlists 22.15). En 22.1 solo se corrigió el texto obsoleto: ya no filtran el número de fase ni anuncian éxitos falsos ("Not available yet."), con un test que escanea el QML para que no vuelva.
**Estado:** ABIERTO — la conexión real; el texto engañoso quedó CERRADO en 22.1.

## RISK-PKG-04 — No existe `twick_hub/__main__.py`: `python -m twick_hub` falla (hallazgo FASE 21e)
**Severidad:** LOW
**Evidencia:** FASE_21_INTEGRACION_FINAL.md §21e menciona `python -m twick_hub`. Solo funcionan `python -m twick_hub.main` y el script `twick-hub` (`pyproject.toml`). Se usó `python -m twick_hub.main` en la verificación.
**Mitigación:** IMPLEMENTADA en 22.1: `twick_hub/__main__.py` con guardia `__name__`; verificado arrancando `python -m twick_hub` (log `Twick Hub started.`) y con un test de importación sin efectos.
**Estado:** CERRADO en 22.1.

## RISK-TWITCH-05 — El único login de Twitch soportado es importar la sesión de Firefox; sin Firefox no hay sesión ni playback (hallazgo FASE 21c)
**Severidad:** MEDIUM
**Evidencia:** `FirefoxCookieImporter` es la única implementación de `CookieImporter` (`browser_cookie_import.py`; el TwitchLink original tampoco tenía otra). `TwitchAccountService.connect()` falla con `NoBrowserSessionFoundError` sin un perfil de Firefox con sesión de Twitch. `TwitchPlaybackResolver._variants_for` exige un token de usuario (`NotAuthenticatedError`). El usuario del proyecto no usa Firefox, así que en su máquina no se pudo probar ni `twitch-account` ni `twitch-playback` (FASE 21c).
**Impacto:** un usuario sin Firefox no puede conectar su cuenta de Twitch en Twick Hub y, con el código actual, no puede resolver playback (capturar streams, bajar VODs y clips de Twitch). Kick no se ve afectado (OAuth propio).
**Mitigación (a decidir antes de 21d, no elegida todavía):** (a) instalar Firefox solo para iniciar sesión una vez — sin cambios de código, pero un requisito raro para un usuario; (b) un login dentro de la app con QtWebEngine (ya es dependencia y ya carga twitch.tv para Integrity), que capture la cookie de sesión — código nuevo con su propia verificación en vivo; (c) importar desde navegadores Chromium — descartable a priori: Chrome/Edge cifran las cookies con claves ligadas a la app en versiones recientes, y sería frágil. Hay que confirmar contra la documentación actual antes de apoyarse en (b) o (c).
**Estado:** ABIERTO.


## RISK-RESUME-02 — Cerrar la app a mitad del remux puede dejar un archivo parcial en el destino final (hallazgo FASE 22.1)
**Severidad:** LOW
**Evidencia:** `FFmpegProcessor.remux_concat` borra `output_path` solo cuando ffmpeg termina con código distinto de 0 (`ffmpeg_processor.py`, tras `await self.runner.run(...)`). Si el worker se cancela durante ese `await` (cierre de la app), la excepción sale antes y el archivo a medio escribir queda con el nombre final; la fila de la descarga sigue en `DOWNLOADING` (RISK-ARCH-09, AD-103).
**Impacto:** una carpeta de destino con un vídeo truncado que parece terminado, hasta que la recuperación relance esa descarga (`ffmpeg -y` lo sobrescribe) o el usuario la cancele.
**Mitigación:** decidir en 22.6 (recuperación de descargas interrumpidas) si se reanuda o se reinicia, y borrar el parcial en `CancelledError` dentro de `remux_concat` (3 líneas + test). No se hizo en 22.1 para no decidir aquí la semántica de reanudación.
**Estado:** ABIERTO — resolver en 22.6.


## RISK-ARCH-10 — Ctrl+C en la terminal no cierra la app (hallazgo FASE 22.1)
**Severidad:** LOW (solo desarrollo)
**Evidencia:** arrancando `python -m twick_hub` y enviando SIGINT, el proceso siguió vivo (había que matarlo): mientras Qt está dentro de `app.exec()`, Python no atiende la señal. Comportamiento anterior a 22.1; no es una regresión.
**Impacto:** ninguno para el usuario final (cierra la ventana); molesto en desarrollo. Sin ventana no hay forma limpia de terminarla desde la terminal.
**Mitigación:** si molesta, un `signal.signal(SIGINT, ...)` que llame a `qt_app.quit()` más un `QTimer` que ceda el control a Python cada ~200 ms. No planificado.
**Estado:** ABIERTO, informativo.

