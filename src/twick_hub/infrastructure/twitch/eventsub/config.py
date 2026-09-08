"""EventSub WebSocket configuration and real, documented capacity
numbers.

**Correction to docs/architecture-decisions.md AD-04, made while
implementing this phase:** AD-04 planned a project-owned app access
token for EventSub specifically to get the 10,000-cost budget instead of
the user token's 10. Twitch's EventSub WebSocket transport, per its own
documentation, requires a *user* access token for subscription creation
(app access tokens are the Webhook-transport path, not WebSocket) — this
project has no server to receive webhooks, and getting one just for this
would be exactly the "backend remoto solo por comodidad" the Master Plan
rules out. So this phase uses the same user token FASE 4a already
obtains (WEB_CLIENT_ID + browser session), and RISK-TWITCH-01's capacity
ceiling is real, not a hypothesis to be engineered around — see
capacity.py.
"""

from __future__ import annotations

EVENTSUB_WEBSOCKET_URL = "wss://eventsub.wss.twitch.tv/ws"
EVENTSUB_SUBSCRIPTIONS_URL = "https://api.twitch.tv/helix/eventsub/subscriptions"

STREAM_ONLINE = ("stream.online", "1")
STREAM_OFFLINE = ("stream.offline", "1")

# Per Twitch's own EventSub documentation (confirmed in FASE 0's audit,
# docs/risk-register.md RISK-TWITCH-01):
MAX_TOTAL_COST_USER_TOKEN = 10
MAX_SUBSCRIPTIONS_PER_SOCKET = 300
MAX_SOCKETS_PER_CLIENT_USER_PAIR = 3
COST_PER_SUBSCRIPTION = 1  # for a channel that isn't the token owner's own
SUBSCRIPTION_TYPES_PER_CHANNEL = 2  # stream.online + stream.offline

# A missed keepalive by this much past its stated timeout means the
# connection is dead — reconnect from scratch rather than waiting
# indefinitely for a message that isn't coming.
KEEPALIVE_GRACE_SECONDS = 5
