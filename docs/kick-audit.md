# Twick Hub — Kick Audit (FASE 0)

Estado de la API de Kick verificado en esta sesión mediante búsqueda actual. No exhaustivo — Kick puede cambiar su API pública sin aviso, como cualquier plataforma en expansión activa. Reconfirmar contra `docs.kick.com` antes de implementar FASE 5.

## Resumen
Kick tiene una API pública oficial (`dev.kick.com` / `docs.kick.com`, base `api.kick.com/public/v1`) activa desde aproximadamente mayo de 2026, con OAuth 2.1 + PKCE. Cubre una porción real y utilizable de lo que necesita Twick Hub, pero **no incluye VOD ni Clips** en su superficie pública.

## Clasificación por capacidad

| Capacidad | Clasificación | Evidencia | Nota |
|---|---|---|---|
| OAuth 2.1 + PKCE | OFICIAL | Documentado en `docs.kick.com`; confirmado por múltiples SDKs de terceros (Rust, Kotlin, C#, Python) que lo implementan contra el endpoint oficial | — |
| Users | OFICIAL | Endpoint `users` documentado y usado por los SDKs | — |
| Channels | OFICIAL | Endpoint `channels`, incluye lectura y actualización | — |
| Livestreams (consulta) | OFICIAL | `GET livestreams`; funciona con token de usuario o de aplicación, sin scope especial; filtra por `broadcaster_user_ids` (máx. 50), `category_id`, `language` | Apto para polling — ver AD-06 |
| Categories | OFICIAL | Documentado y presente en los SDKs | — |
| Chat (lectura/escritura) | OFICIAL | Envío de mensajes documentado | — |
| Moderation | OFICIAL | Documentado | No prioritario para Twick Hub |
| Rewards | OFICIAL | Documentado | No prioritario para Twick Hub |
| Events / Webhooks (tiempo real) | OFICIAL, con matiz arquitectónico | Requiere URL de webhook pública configurada en el dashboard de desarrollador de Kick | Ver AD-06 — no encaja de forma natural con una app de escritorio sin backend propio |
| VOD | NO OFICIAL / INCIERTO | No aparece en la lista de módulos de ningún SDK que implementa `api.kick.com/public/v1`; el acceso conocido (incluida la app Android oficial de Kick) pasa por `api.kick.com/private/v1/...` | No inventar un endpoint público — confirmar antes de FASE 5 |
| Clips | NO OFICIAL / INCIERTO | Mismo hallazgo que VOD: acceso confirmado solo vía `api.kick.com/private/v1/clips` | — |
| Playback / descarga de VOD-clips | NO OFICIAL | Depende de los dos puntos anteriores | Aislar en `KickUnofficialAdapter` — ver AD-05 |
| Rate limits oficiales | INCIERTO | No se confirmó una cifra concreta en esta sesión | Verificar en `docs.kick.com` antes de fijar `RetryPolicy` para Kick en FASE 5 |

## Riesgo operativo adicional (no solo cobertura)
Se encontró un reporte de bug abierto (7 de agosto de 2026, repo oficial `KickEngineering/KickDevDocs`) de una aplicación de desarrollador que no podía completar la autorización OAuth (`invalid_scope` incluso solicitando solo `user:read`) ni activar webhooks pese a tenerlos habilitados en el dashboard. Esto sugiere que, además del hueco de cobertura (VOD/Clips), la superficie oficial puede tener inestabilidad operativa activa a la fecha de esta auditoría. No es bloqueante, pero FASE 5 debe presupuestar tiempo para trabajar alrededor de bugs de plataforma, no solo de huecos de documentación.

## Decisión de FASE 0 (Master Plan §13)
Ver AD-06 en `architecture-decisions.md`: polling adaptativo oficial sobre `Livestreams`, no webhook público, para el monitor de directos de Kick.

## Tareas para FASE 5
1. Confirmar contra `docs.kick.com` (no contra este documento, que puede quedar desactualizado) si VOD/Clips se oficializaron.
2. Si siguen sin oficializar: implementar `KickUnofficialAdapter` aislado, marcado, desactivable, documentando qué endpoint privado se usa y su riesgo de romperse sin aviso.
3. Confirmar límites de rate limit oficiales antes de fijar `RetryPolicy`.
4. Diseñar el polling adaptativo de `Livestreams` con backoff, agrupando favoritos en lotes de hasta 50 `broadcaster_user_ids` por llamada.

## Actualización FASE 5 (implementación real)

### OAuth confirmado con precisión
Endpoints exactos, confirmados contra `KickEngineering/KickDevDocs` (getting-started/generating-tokens-oauth2-flow.md), no contra terceros:
- `GET https://id.kick.com/oauth/authorize` — `client_id`, `response_type=code`, `redirect_uri`, `state`, `scope`, `code_challenge`, `code_challenge_method=S256`.
- `POST https://id.kick.com/oauth/token` (`application/x-www-form-urlencoded`) — mismo endpoint para intercambio de código, refresh, y client_credentials, distinguidos por `grant_type`.
- `POST https://id.kick.com/oauth/revoke?token=...&token_hint_type=...` — parámetros por query string, no por body.
- `POST https://id.kick.com/oauth/token/introspect` — `Authorization: Bearer <token>`, sin body.
- **Hallazgo real:** el intercambio de código exige `client_secret` además de `code_verifier` — inusual para un flujo PKCE (cuyo punto suele ser evitar el secreto en clientes públicos/nativos), pero es lo que la propia documentación de Kick pide, no una elección de este proyecto.
- Kick recomienda `redirect_uri` con host `localhost` (no `127.0.0.1`) por un bug conocido de su propio frontend.

### VOD/Clips: re-confirmado NO oficial (evidencia más fuerte que en FASE 0)
Un issue de la comunidad en el propio repo `KickDevDocs` pide explícitamente soporte para relacionar VOD con su stream en vivo "cuando se agregue el endpoint `https://api.kick.com/public/v1/videos`" — confirma que ese endpoint no existe todavía de forma oficial. Ningún SDK oficial-compatible (Rust, Kotlin, Go) expone un módulo de Videos o Clips. Todo acceso a VOD/clips encontrado (incluyendo un wrapper que se anuncia explícitamente como basado en "las mismas APIs internas que usa la app Android oficial de Kick") pasa por endpoints privados (`kick.com/api/v1/...`, distinto de `api.kick.com/public/v1`), basados en cookies de sesión, no en OAuth.

### Eventos disponibles (documentados, no suscritos)
Seis tipos de evento oficiales confirmados de forma cruzada (SDKs Go y C#): `chat.message.sent`, `channel.followed`, `channel.subscription.renewal`, `channel.subscription.gifts`, `channel.subscription.new`, `livestream.status.updated`. Gestión vía `POST/GET /events/subscriptions`.

### Nuevo hallazgo: los webhooks de Kick tienen problemas de entrega reales, no solo el problema arquitectónico ya conocido
Dos issues activos en `KickDevDocs` (#300, #367) reportan que la entrega de webhooks es "prácticamente inexistente" incluso con URL pública verificada, webhooks activados, y subscriptions activas. Esto refuerza — con evidencia operativa, no solo arquitectónica — la decisión de AD-06 de usar polling adaptativo en vez de webhooks para el monitor de directos.

### Decisión de FASE 5: no se implementa `KickUnofficialAdapter` todavía
Dado que VOD/Clips siguen sin validarse como oficiales (Master Plan §42: "Solo implementar estas capacidades si están validadas"), y dado que este proyecto no tiene forma de probar un endpoint no oficial contra una cuenta real de Kick, se pospone la implementación de un adapter no oficial en vez de construir algo no verificable. Ver AD-27.

## Tareas para FASE 5 — estado
1. ~~Confirmar si VOD/Clips se oficializaron~~ — Hecho, re-confirmado que no.
2. `KickUnofficialAdapter` — pospuesto (AD-27), no implementado esta fase.
3. Rate limits oficiales — seguimos sin una cifra confirmada; `RetryPolicy` de Kick queda pendiente para cuando exista lógica de reintento real (fuera del alcance de FASE 5).
4. Polling adaptativo de `Livestreams` con backoff — sigue siendo tarea de FASE 10 (Live Monitor), no de FASE 5.
