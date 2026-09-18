# Twick Hub — Risk Register (FASE 0)

Severidad: CRITICAL / HIGH / MEDIUM / LOW.

## RISK-TWITCH-01 — Presupuesto de coste de EventSub limita favoritos monitoreables en tiempo real
**Severidad:** HIGH (bajada de CRITICAL — ver Estado)
**Evidencia:** `max_total_cost=10` por token de usuario; suscribirse a un canal ajeno cuesta 1 por tipo de suscripción → con 2 tipos por canal (`stream.online`, `stream.offline`), el techo real confirmado es de exactamente 5 canales monitoreados en tiempo real por token de usuario. FASE 4d confirmó (corrección a AD-04) que el transporte WebSocket exige token de usuario — los tokens de aplicación son el camino de Webhooks, no aplican acá.
**Impacto:** Sin mitigación, Twick Hub tiene un límite de 5 favoritos con notificación en tiempo real vía EventSub — muy por debajo de lo que un usuario espera hoy.
**Mitigación implementada:** `CapacityGovernor` (AD-23) aplica el límite explícitamente — nunca se excede en silencio. Respaldo pendiente de implementar (FASE 10): Helix `Get Streams` en polling de bajo coste (no consume presupuesto EventSub) para favoritos que excedan el presupuesto disponible.
**Estado:** El límite en sí está CONFIRMADO y APLICADO (ya no es una hipótesis a investigar). Sigue ABIERTO lo que le corresponde a FASE 10: decidir y construir qué pasa con los favoritos que exceden las 5 plazas.

## RISK-TWITCH-02 — Server-Side Ad Insertion (SSAI) puede afectar la limpieza de las descargas
**Severidad:** HIGH
**Evidencia:** Fuentes de 2026 confirman que Twitch inserta anuncios directamente en el mismo stream de video, no desde una fuente separada bloqueable como antes. FASE 4c portó `hideAds` (campo real del token de playback de 3.5.5): revela cuándo un viewer específico no recibe anuncios en absoluto (Turbo, o suscripción con beneficio ad-free) — respuesta parcial, verificada, no la pregunta completa: no dice qué hay en los segmentos para un viewer sin ninguno de los dos.
**Impacto:** Si los anuncios quedan incrustados en los segmentos HLS descargados, las grabaciones podrían contener anuncios que antes se evitaban a nivel de manifest/segmento — afecta "Stream downloads" y "Video unmuting", ambas de compatibilidad obligatoria.
**Mitigación propuesta:** No se pudo verificar empíricamente contra un stream real ni en FASE 4c ni antes — Twitch no es alcanzable desde el sandbox de este proyecto. FASE 7 (Download Engine) es quien procesa segmentos de verdad y debe hacer esa verificación antes de declarar paridad de "Stream downloads" — con una cuenta real, decidir qué hacer según `hideAds`.
**Estado:** ABIERTO — parcialmente informado (AD-22), no resuelto. Pasa a ser bloqueante para FASE 7, no para FASE 4c (que solo resuelve URLs, no descarga bytes).

## RISK-SEC-01 — Tokens OAuth en JSON plano (confirmado en 3.5.5)
**Severidad:** HIGH en 3.5.5 / mitigado en Next si AD-07 se implementa correctamente
**Evidencia:** `AppData/Preferences.py` serializa `Account.__save__()` (incluye `OAuthToken`) dentro del árbol que `json.dump()` vuelca completo a `settings.json`, sin cifrado visible en `EncoderDecoder.py`.
**Mitigación:** AD-07 (keyring). FASE 15 debe migrar y purgar el valor legacy, no solo dejar de escribirlo desde ese punto en adelante.
**Estado:** Decisión tomada; pendiente de implementación en FASE 4a y migración en FASE 15.

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
**Mitigación:** Cuando aplique, refactorizar `EnqueueDownloadUseCase` para aceptar un `PlatformRegistry` en vez de un `PlaybackResolver` — cambio de constructor, no cosmético, pendiente de ese momento.
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
