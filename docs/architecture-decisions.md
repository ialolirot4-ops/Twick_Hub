# Twick Hub — Architecture Decisions (FASE 0)

**Estado:** Congelado en FASE 0 · **Basado en:** Master Plan v3.0 + auditoría de TwitchLink 3.5.5 (repo original devhotteok/TwitchLink, subido como referencia)

Formato ADR ligero: contexto → decisión → consecuencias. Estas decisiones son vinculantes para las fases siguientes salvo que una fase futura las revise explícitamente y lo documente aquí (Master Plan §32).

## AD-01 — Punto de partida: repo vacío, sin código heredado de Twick Hub
**Contexto:** No existe ningún repositorio parcial de Twick Hub. Solo se dispone del Master Plan v3.0 y de TwitchLink 3.5.5 vanilla como referencia.
**Decisión:** FASE 0 audita exclusivamente TwitchLink 3.5.5 como fuente de comportamiento/UX a preservar. FASE 1 construye el skeleton desde cero.
**Consecuencias:** El "estado real del repositorio actual" que pide el Master Plan §34 es, en este caso, el estado de 3.5.5 — ver `docs/migration-map.md`.

## AD-02 — PySide6 + QML confirmado, sin alternativa QWidgets
**Contexto:** 3.5.5 usa PyQt6 + QtWidgets + 28 archivos `.ui` (Qt Designer). El Master Plan exige evaluar PySide6+QML vs PySide6+QWidgets.
**Decisión:** Se mantiene PySide6 + QML. QWidgets se descarta: no resolvería el problema de mantenibilidad/extensibilidad que motiva el rewrite.
**Consecuencias:** Ninguno de los 28 `.ui` ni de los 49 archivos de `Ui/*.py` de 3.5.5 se reutiliza como implementación (costo alto, ver RISK-UI-01 en risk-register.md) — se reutiliza comportamiento/flujo, no código.

## AD-03 — Eliminar el patrón `App.Instance`
**Contexto:** `Core/App.py` crea `Instance = App(...)` como efecto secundario del *import* del módulo, y cuelga de él ocho servicios más (`NetworkAccessManager`, `TwitchGQL`, `Translator`, `NotificationManager`, `ContentManager`, `TempManager`, `ImageLoader`, `PartnerContentManager`), también instanciados al importar. `App.Instance` se referencia directamente en al menos 14 archivos.
**Decisión:** Confirma Master Plan §5 sin cambios: estos servicios pasan a `bootstrap/container.py`, inyectados por constructor.
**Consecuencias:** Es el hallazgo de mayor impacto de FASE 0 para FASE 1 — el skeleton debe demostrar arranque/cierre limpio sin ningún objeto creado por efecto secundario de import.

**Corolario (FASE 1, verificado empíricamente):** `Application` no crea su propio `QGuiApplication` — lo recibe por constructor. Qt solo permite una instancia de `QGuiApplication` por proceso (confirmado por un `RuntimeError` real de shiboken al correr la suite de tests: dos tests que cada uno creaba la suya chocaban entre sí). `main.py` construye la instancia una sola vez y se la pasa a `Application`; los tests inyectan la instancia de sesión de `pytest-qt` (`qapp`) en vez de crear la suya. Mismo principio que el resto de AD-03 — nada se construye a través de un global, todo se recibe explícitamente — aplicado a un objeto de Qt que además tiene la restricción física de "uno por proceso".

## AD-04 — Twitch: EventSub por WebSocket, con credencial de aplicación separada de la de usuario
**Contexto:** El PubSub heredado de Twitch fue apagado permanentemente el 14 de abril de 2025 — no es una preferencia arquitectónica, es un hecho verificado: `Services/Twitch/PubSub/*` de 3.5.5 ya no puede conectar a Twitch. El presupuesto de coste de EventSub por token de usuario (`max_total_cost=10`, ~1 de coste por suscripción a un canal ajeno) limita a ~3–5 canales monitoreables en tiempo real por token de usuario — insuficiente para una lista de favoritos típica.
**Decisión:** `TwitchEventSubProvider` usará dos credenciales separadas: (1) el token de usuario actual, extraído de sesión de navegador, para GQL privado/Integrity/reproducción/descarga; (2) un client_id/secret propio de Twick Hub (app registrada en Twitch) para EventSub, a validar en FASE 4d si el transporte WebSocket acepta tokens de aplicación o exige Webhooks (que requerirían endpoint público, indeseable en una app de escritorio).
**Consecuencias:** Es el mayor riesgo técnico abierto del proyecto — ver RISK-TWITCH-01 en risk-register.md. Mitigación de respaldo: Helix `Get Streams` en polling de bajo coste para favoritos que excedan presupuesto.
**Corrección (FASE 4d):** La documentación oficial de EventSub confirma que el transporte WebSocket exige un token de **usuario** para crear subscriptions — los tokens de aplicación son el camino de Webhooks (servidor-a-servidor), que este proyecto no tiene ni quiere montar solo para esto (sería el "backend remoto solo por comodidad" que el propio Master Plan prohíbe). Se descarta la idea de una credencial de aplicación separada para EventSub — `TwitchEventSubProvider` usa el mismo token de usuario de FASE 4a. El techo de RISK-TWITCH-01 (~5 canales) es real, no una hipótesis a resolver con ingeniería — ver AD-23.

## AD-05 — Kick: capacidades oficiales primero, VOD/Clips fuera del core
**Contexto:** La API pública oficial de Kick (`api.kick.com/public/v1`, OAuth 2.1+PKCE, activa desde ~mayo 2026) cubre Users, Channels, Chat, Livestreams, Moderation, Rewards, Categories y Events. No se encontró VOD ni Clips en la superficie pública — el acceso conocido (incluida la app Android oficial de Kick) pasa por `api.kick.com/private/v1/...`, no oficial.
**Decisión:** FASE 5 implementa primero Auth/Users/Channels/Streams/Categories sobre la API oficial. VOD/Clips/Download de Kick se implementan como `KickUnofficialAdapter`: aislado, marcado como no oficial en la UI, desactivable.
**Consecuencias:** La paridad funcional completa con Twitch puede no alcanzarse para Kick en FASE 5; se comunica explícitamente en la UI (capacidades ausentes ocultas/deshabilitadas, Master Plan §9).

## AD-06 — Live monitoring de Kick: polling adaptativo oficial, no webhook público
**Contexto:** El mecanismo de eventos en tiempo real documentado de Kick exige una URL de webhook pública configurada en el dashboard de desarrollador — no encaja con una app de escritorio sin backend propio.
**Decisión:** Opción B del Master Plan §13: polling adaptativo oficial sobre `Livestreams` (funciona con token de usuario o de aplicación, sin scope especial, hasta 50 `broadcaster_user_ids` por llamada), no la opción A (webhook + infraestructura pública).
**Consecuencias:** FASE 10 implementa backoff/agrupación de este polling. Si Kick ofrece en el futuro un transporte push sin endpoint público, esta decisión se revisita.

## AD-07 — Credenciales vía OS keyring, confirmado por hallazgo concreto en 3.5.5
**Contexto:** `AppData/Preferences.py` serializa `Account.__save__()` (incluye el `OAuthToken` del usuario) dentro del árbol que `json.dump()` vuelca completo a `settings.json`, sin cifrado visible en `EncoderDecoder.py`. Es un hallazgo verificado en el código, no una suposición.
**Decisión:** Confirma Master Plan §14 sin cambios — tokens vía `keyring`, nunca en `settings`/SQLite.
**Consecuencias:** FASE 15 (Legacy Migration) debe leer el token viejo de `settings.json` una vez para migrarlo al keyring y luego purgarlo del JSON legacy, no solo dejar de escribir ahí en adelante.

## AD-08 — Selenium/Patchright: se mantienen, carga bajo demanda
**Contexto:** Uso confirmado y acotado a `Services/Account/BrowserCookieDetector/*` y `ExternalBrowserDriver.py` — no está esparcido por el resto de la app. Solo existe detector de Firefox; no hay detector de Chrome/Chromium en 3.5.5.
**Decisión:** Se mantienen (Master Plan §28 lo permite si se justifica), pero como dependencia de import perezoso, aislada en Infrastructure, no cargada en el arranque.
**Consecuencias:** Afecta tamaño de paquete — ver RISK-PKG-01. Evaluar en FASE 4a si conviene sumar Chrome/Chromium.

## AD-09 — PartnerContent: pospuesto
**Contexto:** 3.5.5 tiene un sistema de contenido de socio/patrocinado (`Services/PartnerContent/*`) con caché por referencia de widget.
**Decisión:** POSPONER (una de las tres opciones que exige Master Plan §29). Se decide antes de FASE 2 porque afecta si la UI reserva espacio para este contenido.
**Consecuencias:** Ninguna hasta FASE 2.

## AD-10 — Empaquetado inicial: Windows confirmado, macOS por decidir en FASE 19
**Contexto:** `resources/dependencies/` de 3.5.5 solo empaqueta FFmpeg para `windows/` y `macos/` — no hay binario Linux. PyInstaller ya es la herramienta usada.
**Decisión:** Windows x64 es el target confirmado desde FASE 1. Windows+macOS-desde-el-inicio vs. macOS-después queda explícitamente abierto para FASE 19 (Master Plan §30) — FASE 0 no fuerza esa decisión.
**Consecuencias:** Ninguna hasta FASE 19.

## AD-11 — Theme/Navigation/Toast como QML singletons vía `@QmlElement`/`@QmlSingleton` (FASE 2)
**Contexto:** El shell necesita estado compartido con QML (tema activo, página actual, cola de toasts) sin recurrir a un service locator. PySide6 6.x ofrece registro de tipos QML declarativo vía los decoradores `@QmlElement`/`@QmlSingleton` de `PySide6.QtQml` — probado aislado antes de construir el resto del shell encima.
**Decisión:** `presentation/qml_bridge/{theme,navigation,toast}.py` exponen `Theme`, `NavigationController` y `ToastController` así. `bootstrap/application.py` importa `presentation.qml_bridge` antes de cargar cualquier QML — el import ejecuta los decoradores y registra los tipos; sin ese import, `import TwickHub 1.0` fallaría en QML.
**Consecuencias:** Es el único patrón "global" permitido — no es un service locator porque QML lo resuelve por el sistema de tipos de Qt, no por lookup manual de código Python; nada en Domain/Application lo toca (`presentation/qml_bridge` es exclusivamente de la capa Presentation). `ToastController` solo emite la señal `toastRequested`; la lista visible de toasts vive en `ToastHost.qml`, no en Python — es puro estado de presentación transitorio, sin significado de negocio.
**Nota de stubs:** el stub de tipos de PySide6 no modela bien `Property()` en forma funcional ni `qmlTypeId()` con argumentos `str` (ambos funcionan correctamente en runtime, verificado). Los tests que topan con esto llevan `cast()`/`pyright: ignore` puntuales y comentados — ver `tests/test_theme.py` y `tests/test_qml_shell.py`.

## AD-12 — Paleta del shell: identidad propia, ni Twitch ni Kick
**Contexto:** El Master Plan no fija paleta de colores (verificado — no hay ninguna sección al respecto). Twitch (morado `#9147FF`) y Kick (verde `#53FC18`) son ambas plataformas de primera clase (AD-05); usar el color de marca de una como acento del propio shell implicaría favoritismo visual hacia esa plataforma.
**Decisión:** El shell usa una paleta neutra propia (grafito frío en dark, casi-blanco cálido en light) con un acento ámbar (`#E8A33D`) que no es ni Twitch ni Kick. Los colores de marca de cada plataforma aparecen únicamente en `PlatformBadge.qml` — nunca en la chrome de la app (sidebar, header, fondos).
**Consecuencias:** Si una fase futura agrega una tercera plataforma, no requiere retocar la paleta del shell — solo agregar su color de badge correspondiente.

## AD-13 — Entidades de dominio: dataclasses congeladas + `Media` como referencia polimórfica ligera
**Contexto:** FASE 3 exige 14 entidades (Channel, User, Stream, Video, Clip, Media, Download, DownloadJob, DownloadSegment, Favorite, Playlist, ScheduledDownload, Notification, PlatformAccount) más enums/value objects/protocols/use cases, sin PySide6 ni ningún framework.
**Decisión:** Todas las entidades y value objects son `@dataclass(frozen=True, slots=True)` — inmutables, actualizaciones vía `dataclasses.replace()` o un método que devuelve una instancia nueva (p. ej. `Playlist.with_item_added`), nunca mutación in-place. `Media` no es una entidad con historia propia sino un value object polimórfico (`kind`, `ref`, `title`, `channel_ref`, `thumbnail_url`, `duration`) que `Download`, `Favorite`-adyacentes (`PlaylistItem`), y `Notification` usan para apuntar a "contenido" sin importar si es un Stream, Video o Clip. `Download` (registro persistente/UI) se separa de `DownloadJob`+`DownloadSegment` (unidades de ejecución del motor de FASE 7) — un Download puede sobrevivir a varios intentos de Job sin que la UI necesite saberlo.
**Consecuencias:** Favorites/Playlists/Notifications no necesitan tres campos opcionales (`stream_id`, `video_id`, `clip_id`) ni un `Union[Stream, Video, Clip]` — un solo campo `Media` cubre los tres casos. `PlatformRef` (platform + external_id) es la identidad natural para todo lo que viene de una plataforma (Channel, User, Stream, Video, Clip); las entidades puramente locales (Download, Favorite, Playlist, ScheduledDownload, Notification) generan su propio `id` (UUID) porque no existen en ninguna plataforma.

## AD-14 — Protocols de plataforma segregados, no un `PlatformClient` único
**Contexto:** docs/risk-register.md (RISK-TWITCH-03) ya nombraba `VideoProvider`/`ClipProvider` como el límite de aislamiento para la API GQL no oficial de Twitch. docs/kick-audit.md confirmó que la API oficial de Kick no cubre VOD/Clips.
**Decisión:** `domain/protocols.py` define protocols angostos y específicos (`ChannelDirectory`, `LiveStreamProvider`, `VideoProvider`, `ClipProvider`, `PlaybackResolver`, `LiveMonitor`) en vez de una única interfaz "PlatformClient" que fuerce a cada adapter a implementar métodos que no puede soportar. Un adapter de Kick (FASE 5) puede implementar `ChannelDirectory`+`LiveStreamProvider` sin verse obligado a fingir `VideoProvider`/`ClipProvider` mientras Kick no los oficialice.
**Consecuencias:** El código de Application (casos de uso) que dependa de `VideoProvider` simplemente no es aplicable a un platform que no lo implementa — eso se resuelve en FASE 5/6 (capa de plataforma unificada), no en FASE 3. Todos los métodos de protocol son `async def`: ninguna implementación real (HTTP, SQL) puede bloquear el hilo de UI, regla permanente del Master Plan.

## AD-15 — Auth de Twitch implementada: dos credenciales, `/oauth2/validate` en vez de GQL
**Contexto:** FASE 4a implementa lo que AD-04 solo había diseñado. Prohibición explícita del Master Plan §38: "No implementar GraphQL completo todavía" — necesitaba una forma de saber a quién pertenece el token de sesión sin GQL.
**Decisión:** `infrastructure/twitch/account_service.py` usa el endpoint oficial y documentado `GET https://id.twitch.tv/oauth2/validate` (devuelve `login`/`user_id`/`expires_in`) para identificar la cuenta — no toca GQL. `infrastructure/twitch/app_token_provider.py` implementa el flujo separado de AD-04 (client credentials) para el futuro token de aplicación de EventSub, con caché y refresh automático por expiración. `AccountProvider` (nuevo protocol en `domain/protocols.py`, agregado en esta fase) es lo que `TwitchAccountService` implementa — `connect`/`disconnect`/`current_account`.
**Consecuencias:** FASE 4b construye el cliente GQL completo sobre esta base sin tocar la lógica de autenticación ya resuelta aquí.

## AD-16 — Integrity: se captura la cabecera real de Twitch, no se calcula
**Contexto:** Al portar `IntegrityGenerator.py` de 3.5.5 se confirmó que el mecanismo no calcula ni falsea nada — carga la página de cuenta de Twitch en un `QWebEnginePage` oculto, deja correr el JavaScript real y sin modificar de Twitch, e intercepta la petición real que ese JS genera hacia `INTEGRITY_URL`, capturando sus cabeceras para reenviarlas él mismo (con el token del usuario agregado). El cómputo anti-bot ocurre enteramente dentro del código de Twitch, no en este proyecto.
**Decisión:** Se porta el mecanismo tal cual (`infrastructure/twitch/integrity_adapter.py`), adaptado a PySide6 e inyección de dependencias (sin `App.Instance`).
**Verificación honesta:** `QtWebEngineCore` importa y `QWebEngineProfile` se construye en el sandbox de esta fase. Cargar la página real y capturar un token no pudo verificarse acá — ni por red (dominios de Twitch fuera de la lista permitida de este sandbox) ni por Chromium, que rechaza correr su renderer como root sin `--no-sandbox` (error real confirmado al probarlo). Corroborar en una máquina real con sesión de Twitch real antes de que FASE 4d dependa de esto — coincide con lo que RISK-TWITCH-04 ya anticipaba (mantenimiento continuo, no algo que se arregla una vez).

## AD-17 — `CookieImporter` es un protocol de Infrastructure, no de Domain
**Contexto:** `TwitchAccountService` necesita depender de una abstracción para importar cookies del navegador (para poder testear con un fake, y para poder sumar Chrome/Chromium después — AD-08), pero esta capacidad es específica de cómo Twitch obtiene su token de sesión, no algo que Kick o cualquier otra plataforma necesite de la misma forma.
**Decisión:** `CookieImporter` vive en `infrastructure/twitch/browser_cookie_import.py`, no en `domain/protocols.py`. No todo protocol necesita vivir en Domain — solo lo que Application o varias plataformas necesitan cruzar el límite de Domain para usar.
**Consecuencias:** Mantiene `domain/protocols.py` enfocado en lo que de verdad es multiplataforma (AD-14), sin inflarlo con detalles de implementación de un solo adapter.

## AD-18 — Queries GQL portadas literalmente; Integrity solo en las operaciones que de verdad lo piden
**Contexto:** Al auditar `TwitchGQLOperations.py`/`TwitchGQLAPI.py` de 3.5.5 para FASE 4b se confirmó que las operaciones de metadata (GetChannel, GetChannelVideos, GetChannelClips, GetVideo, GetClip) son GraphQL normal — texto de query real, no hashes de persisted query — a diferencia de las tres operaciones de playback (persisted query + Integrity + auth de usuario), que son FASE 4c y no se tocan acá. `useIntegrity` solo es `True` para `GetChannelVideos`/`GetChannelClips`; `GetChannel`/`GetVideo`/`GetClip` no lo necesitan, y ninguna operación de esta fase necesita el token OAuth del usuario.
**Decisión:** `infrastructure/twitch/gql/operations.py` porta las cinco queries de metadata tal cual, con `OPERATIONS_REQUIRING_INTEGRITY` marcando exactamente esas dos. `TwitchGQLClient` depende de un `IntegrityHeaderSource` (protocol angosto, no el `IntegrityAdapter` completo) para poder testear sin QWebEngine.
**Consecuencias:** FASE 4c reutiliza `TwitchGQLClient` sin cambios — solo agrega las operaciones de playback y, ahí sí, el token de usuario.

## AD-19 — Resolución id→login para listar videos/clips; `mappers.py` es el único lugar que ve el schema de Twitch
**Contexto:** `PlatformRef` usa el id numérico de Twitch como identidad canónica (AD-13, porque el login puede cambiar), pero `GetChannelVideos`/`GetChannelClips` solo aceptan `login`, no `id`.
**Decisión:** `TwitchVideoProvider`/`TwitchClipProvider` reciben un `ChannelDirectory` y resuelven id→login antes de listar, en vez de cambiar qué guarda `PlatformRef`. Todo el mapeo de dict de GQL (`displayName`, `lengthSeconds`, nodos anidados) a entidades de Domain vive únicamente en `infrastructure/twitch/gql/mappers.py` — es el límite real de "no mezclar API con Domain" del Master Plan §39: Domain nunca ve una forma de dato de Twitch, ni GQL nunca importa nada de `domain/`.
**Consecuencias:** Un futuro adapter de Kick (FASE 5) puede resolver su propio id→handle de la misma forma si su API lo exige, sin que `PlatformRef` ni ningún caso de uso de Application se enteren de la diferencia.

## AD-20 — Playback separado de metadata y de download; token+manifest, sin tocar bytes de video
**Contexto:** Master Plan §40 exige separar explícitamente "API metadata / Playback / Download". Las 3 operaciones de playback (persisted query, `useIntegrity=True`, `useAuth=True`) eran justo lo que FASE 4b dejó pendiente a propósito.
**Decisión:** `infrastructure/twitch/playback/` es un paquete aparte de `infrastructure/twitch/gql/` (FASE 4b) — comparte `TwitchGQLClient` (extendido con `send_persisted`/`send_persisted_batch`, sin romper `send()` de FASE 4b) pero no toca `channel_directory.py`/`video_provider.py`/`clip_provider.py`. `TwitchPlaybackResolver.resolve()` devuelve una `PlaybackSource` (URL + etiqueta de calidad) — nunca descarga ni escribe un byte; eso sigue siendo FASE 7.
**Consecuencias:** El mismo `TwitchGQLClient` seguirá sirviendo para FASE 4d (EventSub) si hace falta, sin duplicar la lógica de headers/Integrity.

## AD-21 — Subscriber-only confirmado: es el `reason` exacto del propio token de Twitch
**Contexto:** docs/functional-baseline.md dejó pendiente confirmar en FASE 4c cómo se detecta un video solo-para-suscriptores.
**Decisión:** Se confirma el mecanismo exacto (portado de `_validateToken` de 3.5.5): el playback token, decodificado, trae `authorization.forbidden=true` con `authorization.reason="UNAUTHORIZED_ENTITLMENTS"` específicamente para este caso — `SubscriberOnlyRestrictedError` en `playback/errors.py` distingue este reason exacto de cualquier otro `forbidden` (que cae en `PlaybackForbiddenError`, genérico, porque no hay confirmación de qué otros reasons existen — no se inventan significados no verificados).
**Consecuencias:** docs/functional-baseline.md puede marcar esta fila como confirmada — ver ahí.

## AD-22 — SSAI: respuesta parcial, no la pregunta completa de RISK-TWITCH-02
**Contexto:** El campo `hideAds` de `StreamPlaybackAccessToken` en 3.5.5 sí revela cuándo Twitch no muestra anuncios a un viewer específico (Turbo o beneficio de sub ad-free).
**Decisión:** Se porta `stream_hides_ads()` y se registra su resultado, pero no se usa para tomar ninguna decisión todavía (no hay pipeline de descarga real aún — eso es FASE 7). No se declara resuelto RISK-TWITCH-02: este campo solo confirma cuándo un viewer específico NO tiene el problema; no dice nada sobre qué hay en los segmentos para quien sí los recibe.
**Consecuencias:** FASE 7 (Download Engine) es quien realmente necesita decidir qué hacer con `hideAds`/SSAI al procesar segmentos — ver docs/risk-register.md RISK-TWITCH-02, actualizado con esta precisión.

## AD-23 — El techo de EventSub se aplica de verdad, no se documenta y ya
**Contexto:** RISK-TWITCH-01 identificó el techo de ~5 canales (`floor(10/2)`, dos tipos de subscription por canal) desde FASE 0. Implementarlo sin aplicarlo dejaría que el código intente suscribir un sexto canal y falle de forma confusa contra la API real.
**Decisión:** `CapacityGovernor` (`infrastructure/twitch/eventsub/capacity.py`) rechaza explícitamente con `CapacityExceededError` antes de intentar la subscription — nunca deja que Twitch sea quien lo descubra. `TwitchEventSubProvider.subscribe()` libera la reserva si la creación de la subscription falla, para que un fallo no deje presupuesto "fantasma" ocupado.
**Consecuencias:** FASE 10 (Live Monitor) es quien decide qué hacer con favoritos más allá del techo (polling Helix de bajo coste, ya previsto como mitigación) — esta fase solo garantiza que el límite nunca se viola en silencio.

## AD-24 — Bus de eventos interno en Domain, EventSub nunca toca UI
**Contexto:** Master Plan §41 exige "conectar OFFLINE → ONLINE mediante eventos internos" y "no conectar EventSub directamente con UI."
**Decisión:** `domain/events.py` agrega `ChannelWentOnline`/`ChannelWentOffline` + un `EventBus` mínimo (suscribir/publicar, sin frameworks). `TwitchEventSubProvider` publica ahí — no conoce ni le importa quién escucha. Nadie escucha todavía (eso es FASE 9/10/11); esta fase solo construye el bus y publica.
**Consecuencias:** Cuando FASE 10 conecte Favoritos/Notificaciones al bus, no necesita tocar nada de `infrastructure/twitch/eventsub/`.

## AD-25 — `_receive_and_handle_one` como unidad de trabajo testeable, separada del loop infinito
**Contexto:** Un cliente WebSocket real corre en un loop infinito (`run_forever`), difícil de testear de forma determinista sin correr una tarea de fondo real.
**Decisión:** Toda la lógica (recibir, dedupe, despachar por tipo, reconectar ante corte anormal) vive en `_receive_and_handle_one()`, una corrutina que procesa exactamente un mensaje y retorna. `run_forever()` es un `while True` de una línea que la llama. Los tests llaman `_receive_and_handle_one()` directamente con una conexión falsa que entrega mensajes guionados — sin tareas de fondo, sin timing real.
**Consecuencias:** Encontrado real durante la implementación: la primera llamada tras conectar consume el mensaje de bienvenida Y el primer mensaje real en la misma llamada — documentado en los tests, no es un bug.

## AD-26 — OAuth de Kick: listener HTTP local de un solo uso, no esquema de URI personalizado
**Contexto:** Kick usa OAuth 2.1 + PKCE real (a diferencia de Twitch, que no tiene flujo OAuth propio para este proyecto — ver AD-04/AD-15). Una app de escritorio necesita recibir el redirect del navegador de alguna forma.
**Decisión:** `infrastructure/kick/redirect_listener.py` levanta un servidor HTTP local de un solo uso (`http.server` en un hilo, coordinado con asyncio vía `call_soon_threadsafe`) en `localhost` — no un esquema de URI personalizado (`twickhub://...`), que exige registro específico por sistema operativo y no lo pide la documentación de Kick. `RedirectListener` es un protocol angosto para poder testear sin navegador real.
**Consecuencias:** Verificado de punta a punta en esta fase con una petición HTTP real (no mockeada) contra el listener — es el test más directo de todo el proyecto hasta ahora, porque no depende de que Kick sea alcanzable.

## AD-27 — `KickUnofficialAdapter` pospuesto, no implementado en FASE 5
**Contexto:** Master Plan §42: "Solo implementar estas capacidades [VOD/clips/playback/download] si están validadas." docs/kick-audit.md reconfirma con evidencia más fuerte que en FASE 0 que VOD/Clips siguen sin oficializarse.
**Decisión:** No se construye `KickUnofficialAdapter` esta fase. A diferencia de Twitch (donde FASE 4a-4c pudieron portar mecanismos ya probados de TwitchLink 3.5.5), Kick no tiene código de referencia propio en este proyecto — construir un adapter no oficial ahora significaría escribir contra endpoints reverse-engineered de terceros sin poder verificarlos contra una cuenta Kick real, exactamente el tipo de cosa que "no inventar endpoints" busca evitar.
**Consecuencias:** Kick queda con paridad funcional parcial frente a Twitch (sin VOD/Clips) hasta que la API oficial los cubra o una fase futura decida construir el adapter no oficial con la debida cautela (aislado, marcado, desactivable — tal como exige el Master Plan si en algún momento se implementa).

## AD-28 — Mapeo de Usuario de Kick, hecho a propósito de forma defensiva
**Contexto:** A diferencia de Channel/Livestream (confirmados campo por campo contra la documentación oficial de un SDK), no se encontró un ejemplo de respuesta confirmado para `GET /users`.
**Decisión:** `infrastructure/kick/mappers.py::map_user` usa `.get()` con nombres de campo alternativos (`user_id`/`id`, `name`/`username`) en vez de asumir una forma exacta, y el módulo documenta explícitamente esta incertidumbre en vez de ocultarla.
**Consecuencias:** Confirmar contra una respuesta real de `/users` antes de que el flujo de cuenta de Kick se use en producción — señalado aquí y en el propio código, no asumido como resuelto.

## AD-29 — `PlatformRegistry` decide capacidades por presencia, no por flags declarados a mano
**Contexto:** FASE 6 (Master Plan §43) exige `PlatformCapabilities` para que la UI pueda ocultar/deshabilitar funciones no soportadas por plataforma.
**Decisión:** `PlatformCapabilities.from_adapters()` deriva cada bandera (`has_live`, `has_videos`, `has_clips`, `has_playback`, `has_live_monitor`, `has_account`, `can_search_channels`) directamente de si el campo correspondiente de `PlatformAdapters` es `None` o no — nunca una bandera mantenida a mano aparte. Misma filosofía que `domain/protocols.py` y `application/search.py` (FASE 4b/5): la ausencia de un adapter es la única fuente de verdad de "no soportado".
**Consecuencias:** Imposible que `PlatformCapabilities` quede desincronizado de lo que el registry realmente tiene wireado — no hay dos lugares que mantener en sync.

## AD-30 — Dispatch unificado (channels/live/media) vive como métodos de `PlatformRegistry`, no como una `UseCase` por capacidad
**Contexto:** Master Plan §43 pide "unified search; unified channels; unified live; unified media" como comportamientos, no necesariamente como cuatro clases `*UseCase` nuevas (el patrón usado en el resto de `application/` para casos de uso con reglas de negocio propias).
**Decisión:** `get_channel()`, `get_live_stream()`, `resolve_playback()` y `available_qualities()` son métodos async directos de `PlatformRegistry` — cada uno resuelve la plataforma correcta por `ref.platform`/`media.ref.platform` y delega al adapter correspondiente, sin lógica de negocio adicional que justifique una clase `UseCase` separada (que solo envolvería una llamada de una línea). `SearchContentUseCase` es la excepción: ya existía desde FASE 4b con lógica propia (filtro opcional por plataforma, `asyncio.gather`), así que FASE 6 solo le agrega `from_registry()` como constructor alternativo — su constructor `directories=` original queda intacto.
**Consecuencias:** Si una fase futura necesita lógica de negocio real alrededor de channels/live/media (no solo dispatch), esa lógica debe vivir en su propia `UseCase` que dependa de `PlatformRegistry` — no se debe inflar `PlatformRegistry` con reglas que no sean de enrutamiento.

## AD-31 — FASE 6 no conecta `PlatformRegistry` al `Container` ni a la UI real
**Contexto:** `bootstrap/container.py` todavía no wirea ningún adapter concreto de Twitch/Kick (su propio comentario lo señala desde FASE 3 y sigue así en el ZIP recibido para esta fase). Conectar `PlatformRegistry` con instancias reales exige ensamblar keyring, token stores, cliente GQL/HTTP, Integrity, EventSub y OAuth/PKCE de Kick — trabajo sustancial no descrito en el alcance de FASE 6 (§43). Igualmente, `presentation/qml` sigue siendo mock puro por decisión explícita de FASE 2 (Master Plan §36: "No conectar plataformas reales").
**Decisión:** FASE 6 entrega `PlatformRegistry`/`PlatformCapabilities`/dispatch unificado como código de Application puro, testeado con fakes — sin tocar `bootstrap/container.py`, `bootstrap/dependencies.py` ni ningún archivo `.qml`. `PlatformCapabilities.as_dict()` deja un mapeo bool camelCase ya listo para que una fase de wiring de UI lo consuma sin rediseño.
**Decisión (regla de alcance, Master Plan §0.5):** el wireado real al Container y la conexión UI→capabilities no se implementan aquí; quedan registrados en `docs/risk-register.md` (RISK-ARCH-01, RISK-UI-02) en vez de implementarse "por comodidad" dentro de esta fase.
**Consecuencias:** FASE 7 (Download Engine) y las fases de feature real (FASE 9+) son las candidatas naturales para wirear `PlatformRegistry` al `Container` cuando de verdad lo necesiten — no antes.

## AD-32 — `DownloadStatus` corregido retroactivamente a los 8 estados exactos de FASE 7
**Contexto:** `domain/enums.py::DownloadStatus` (creado en FASE 3) tenía 6 estados (`PENDING/DOWNLOADING/PAUSED/COMPLETED/FAILED/CANCELLED`). Master Plan §44 (FASE 7) exige exactamente ocho: `QUEUED/PREPARING/DOWNLOADING/PROCESSING/COMPLETED/FAILED/CANCELLED/PAUSED`. Sin este cambio, `DownloadExecutor` no podría representar sus propios estados de pipeline (`PREPARING` antes de resolver playback, `PROCESSING` durante el remux) usando el enum del dominio.
**Decisión:** Corrección retroactiva (Master Plan §0.13): `PENDING` → `QUEUED`, se agregan `PREPARING` y `PROCESSING`. Blast radius verificado por grep antes del cambio: solo `domain/downloads.py` (valor por defecto) y `tests/application/test_downloads.py` (una aserción) referenciaban `PENDING` — ambos actualizados, regresión completa ejecutada después (296/296 en ese punto).
**Consecuencias:** Cualquier fase futura que serialice `DownloadStatus` a un formato externo (UI, persistencia FASE 8) debe usar los nuevos valores string (`"queued"`, no `"pending"`) — no hay datos persistidos todavía que migrar, así que no aplica una migración de FASE 8.

## AD-33 — Arquitectura de segmentos: total desconocido por defecto, `segments_completed_of()` como respaldo
**Contexto:** Un VOD/clip conoce su lista completa de segmentos tras una sola lectura de playlist; un directo (`stream`) no conoce su total hasta que termina. `DownloadExecutor` no distingue de antemano cuál es cuál sin leer primero.
**Decisión:** `DownloadExecutor` siempre llama `progress.start(download_id, total_segments=None)` — igual para VOD que para directo — así que `ProgressTracker.progress_of()` devuelve `0.0` durante toda la descarga en ambos casos por ahora. `segments_completed_of()` (cuenta cruda, siempre funciona) queda como vía de escape para una fase de UI futura que quiera mostrar "N segmentos descargados" en vez de un porcentaje.
**Consecuencias:** Reportar porcentaje real para VOD (detectando que el primer batch ya trae `is_complete=True` y fijando el total entonces) es una mejora incremental, no una reescritura — queda pendiente, registrada en `docs/risk-register.md`, no implementada aquí para no ampliar el alcance de FASE 7 sin necesidad.

## AD-34 — Cancelación verificada también después del loop de polling, no solo vía excepción
**Contexto:** `SegmentManager` señaliza cancelación lanzando `DownloadCancelledError`, pero `HlsPlaylistReader.poll_until_complete`'s `should_stop` (=`is_cancelled`) puede cortar el loop de polling *sin* que `SegmentManager` llegue a lanzar nada — por ejemplo si la cancelación llega entre un poll y el siguiente, sin ningún segmento en vuelo. Descubierto durante el testing de esta misma fase (`test_cancellation_mid_download_stops_the_pipeline` falló en el primer intento: el download terminaba en `COMPLETED` con contenido parcial).
**Decisión:** `DownloadExecutor.run()` verifica `is_cancelled()` explícitamente otra vez justo después de que el `async for` del polling termina, antes de pasar a `PROCESSING` — sin importar si el loop terminó por agotarse (VOD completo) o por cancelación silenciosa.
**Consecuencias:** Cualquier futura fuente adicional de "corte silencioso" del loop de polling (por ejemplo, un límite de duración máxima) debe pasar por el mismo chequeo explícito post-loop, no asumir que una excepción siempre se propaga.

## AD-35 — Pausa/reanudación: el estado visible lo fija `DownloadService`, no el worker bloqueado
**Contexto:** Master Plan §44 exige el estado `PAUSED` y tests de pausa. El worker que ejecuta un `Download` puede estar bloqueado dentro de `SegmentManager._wait_while_paused` en el momento exacto en que se solicita la pausa — no puede "darse cuenta" y actualizar su propio estado en ese instante.
**Decisión:** `DownloadService.pause()`/`.resume()` actualizan `Download.status` inmediatamente y por su cuenta (independientemente de dónde esté el worker), y además marcan/limpian una bandera en `JobControlStore` que `SegmentManager` sondea cooperativamente. El worker no se cancela ni se vuelve a encolar al pausar: simplemente se queda bloqueado en el mismo punto y continúa exactamente ahí al reanudar — sin necesidad de un mecanismo de reanudación-desde-cero para el caso "misma sesión de la app".
**Consecuencias:** Si la app se reinicia mientras un download está `PAUSED`, el worker en memoria ya no existe — reanudar después de un reinicio requiere invocar `DownloadExecutor.run()` de nuevo desde cero, lo cual funciona para segmentos ya descargados (se saltan, ver `SegmentManager`) pero no puede funcionar para un directo que ya terminó mientras tanto (su URL de reproducción ya no es válida). Registrado como RISK-RESUME-01, no resuelto aquí — no estaba en el alcance de FASE 7 (que no pide recuperación tras caída, eso es más cercano a "safe shutdown" de FASE 8).

## AD-36 — FASE 7 tampoco conecta el motor de descargas al `Container`
**Contexto:** Mismo patrón que AD-31 (FASE 6): `bootstrap/container.py` sigue sin wirear ningún componente real — ahora tampoco `DownloadService`/`DownloadCoordinator`/`DownloadExecutor`. Wirearlos de verdad exige decidir cuántos workers usar, dónde vive `work_dir`, qué cliente HTTP comparte `HlsPlaylistReader`, y de dónde sale un `ffmpeg` real — nada de eso está descrito en el alcance de FASE 7 (§44).
**Decisión:** El motor se entrega como código de Infrastructure puro, testeado con fakes en las fronteras impuras (HTTP, subprocess), sin tocar `bootstrap/container.py` ni `bootstrap/dependencies.py`.
**Consecuencias:** Registrado como RISK-ARCH-03. La fase que primero necesite el motor corriendo de verdad dentro de la app (candidata natural: una fase de feature real, FASE 9+, o una fase de wiring dedicada) decide ahí esas configuraciones — no antes.
