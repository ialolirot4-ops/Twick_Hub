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
