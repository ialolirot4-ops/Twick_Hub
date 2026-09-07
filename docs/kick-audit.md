# TwitchLink Next — Kick Audit (FASE 0)

Estado de la API de Kick verificado en esta sesión mediante búsqueda actual. No exhaustivo — Kick puede cambiar su API pública sin aviso, como cualquier plataforma en expansión activa. Reconfirmar contra `docs.kick.com` antes de implementar FASE 5.

## Resumen
Kick tiene una API pública oficial (`dev.kick.com` / `docs.kick.com`, base `api.kick.com/public/v1`) activa desde aproximadamente mayo de 2026, con OAuth 2.1 + PKCE. Cubre una porción real y utilizable de lo que necesita TwitchLink Next, pero **no incluye VOD ni Clips** en su superficie pública.

## Clasificación por capacidad

| Capacidad | Clasificación | Evidencia | Nota |
|---|---|---|---|
| OAuth 2.1 + PKCE | OFICIAL | Documentado en `docs.kick.com`; confirmado por múltiples SDKs de terceros (Rust, Kotlin, C#, Python) que lo implementan contra el endpoint oficial | — |
| Users | OFICIAL | Endpoint `users` documentado y usado por los SDKs | — |
| Channels | OFICIAL | Endpoint `channels`, incluye lectura y actualización | — |
| Livestreams (consulta) | OFICIAL | `GET livestreams`; funciona con token de usuario o de aplicación, sin scope especial; filtra por `broadcaster_user_ids` (máx. 50), `category_id`, `language` | Apto para polling — ver AD-06 |
| Categories | OFICIAL | Documentado y presente en los SDKs | — |
| Chat (lectura/escritura) | OFICIAL | Envío de mensajes documentado | — |
| Moderation | OFICIAL | Documentado | No prioritario para TwitchLink Next |
| Rewards | OFICIAL | Documentado | No prioritario para TwitchLink Next |
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
