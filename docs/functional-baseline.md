# Twick Hub — Functional Baseline (FASE 0)

Checklist de compatibilidad funcional obligatoria (Master Plan §26 + §31), con estado observado en TwitchLink 3.5.5 y criterio de aceptación para Next. "Estado en 3.5.5" describe el código fuente auditado, no una re-certificación en vivo contra Twitch — eso está fuera del alcance de FASE 0, que no escribe ni ejecuta implementación nueva.

| Función | Estado en 3.5.5 | Módulo(s) origen | Criterio de aceptación en Next |
|---|---|---|---|
| Autenticación Twitch | Implementado (token de sesión de navegador) | `Services/Twitch/Authentication/*` | Login exitoso, token persistido en keyring (no JSON), refresh/expiración manejados. Una sesión ya iniciada en una instalación legacy existente se migra al keyring en vez de perderse (FASE 15) |
| Search (Twitch) | Implementado | `Search/Engine.py`, `QueryParser.py` | Búsqueda unificada Twitch+Kick con etiqueta de plataforma visible (Master Plan §23) |
| Stream downloads | Implementado | `StreamDownloader.py` + `StreamEngine` | Descarga completa de un directo en curso; verificar impacto de SSAI (RISK-TWITCH-02) |
| VOD downloads | Implementado | `VideoDownloader.py` + `VideoEngine` | Paridad con 3.5.5 vía GQL privado (RISK-TWITCH-03 aceptado) |
| Clip downloads | Implementado | `ClipDownloader.py` + `ClipEngine` | Igual que VOD |
| Subscriber-only video downloads | Mecanismo confirmado en FASE 4c: el token de playback trae `authorization.reason="UNAUTHORIZED_ENTITLMENTS"` cuando aplica (AD-21) — `SubscriberOnlyRestrictedError` lo distingue de cualquier otro forbidden. Sin verificar todavía contra una cuenta con suscripción real (Twitch no es alcanzable desde este sandbox). | `infrastructure/twitch/playback/` | Confirmar con una cuenta con suscripción real antes de declarar paridad total — el mecanismo de detección ya está confirmado, falta la prueba en vivo |
| Scheduled downloads | IMPLEMENTADO sobre EventSub/polling (FASE 11) | `ScheduledDownloadManager.py`, `ScheduledDownloadPubSubManager.py` | Reescrito desde cero (Live Monitor de FASE 10 + `ScheduledDownloadScheduler`/`RecordingService`/`AutoDownloadService` de FASE 11); se preserva el comportamiento observable (RECURRING = graba cada directo, como el original), no el mecanismo interno. AT_TIME es una regla nueva sin equivalente en 3.5.5 |
| Thumbnail downloads | Implementado | `Services/Image/*`, `FileEngine` | Con caché LRU y carga async (Master Plan §7) |
| Audio-only downloads | Implementado | `Engine/Config.py` (modo de descarga) | — |
| Video unmuting | Implementado | Downloader/FFmpeg pipeline | Verificar interacción con SSAI (RISK-TWITCH-02) |
| Video cropping | Implementado | Downloader/FFmpeg pipeline | — |
| Custom filename templates | Implementado | `Download/DownloadInfo.py` | Confirmar cobertura exacta de variables de plantilla en FASE 7. Plantillas por tipo de contenido guardadas por un usuario legacy (`Templates.*`) no tienen destino en `Settings` todavía y no se migran (FASE 15, RISK-MIGRATION-03) |
| Channel bookmarks / Favorites | Implementado como "bookmarks"; no equivalente a los nuevos Favorites (Master Plan §21 los redefine con más campos) | — | Nuevo modelo `Favorite` (Domain), no port directo. Bookmarks de una instalación legacy real se migran resolviendo cada login contra la API (FASE 15) — ver AD-86 |
| External playback | Implementado | `Search/ExternalPlaybackGenerator.py` | — |
| Download history | Implementado | `Download/History/*` | Modelo destino: `DownloadRepository` (SQLAlchemy, FASE 8). Historial real de una instalación legacy se migra a esa misma tabla (FASE 15) — `content`/`playback` (objetos GQL completos) no se portan, solo id/título/canal/duración/estado, ver AD-85 |
| Language / time-zone settings | Implementado | `Services/Translator/*`, `AppData/Preferences.py` | Idioma migra a `Settings.language` (FASE 15, id de paquete de traducción legacy ya es un tag BCP-47 como `"en"`/`"ko"`). Huso horario no tiene campo destino todavía y no se migra (RISK-MIGRATION-03) |
| FFmpeg | Implementado, buen diseño (subprocess por lista de args, sin `shell=True`) | `Engine/FFmpeg/FFmpeg.py` | Preservar diseño (Master Plan §18) |
| Auto-download | Implementado (ligado a bookmarks/PubSub) | — | Reescrito como `AutoDownloadRule` (FASE 11) |
| Settings (general) | Implementado | `AppData/Preferences.py` | Reestructurado por dominio (Master Plan §13: General/Downloads/Twitch/Kick/…). Preferencias reales de una instalación legacy (notificaciones, tema, bandeja del sistema, concurrencia, directorio/formato de stream) se migran sobre la fila existente, sin resetear campos que legacy no tiene — ver AD-85 (FASE 15) |

## Alcance de esta tabla
Cubre exactamente lo exigido por Master Plan §26/§31. No cubre comportamiento de detalle (calidad exacta de cada preset, mensajes de error específicos) — eso se define por función en la fase que la implementa, con sus propios tests (Master Plan §33).
