"""
school/middleware.py

AuditLogMiddleware
──────────────────
Hooks into Django's request/response cycle and writes one AuditLog row for
every API call. Runs after the response is fully formed so it never blocks
the view layer. The DB write is synchronous — it reuses the request thread's
already-open connection, costing ~2 ms rather than the 30–80 ms a new-thread
connection handshake would require.

Rules
-----
• Skips OPTIONS pre-flight, static files, media files, and /admin/.
• Reads the request body before the view consumes it (stored on the request
  object so the view can still access request.data normally via DRF).
• Sanitises sensitive keys (password, token, refresh, secret …) to "***".
• Captures the real client IP from X-Forwarded-For when present.
• Derives a human-readable `action` (login.success, create, delete …) from
  the URL path + HTTP method + response status code.
• For every 4xx / 5xx response, reads the response body and stores the full
  error detail in `error_detail` so you know exactly what went wrong, not
  just that it went wrong.
• On error the middleware silently swallows any exception — audit logging
  must never break a live request.
"""

import json
import time

# ── Constants ─────────────────────────────────────────────────────────────────

# Keys whose values are replaced with "***" before storage
_SENSITIVE_KEYS = frozenset({
    "password", "token", "refresh", "access", "secret",
    "authorization", "api_key", "apikey", "auth",
})

# Path prefixes that are never logged
_SKIP_PREFIXES = (
    "/media/",
    "/static/",
    "/admin/",
    "/api/schema",
    "/api/docs",
    "/api/redoc",
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sanitize(data):
    """Recursively replace sensitive field values with '***'."""
    if isinstance(data, dict):
        return {
            k: "***" if k.lower() in _SENSITIVE_KEYS else _sanitize(v)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_sanitize(item) for item in data]
    return data


def _get_client_ip(request):
    """Return the real client IP, honouring X-Forwarded-For from a proxy."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        # The first address in the chain is the original client
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def _derive_action(method: str, path: str, status_code: int) -> str:
    """
    Map (method, path, status_code) → one of the AuditLog.ACTION_CHOICES values.

    Priority: named endpoints first, then generic HTTP verb mapping.
    """
    p = path.lower()

    # Named endpoints
    if "login" in p:
        return "login.success" if status_code < 400 else "login.failed"
    if "logout" in p:
        return "logout"
    if "register" in p:
        return "register"
    if p.rstrip("/") in ("/api", "/api/", "") or "health" in p:
        return "health_check"
    if "bulk" in p:
        return "bulk"

    # Server errors
    if status_code >= 500:
        return "error"

    # Generic CRUD
    verb_map = {
        "GET":    "read",
        "POST":   "create",
        "PUT":    "update",
        "PATCH":  "update",
        "DELETE": "delete",
    }
    return verb_map.get(method.upper(), "action")


def _extract_error_detail(response) -> str:
    """
    For 4xx / 5xx responses, parse the response body and return a clean,
    human-readable string describing what went wrong.

    Examples of what gets stored
    ----------------------------
    400  {"email": ["This field is required."]}
         → "email: This field is required."

    400  {"amount": ["Payment amount must match invoice balance."]}
         → "amount: Payment amount must match invoice balance."

    403  {"error": "Only admins can delete students."}
         → "Only admins can delete students."

    401  {"detail": "Given token not valid for any token type"}
         → "Given token not valid for any token type"

    500  (Django HTML traceback or empty body)
         → "Internal server error (no detail)"

    Returns an empty string for 2xx / 3xx — nothing went wrong.
    """
    if response.status_code < 400:
        return ""

    # ── Try to read the response body ─────────────────────────────────────
    # StreamingHttpResponse has no .content attribute; guard against that.
    try:
        raw = response.content  # bytes — already rendered at this point
    except Exception:
        return "Could not read response body."

    if not raw:
        return "Empty error response."

    # ── Try JSON first (DRF always returns JSON) ───────────────────────────
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Non-JSON (e.g. Django's HTML 500 page in DEBUG mode)
        text = raw.decode("utf-8", errors="replace").strip()
        # Trim to something readable — full HTML tracebacks are huge
        return text[:300] if text else "Non-JSON error response."

    if not isinstance(data, dict):
        return str(data)[:500]

    # ── Flatten common DRF error shapes into a readable string ────────────
    lines = []

    # Shape 1 — {"detail": "..."} — DRF permission / auth errors
    if "detail" in data:
        lines.append(str(data["detail"]))

    # Shape 2 — {"error": "..."} — our own views return this
    elif "error" in data:
        lines.append(str(data["error"]))

    # Shape 3 — {"field": ["msg1", "msg2"], ...} — DRF validation errors
    else:
        for field, messages in data.items():
            if isinstance(messages, list):
                lines.append(f"{field}: {'; '.join(str(m) for m in messages)}")
            elif isinstance(messages, dict):
                # Nested serialiser errors — flatten one level deep
                for sub_field, sub_msgs in messages.items():
                    lines.append(f"{field}.{sub_field}: {'; '.join(str(m) for m in sub_msgs)}")
            else:
                lines.append(f"{field}: {messages}")

    return " | ".join(lines)[:1000] if lines else str(data)[:1000]

def _extract_resource(path: str):
    """
    Parse the URL path into (resource_type, resource_id).

    /api/students/          → ("students", "")
    /api/students/abc-123/  → ("students", "abc-123")
    /api/invoices/42/pay/   → ("invoices", "42")
    """
    parts = [p for p in path.strip("/").split("/") if p]
    # Drop the "api" prefix if present
    if parts and parts[0] == "api":
        parts = parts[1:]
    if not parts:
        return "", ""
    resource    = parts[0]                          # e.g. "students"
    resource_id = parts[1] if len(parts) > 1 else ""  # e.g. "abc-123" or ""
    return resource, resource_id


# ── Middleware ────────────────────────────────────────────────────────────────

class AuditLogMiddleware:
    """
    Standard new-style Django middleware (not MiddlewareMixin).

    Place this *after* AuthenticationMiddleware in MIDDLEWARE so that
    request.user is already populated when we capture it.

    The audit INSERT runs synchronously on the request thread and reuses its
    pooled DB connection.  Do NOT revert to a background thread — see the
    inline comment above AuditLog.objects.create() for the full explanation.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # ── Skip irrelevant paths ──────────────────────────────────────────
        if any(request.path.startswith(prefix) for prefix in _SKIP_PREFIXES):
            return self.get_response(request)

        # Skip CORS pre-flight — no user action, no useful data
        if request.method == "OPTIONS":
            return self.get_response(request)

        # ── Read & stash the body BEFORE the view consumes it ─────────────
        # DRF reads request.body internally; we must not re-read a consumed
        # stream, so we capture it here while it is still fresh.
        try:
            raw_body = request.body  # bytes; safe to read here
            body_data = json.loads(raw_body) if raw_body else {}
        except Exception:
            body_data = {}
        request._audit_body = _sanitize(body_data)

        # ── Start timer ───────────────────────────────────────────────────
        start = time.monotonic()

        # ── Hand off to the view ──────────────────────────────────────────
        response = self.get_response(request)

        # ── Collect everything we need for the log row ────────────────────
        elapsed_ms = int((time.monotonic() - start) * 1000)

        user     = getattr(request, "user", None)
        user_obj = user if (user and user.is_authenticated) else None

        resource_type, resource_id = _extract_resource(request.path)
        action = _derive_action(request.method, request.path, response.status_code)

        log_kwargs = {
            "user":             user_obj,
            "user_email":       user_obj.email           if user_obj else "",
            "user_role":        user_obj.role            if user_obj else "",
            "ip_address":       _get_client_ip(request),
            "user_agent":       request.META.get("HTTP_USER_AGENT", "")[:500],
            "method":           request.method,
            "path":             request.path[:500],
            "query_params":     dict(request.GET),
            "request_body":     getattr(request, "_audit_body", {}),
            "response_status":  response.status_code,
            "response_time_ms": elapsed_ms,
            "resource_type":    resource_type,
            "resource_id":      str(resource_id),
            "action":           action,
            # The actual error message — only populated for 4xx / 5xx.
            # This is the answer to "what went wrong?".
            "error_detail":     _extract_error_detail(response),
        }

        # ── Write synchronously on the request thread's existing connection ──
        #
        # WHY NOT A BACKGROUND THREAD (the original approach was wrong)
        # ──────────────────────────────────────────────────────────────
        # The previous code spawned a new daemon thread for every request.
        # Django's database layer does not share connections across threads —
        # each thread must open its own connection to the database server.
        # A TCP + TLS handshake to PostgreSQL costs ~30–80 ms.  Under any
        # moderate load (e.g. 20 concurrent users) you therefore had 20+
        # threads all fighting to open fresh DB connections simultaneously,
        # rapidly exhausting the connection pool and causing every subsequent
        # request to hang waiting for a free slot — a classic "connection storm".
        #
        # The INSERT itself takes < 2 ms and reuses the connection that the
        # request thread already holds open (Django keeps one connection per
        # thread alive for the lifetime of the process via its connection pool).
        # Writing synchronously here costs ~2 ms in the rarest case; the thread
        # approach cost 30–80 ms per request even before the INSERT ran, plus
        # pool exhaustion under load.
        #
        # The only downside of synchronous writing is that a DB hiccup on the
        # audit INSERT could delay the response.  The try/except below guarantees
        # that any such failure is swallowed silently — the caller never sees it.
        try:
            from school.models import AuditLog
            AuditLog.objects.create(**log_kwargs)
        except Exception:
            pass  # audit logging MUST NOT surface errors to the caller

        return response