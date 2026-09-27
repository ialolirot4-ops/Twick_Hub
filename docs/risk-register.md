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
**Estado:** Aceptado, sin mitigación estructural posible más allá del aislamiento.

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
**Estado:** Aceptado, es el costo conocido de AD-02.

## RISK-PKG-01 — Selenium/Patchright + PyQt6-WebEngine en tamaño y estabilidad del paquete
**Severidad:** MEDIUM
**Evidencia:** `requirements.txt` de 3.5.5 incluye `PyQt6-WebEngine`, `selenium==4.40.0`, `patchright==1.60.1` — dependencias pesadas para una funcionalidad acotada (importar cookies del navegador).
**Impacto:** Tamaño de instalador (FASE 19) y superficie de fallo (versiones de navegador cambiantes).
**Mitigación:** AD-08 — carga bajo demanda, no en el arranque; evaluar en FASE 4a si `PyQt6-WebEngine` es realmente necesario.
**Estado:** Abierto, no bloqueante para FASE 1-3.

## RISK-PROD-01 — PartnerContent sin decisión final
**Severidad:** LOW · **Estado:** pospuesto (AD-09), decidir antes de FASE 2.

## RISK-PROD-02 — Alcance de macOS/Linux sin decidir
**Severidad:** LOW · **Estado:** explícitamente diferido a FASE 19 por el propio Master Plan §30 — no es una omisión de FASE 0.

## RISK-BUILD-01 — `src/twitchlink_next/` obsoleto se empaqueta junto a `twick_hub` (hallazgo FASE 6)
**Severidad:** MEDIUM
**Evidencia:** El ZIP recibido para FASE 6 contiene `src/twick_hub/` (vigente, importado por todos los tests y por `pyproject.toml`'s `twick-hub = "twick_hub.main:main"`) Y `src/twitchlink_next/` (copia obsoleta previa al rename de FASE 4d, sin `infrastructure/kick/`, sin `infrastructure/twitch/eventsub/`). `[tool.setuptools.packages.find] where = ["src"]` no tiene `include`/`exclude`, así que `pip install -e ".[dev]"` deja **ambos** paquetes importables (`import twitchlink_next` funciona igual que `import twick_hub`) y cualquier build real (FASE 19) empaquetaría el código obsoleto también.
**Impacto:** No rompe tests/ruff/pyright hoy (nadie importa `twitchlink_next`), pero viola Master Plan §0.9 ("No introducir nombres nuevos como 'TwitchLink Next'... salvo razón de compatibilidad legacy explícita y documentada") en el artefacto final, e infla el paquete distribuido con código muerto y potencialmente confuso.
**Mitigación:** Fuera del alcance de FASE 6 (no es un defecto de esta fase ni bloquea su cierre — Master Plan §0.5/§0.13: se registra, no se corrige de paso). Corrección mínima sugerida para quien la aborde: borrar `src/twitchlink_next/` del repositorio (ya no lo usa nada) o, si se prefiere no borrar código sin entender su cobertura (regla permanente #28), añadir `include = ["twick_hub*"]` a `[tool.setuptools.packages.find]` como mitigación inmediata sin tocar el árbol de archivos.
**Estado:** ABIERTO — no bloqueante para FASE 6, debe resolverse antes de FASE 19 (Packaging).

## RISK-BUILD-02 — El historial de `git` está muy por detrás del estado real del código en disco (hallazgo FASE 18)
**Severidad:** LOW — no afecta al código en sí, pero sí a la trazabilidad fase-por-fase.
**Evidencia:** `git log --oneline` en el repositorio recibido para FASE 18 muestra solo 4 commits (`F4c`, `fase 4d`, `Fase5`, `Fase7`) — nada posterior a FASE 7. El código en disco, sin embargo, ya refleja el trabajo hasta FASE 17 completo (persistencia, migración, scheduling, live monitor, updates, etc., todos presentes y con tests en verde). `git status --short` al empezar FASE 18 mostraba decenas de archivos nuevos/modificados sin commitear, acumulados a lo largo de al menos 10 fases.
**Impacto:** Ninguno funcional — `pytest`/`ruff`/`pyright` no dependen de `git`. El impacto real es de trazabilidad: no es posible usar `git diff`/`git log` para aislar qué cambió en una fase concreta frente a las anteriores, que es precisamente para lo que el Master Plan pide "continuidad entre fases vía docs/ actualizados" como red de seguridad independiente de git.
**Mitigación:** Esta fase no reescribe el historial (no es su mandato, y "squashear" 10 fases en un commit retroactivo perdería más trazabilidad de la que arreglaría). En su lugar, el propio commit de cierre de FASE 18 documenta explícitamente en su mensaje que agrupa el catch-up de todo el trabajo previo no commiteado más los cambios reales de esta fase, para que quede constancia del corte. Recomendación para quien retome el proyecto: commitear al final de cada fase a partir de ahora (ideal: un commit por fase, como ya hacían los primeros 4).
**Estado:** ABIERTO, informativo — no bloqueante.

## RISK-ARCH-01 — `PlatformRegistry` sin wirear a `bootstrap/container.py` (FASE 6)
**Severidad:** LOW por ahora, bloqueante para quien primero necesite adapters reales
**Evidencia:** Ver AD-31. `Container` sigue sin ningún campo de plataforma; `PlatformRegistry` (FASE 6) existe y está testeado con fakes, pero nada en `bootstrap/dependencies.py` construye un `PlatformAdapters` real con las clases de `infrastructure/twitch/`/`infrastructure/kick/`.
**Impacto:** Ninguno todavía — FASE 6 no lo necesitaba. Sí bloquea a la primera fase que necesite un `PlatformRegistry` con datos reales corriendo dentro de la app (candidata: FASE 7 Download Engine o una fase de feature real, FASE 9+).
**Mitigación:** Ensamblar `PlatformAdapters` reales en `bootstrap/dependencies.py` cuando esa fase lo requiera — requiere decidir ahí mismo cómo resolver las dependencias de cada adapter concreto (keyring, cliente HTTP, Integrity, etc.), no antes.
**Estado:** ABIERTO, informativo — no bloquea FASE 6 ni FASE 7 en sí (solo bloquea el primer uso real del registry).

## RISK-UI-02 — `PlatformCapabilities` aún no llega a la UI (FASE 6)
**Severidad:** LOW
**Evidencia:** Master Plan §43: "La UI debe ocultar/deshabilitar funciones no soportadas." `presentation/qml` sigue siendo mock puro (decisión explícita de FASE 2, RISK-UI-01) — no hay ningún bridge QML que exponga `PlatformCapabilities.as_dict()` todavía.
**Impacto:** Ninguno hoy — ninguna página real consume datos de plataforma aún. Si una fase de feature real (FASE 9+) conecta datos sin antes conectar capabilities, podría mostrar controles para funciones que la plataforma activa no soporta (p. ej. "Clips" en Kick).
**Mitigación:** `PlatformCapabilities.as_dict()` ya deja el mapeo bool camelCase listo (ver AD-31) para que la primera fase que conecte una página real a datos de plataforma agregue el bridge QML correspondiente antes o junto con esa conexión.
**Estado:** ABIERTO, informativo — recordar explícitamente en el `docs/phase-state.md` de FASE 9+ antes de cerrar cualquiera de esas fases como PASS.

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
**Estado:** ABIERTO, informativo.

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
**Estado:** ABIERTO, informativo. (FASE 10 no necesitó ninguno de los 5 repositorios: el monitor solo lee `favorites`.)

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
**Estado:** ABIERTO.

## RISK-ARCH-07 — El `DirectoryBackupInstaller` es un instalador provisional; el instalador real depende de una decisión de FASE 19 que no existe
**Severidad:** MEDIUM — bloqueante para un release real, no para el desarrollo.
**Evidencia:** AD-78. Master Plan §51 lista "packaging strategy" como prerrequisito de FASE 14; FASE 19 (Packaging) sigue sin empezar. `DirectoryBackupInstaller` asume que la app se distribuye como "un directorio de archivos" reemplazable por un zip — funciona y está probado, pero no es necesariamente cómo la app termine empaquetándose de verdad (un instalador de Windows, un bundle firmado, etc. tendrían mecanismos de reemplazo/rollback completamente distintos, y probablemente necesiten cerrar la app antes de reemplazar sus propios archivos en ejecución — algo que este instalador tampoco maneja).
**Impacto:** Ninguno en desarrollo/pruebas. Un release real con este instalador tal cual podría fallar en Windows si la app está corriendo desde el mismo directorio que se intenta sobreescribir (archivos bloqueados por el propio proceso).
**Mitigación:** Cuando FASE 19 decida el empaquetado real, implementar el `UpdateInstaller` correspondiente — el protocolo ya existe y `UpdateService` no necesita cambios.
**Estado:** ABIERTO — bloqueante para un release real, no para esta fase.

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
