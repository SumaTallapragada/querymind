"""Client IP / User-Agent extraction -- shared by audit logging and rate limiting (Phase 22D),
so proxy-trust policy lives in exactly one place rather than being reimplemented per caller.

`request.client.host` (Starlette's own, read from the raw TCP connection) is the default and the
*only* thing ever trusted unless `Settings.trust_proxy_headers` is explicitly on. Blindly
trusting `X-Forwarded-For` is unsafe whenever the backend is reachable directly (bypassing the
reverse proxy that's supposed to set it): a client could then simply set the header itself and
spoof any IP it likes. Phase 22D's approved design removes the app service's direct host-port
publish specifically so `docker-compose.yml`'s intended path is `browser -> nginx -> app`, making
`trust_proxy_headers=True` meaningful in that deployment -- but this stays a `Settings`-gated
opt-in regardless, never the default, since this module has no way to verify that topology holds
at runtime.
"""

from __future__ import annotations

from starlette.requests import Request

_MAX_USER_AGENT_LENGTH = 300


def get_client_ip(request: Request, *, trust_proxy_headers: bool) -> str | None:
    """The caller's IP, or `None` if it can't be determined at all (never raises)."""
    if trust_proxy_headers:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # The first entry is the original client; every later one is a proxy hop nginx (or
            # another intermediary) appended -- see nginx.conf's own `proxy_set_header
            # X-Forwarded-For $proxy_add_x_forwarded_for`.
            return forwarded_for.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
    return request.client.host if request.client is not None else None


def get_user_agent(request: Request) -> str | None:
    """The caller's `User-Agent`, capped to a safe length -- never unbounded, since it's
    attacker-controlled input that ends up in a log line and a database row.
    """
    user_agent = request.headers.get("User-Agent")
    return user_agent[:_MAX_USER_AGENT_LENGTH] if user_agent else None


async def get_attempted_username(request: Request) -> str | None:
    """Best-effort: `UserLogin`'s body has a `username` field (accepting either a username or an
    email -- see that schema's own docstring; this project's login contract has no separate
    `email` field to prefer instead). Reading `request.json()` here does not conflict with
    FastAPI's own later parsing of the same body into `UserLogin` -- Starlette caches the body
    bytes after the first read. Never raises: an unparsable/already-consumed body just means no
    username-based identity is available for this call, not a broken request.
    """
    try:
        body = await request.json()
    except Exception:
        return None
    username = body.get("username") if isinstance(body, dict) else None
    return username if isinstance(username, str) else None
