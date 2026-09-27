# Twick Hub — Migration Map (FASE 0)

Mapeo de TwitchLink 3.5.5 (fuente, 209 archivos `.py`) hacia Twick Hub. La clasificación se refiere al **estado en 3.5.5** — no existe código de Next aún (ver AD-01 en `architecture-decisions.md`). La columna "Destino" indica el tratamiento planeado, no una tarea completada.

## Leyenda
- **IMPLEMENTADO** — funciona en 3.5.5 tal como está
- **PARCIAL** — funciona con huecos conocidos
- **INCORRECTO** — bug confirmado o comportamiento roto
- **RIESGO** — funciona pero con fragilidad o deuda significativa
- **PENDIENTE** — no existe en 3.5.5, hay que construirlo
- **INNECESARIO** — no debe portarse a Next

## Core / Bootstrap
| Componente 3.5.5 | Clasificación | Destino en Next | Nota |
|---|---|---|---|
| `Core/App.py` (`App.Instance` + 8 servicios colgados) | RIESGO | `bootstrap/{application,container,dependencies}.py` | Ver AD-03. Reescritura completa, no port |
| `TwitchLink.py` (entry point) | IMPLEMENTADO | `main.py` / `bootstrap/application.py` | Patrón simple (`start()` + exit codes RESTART/UNEXPECTED_ERROR_RESTART) — comportamiento a preservar, código a reescribir |
| `Core/Launcher.py` (`SingleApplicationLauncher`) | IMPLEMENTADO | Infrastructure/OS | Mecanismo de instancia única — preservar comportamiento |
| `Core/GlobalExceptions.py` | IMPLEMENTADO | Infrastructure | Preservar: handler de excepciones no capturadas |
| `Core/Updater.py` | PARCIAL | FASE 14 (`UpdateChecker/Service/Downloader/Installer`) | Auditar en detalle en FASE 14, no en FASE 0 |
| `Core/Qt/*` (wrappers QtCore/QtNetwork/QtWidgets, incl. `SafeNetworkReply.py`) | IMPLEMENTADO | Infrastructure (equivalentes PySide6) | `SafeNetworkReply` es la clase señalada en un hallazgo de carrera de datos ya documentado por separado sobre este mismo linaje de código — revisar su reemplazo con cuidado en FASE 7 |
| 46 usos de `from X import *` en el proyecto | INCORRECTO | — | Prohibido explícitamente por Master Plan §6; cero tolerancia en Next |
| `AppData/Preferences.py`, `AppData/EncoderDecoder.py` | RIESGO (persiste el token OAuth en texto plano — ver RISK-SEC-01) | `Settings` (FASE 13) + `LegacyMigrationService` (FASE 15) | Formato JSON con tags propios (`"str:"`, `"obj:<módulo>:<Clase>"`, etc.), auditado y decodificado íntegro en FASE 15 sin depender de PyQt6 ni de los módulos legacy (`infrastructure/migration/legacy_codec.py`) — ver AD-82 |

## Twitch
| Componente 3.5.5 | Clasificación | Destino en Next | Nota |
|---|---|---|---|
| `Services/Twitch/PubSub/*` | INNECESARIO (inoperante) | — | PubSub de Twitch fue apagado el 14 abr 2025; este código ya no puede conectar a Twitch |
| `Services/Twitch/GQL/*` (`TwitchGQLAPI`, Models, Operations) | RIESGO | `Infrastructure/Twitch/GraphQL*` | API privada no documentada — funcional hoy, sin garantía contractual. Única vía conocida para VOD/clips/metadata; se aísla detrás de `VideoProvider`/`ClipProvider` |
| `Services/Twitch/Authentication/Integrity/*` | RIESGO | `Infrastructure/Twitch/Integrity*` | Anti-bot en endurecimiento activo (confirmado en esta auditoría) — mantenimiento continuo esperado |
| `Services/Twitch/Authentication/OAuth/OAuthToken.py` | IMPLEMENTADO | `Infrastructure/Twitch/Auth` | El problema no era este modelo sino dónde se persiste (ver AD-07, FASE 4a). FASE 15 migra el valor real de una instalación legacy existente al credential store — ver AD-83, RISK-SEC-01 |
| `Services/Twitch/Playback/*` | IMPLEMENTADO | `Infrastructure/Twitch/Playback*` (FASE 4c) | Verificar impacto de Server-Side Ad Insertion (activo en 2026) en la limpieza de las descargas — ver RISK-TWITCH-02 |
| EventSub (no existe en 3.5.5) | IMPLEMENTADO (FASE 4d) + integrado al Live Monitor (FASE 10) | `TwitchEventSubProvider` + `HybridLiveMonitor` | Ver AD-04/AD-23/AD-51 — techo de 5 canales aplicado; el resto cae a Helix por lotes. Validación con cuenta real: PENDING |

## Kick
| Componente 3.5.5 | Clasificación | Destino en Next | Nota |
|---|---|---|---|
| — (no existe soporte Kick en 3.5.5) | PENDIENTE | `Infrastructure/Kick/*` (FASE 5) | Ver `docs/kick-audit.md` para el desglose oficial/no oficial |

## Download Engine
| Componente 3.5.5 | Clasificación | Destino en Next | Nota |
|---|---|---|---|
| `Download/GlobalDownloadManager.py` | IMPLEMENTADO | `DownloadQueue` + `DownloadCoordinator` | Cola global — comportamiento a preservar |
| `Download/DownloadManager.py`, `DownloadInfo.py` | IMPLEMENTADO | `DownloadJob` | — |
| `Downloader/Core/Base*Downloader.py` → `Stream/Video/ClipDownloader.py` | IMPLEMENTADO | `DownloadExecutor` + adapters por tipo de contenido | Jerarquía limpia, vale la pena preservar el diseño (no el código) |
| `Downloader/Core/Engine/Playlist/PlaylistEngine.py`, `SegmentDownloader.py`, `MutableSegmentDownloader.py` | RIESGO | `SegmentManager` (HLS) | Este archivo ya recibió al menos un fix de detección de cambio de códec/mapa en el linaje del fork; revisar ese comportamiento al reescribir, no asumir que el diseño original lo cubre bien |
| `Downloader/Core/Engine/FFmpeg/FFmpeg.py` | IMPLEMENTADO | `MediaProcessor/FFmpegProcessor` | Buen diseño confirmado: subprocess con lista de argumentos, sin `shell=True` — Master Plan §18 pide preservarlo explícitamente |
| `Downloader/Core/Engine/File/File*.py` | IMPLEMENTADO | `FileEngine` (thumbnails, descargas simples) | — |
| `Download/History/*` | IMPLEMENTADO | `DownloadRepository` (SQLAlchemy) | Migrado en FASE 15 (`legacy_transform.download_from_history_entry`) directo a la tabla `downloads` existente (FASE 8) — no se creó una tabla `download_history` separada, ver RISK-DATA-02 actualizado. `content`/`playback` (objetos GQL completos) no se portan, solo id/título/canal/duración — ver AD-85 |
| `Download/History/DownloadOptionHistory.py` | IMPLEMENTADO | `Settings.default_directory`/`default_format` (FASE 13) | Solo `StreamHistory` se usa como fuente en FASE 15 — Video/Clip/Thumbnail/ScheduledDownload con directorio/formato propio no tienen destino individual, ver AD-85 |
| `Download/ScheduledDownloadPreset.py` (bookmarks vía `General._bookmarks`, no en este archivo) | IMPLEMENTADO | `Favorite`/`ScheduledDownload` (FASE 9/11) | FASE 15 resuelve login → `PlatformRef` vía `ChannelDirectory.find_channel()` antes de migrar — requiere red; ver AD-86, RISK-MIGRATION-04 |
| `Download/ScheduledDownloadManager.py`, `ScheduledDownloadPubSubManager.py` | IMPLEMENTADO (FASE 11) | `ScheduledDownloadScheduler` + `RecordingService` + `AutoDownloadService` (application/scheduling) | Reescrito sobre EventSub/polling (Live Monitor, FASE 10); RECURRING replica el comportamiento del manager original (verificado contra su código fuente); AT_TIME es nuevo (Master Plan §20). Wireo a Container: PENDING (RISK-ARCH-05) |

## Search / Account / Image / PartnerContent
| Componente 3.5.5 | Clasificación | Destino en Next | Nota |
|---|---|---|---|
| `Search/Engine.py`, `QueryParser.py`, `SearchMode.py` | IMPLEMENTADO | `SearchProvider` unificado (FASE 6) | Parser de URLs a extender para Kick (Master Plan §23) |
| `Services/Account/BrowserCookieDetector/*`, `ExternalBrowserDriver.py` | RIESGO | `Infrastructure/Account/BrowserImport` | Ver AD-08. Solo Firefox soportado hoy |
| `Services/Image/Loader.py`, `Presets.py`, `UrlFormatter.py` | PARCIAL | `Infrastructure/Image` (caché LRU, carga async) | Auditar contra el problema de carrera de miniaturas ya documentado por separado sobre este linaje antes de fijar el diseño de caché (Master Plan §7 lo exige igualmente) |
| `Services/PartnerContent/*` | RIESGO | Ver AD-09 (pospuesto) | — |
| `Services/Playlist/*`, `Theme/*`, `Translator/*`, `Utils/*`, `Temp/*`, `Logging/*` | IMPLEMENTADO | Infrastructure equivalentes | Sin hallazgos que bloqueen — auditoría de detalle en la fase que corresponda |

## UI
| Componente 3.5.5 | Clasificación | Destino en Next | Nota |
|---|---|---|---|
| `Ui/*.py` (49 archivos) + `resources/ui/*.ui` (28 archivos, Qt Designer) | INNECESARIO como implementación | QML (FASE 2) | Ver AD-02. Se reutiliza comportamiento/flujo, no código ni `.ui` |

---
**Nota de alcance:** esta tabla cubre los subsistemas con impacto arquitectónico, no enumera los 209 archivos uno por uno — el detalle exhaustivo de cada función se audita en la fase que la implementa, con su propio gate (Master Plan §33).
