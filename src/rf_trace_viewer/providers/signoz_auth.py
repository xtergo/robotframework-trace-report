"""SigNoz authentication — automatic token acquisition and refresh.

Supports three authentication modes:

1. **Static API key** — user provides a long-lived token (SigNoz Cloud).
   No refresh needed.

2. **JWT secret (self-hosted)** — provider registers/discovers a user in
   SigNoz, then self-signs HS256 JWTs using the known secret. Tokens are
   refreshed automatically on 401.

3. **No auth** — endpoint doesn't require authentication (rare).

Uses only stdlib (no third-party JWT libraries).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Default credentials for self-hosted auto-registration
_DEFAULT_EMAIL = "rf-trace-viewer@internal.local"
_DEFAULT_PASSWORD = "RfTraceViewer!AutoAuth2024"
_DEFAULT_ORG = "rf-trace-viewer"
_DEFAULT_NAME = "RF Trace Viewer"

# Token lifetime: 23 hours (refresh before 24h SigNoz default expiry)
_TOKEN_LIFETIME_S = 23 * 3600


class SigNozAuth:
    """Manages SigNoz API authentication tokens.

    Thread-safe for read access to `token` property. Write access
    (refresh) is idempotent — concurrent refreshes produce the same result.
    """

    def __init__(
        self,
        endpoint: str,
        api_key: str = "",
        jwt_secret: str | None = None,
        user_id: str | None = None,
        org_id: str | None = None,
        email: str | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._jwt_secret = jwt_secret
        self._token: str = api_key if api_key and api_key != "none" else ""
        self._user_id: str = user_id or ""
        self._org_id: str = org_id or ""
        self._email: str = email or ""
        self._token_exp: float = 0  # Unix timestamp when token expires

        # Extract user/org IDs and email from existing token if not provided
        if self._token and (not self._user_id or not self._org_id or not self._email):
            claims = _decode_jwt_claims(self._token)
            if claims:
                if not self._user_id:
                    self._user_id = claims.get("id", "")
                if not self._org_id:
                    self._org_id = claims.get("orgId", "")
                if not self._email:
                    self._email = claims.get("email", "")
                self._token_exp = claims.get("exp", 0)

    @property
    def token(self) -> str:
        """Current auth token. May be empty if not yet acquired."""
        return self._token

    @property
    def can_auto_auth(self) -> bool:
        """Whether automatic authentication is possible."""
        return bool(self._jwt_secret)

    def ensure_token(self) -> str:
        """Get a valid token, acquiring one if needed.

        Returns the token string, or empty string if auth is not configured.
        """
        if self._token and not self._is_token_expiring_soon():
            return self._token

        if self._jwt_secret:
            self._acquire_token()

        return self._token

    def refresh_token(self) -> bool:
        """Force token refresh after a 401. Returns True if successful.

        Clears cached user/org IDs so that ``_acquire_token`` goes through
        the full discovery flow (register → login → probe) instead of
        just re-signing with stale IDs.  This handles the case where
        SigNoz was restarted with a fresh database and the old user no
        longer exists.
        """
        if not self._jwt_secret:
            return False
        # Clear stale IDs — they may belong to a previous SigNoz instance
        self._user_id = ""
        self._org_id = ""
        self._email = ""
        return self._acquire_token()

    def get_headers(self) -> dict[str, str]:
        """Return auth headers for a SigNoz API request."""
        token = self.ensure_token()
        if not token:
            return {}
        return {
            "Authorization": f"Bearer {token}",
            "SIGNOZ-API-KEY": token,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _is_token_expiring_soon(self) -> bool:
        """Check if token expires within 5 minutes."""
        if not self._token_exp:
            return False
        return time.time() > (self._token_exp - 300)

    def _acquire_token(self) -> bool:
        """Acquire a fresh token via the most reliable method available.

        Tries in order:
        1. Re-sign with known user/org IDs (fastest, no network)
        2. Register a new user (works on fresh SigNoz instances)
        3. Login via session API (works when user already exists)
        4. Probe endpoints with a self-signed token (legacy fallback)
        """
        # If we already have user/org IDs, just re-sign
        if self._user_id and self._org_id:
            return self._sign_fresh_token()

        # Try to register a new user (works on fresh SigNoz instances)
        if self._try_register():
            return self._sign_fresh_token()

        # Registration failed (user exists / self-reg disabled).
        # Login via the v2 session API to get real IDs.
        if self._try_login():
            return self._sign_fresh_token()

        # Try to discover user/org IDs from the existing token
        if self._token:
            claims = _decode_jwt_claims(self._token)
            if claims and claims.get("id") and claims.get("orgId"):
                self._user_id = claims["id"]
                self._org_id = claims["orgId"]
                if not self._email:
                    self._email = claims.get("email", "")
                return self._sign_fresh_token()

        # Last resort: probe SigNoz API endpoints with a self-signed
        # token containing synthetic IDs.  Works on older SigNoz
        # versions that don't validate user ID existence.
        if self._jwt_secret and self._try_probe_ids():
            return self._sign_fresh_token()

        print("[signoz-auth] Cannot acquire token: no user/org IDs available", file=sys.stderr)
        return False

    def _try_login(self) -> bool:
        """Login via SigNoz v2 session API to discover real user/org IDs.

        Two-step flow (no auth required for either step):
        1. ``GET /api/v2/sessions/context?email=...`` → discover org ID
        2. ``POST /api/v2/sessions/email_password`` → get access token
           with real user/org IDs embedded in the JWT claims.
        """
        email = self._email or _DEFAULT_EMAIL

        # Step 1: Discover org ID via session context (no auth needed)
        org_id = self._org_id
        if not org_id:
            org_id = self._discover_org_id(email)
        if not org_id:
            return False

        # Step 2: Login with email + password + orgId
        url = f"{self._endpoint}/api/v2/sessions/email_password"
        payload = json.dumps(
            {
                "email": email,
                "password": _DEFAULT_PASSWORD,
                "orgId": org_id,
            }
        ).encode()
        req = Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")

        try:
            with urlopen(req, timeout=10) as resp:
                body = resp.read().decode()
                if body.strip().startswith("<!doctype") or body.strip().startswith("<html"):
                    return False
                data = json.loads(body)
                # Response: {"status":"success","data":{"accessToken":"...","refreshToken":"..."}}
                token_data = data.get("data", data)
                access_token = token_data.get("accessToken", "")
                if not access_token:
                    return False

                # Decode the access token to extract real user/org IDs
                claims = _decode_jwt_claims(access_token)
                if not claims:
                    return False

                user_id = claims.get("id", "")
                claimed_org = claims.get("orgId", "")
                claimed_email = claims.get("email", "")

                if user_id and claimed_org:
                    self._user_id = user_id
                    self._org_id = claimed_org
                    self._email = claimed_email or email
                    print(
                        f"[signoz-auth] Logged in via session API: "
                        f"user={self._user_id} org={self._org_id}",
                        file=sys.stderr,
                    )
                    return True
                return False
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"[signoz-auth] Session login failed: {exc}", file=sys.stderr)
            return False

    def _discover_org_id(self, email: str) -> str:
        """Discover org ID via the unauthenticated session context endpoint.

        ``GET /api/v2/sessions/context?email=<email>`` returns:
        ``{"status":"success","data":{"exists":true,"orgs":[{"id":"..."}]}}``
        """
        import urllib.parse

        url = (
            f"{self._endpoint}/api/v2/sessions/context"
            f"?email={urllib.parse.quote(email)}&ref=http://localhost"
        )
        req = Request(url)
        req.add_header("Accept", "application/json")

        try:
            with urlopen(req, timeout=5) as resp:
                body = resp.read().decode()
                if body.strip().startswith("<!doctype") or body.strip().startswith("<html"):
                    return ""
                data = json.loads(body)
                ctx = data.get("data", data)
                orgs = ctx.get("orgs", [])
                if orgs and isinstance(orgs, list):
                    return orgs[0].get("id", "")
                return ""
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError):
            return ""

    def _try_probe_ids(self) -> bool:
        """Probe SigNoz for user/org IDs using a self-signed probe token.

        Signs a temporary JWT with synthetic IDs and queries several
        endpoints.  The most reliable is ``/api/v1/user`` which returns
        ``{"status":"success","data":[{"id":"...","orgId":"...","email":"..."}]}``.
        Falls back to ``/api/v1/org`` and ``/api/v1/orgs`` for older versions.
        """
        import uuid

        probe_user = str(uuid.uuid4())
        probe_org = str(uuid.uuid4())
        now = int(time.time())
        probe_claims = {
            "id": probe_user,
            "email": _DEFAULT_EMAIL,
            "role": "ADMIN",
            "orgId": probe_org,
            "iat": now,
            "exp": now + 300,
        }
        probe_token = _sign_jwt(probe_claims, self._jwt_secret or "")

        # /api/v1/user is the most reliable — it returns real user records
        # even when the JWT contains synthetic IDs (SigNoz only checks
        # the JWT signature, not the user ID in the claims).
        # Try it first, then fall back to org-level endpoints.
        for path in ("/api/v1/user", "/api/v1/org", "/api/v1/orgs", "/api/v1/orgUsers"):
            url = f"{self._endpoint}{path}"
            req = Request(url)
            req.add_header("Authorization", f"Bearer {probe_token}")
            try:
                with urlopen(req, timeout=5) as resp:
                    body = resp.read().decode()
                    if body.strip().startswith("<!doctype") or body.strip().startswith("<html"):
                        continue
                    data = json.loads(body)
                    # Extract org/user IDs from response
                    if isinstance(data, list) and len(data) > 0:
                        item = data[0]
                    elif isinstance(data, dict) and "data" in data:
                        item = data["data"]
                        if isinstance(item, list) and len(item) > 0:
                            item = item[0]
                    elif isinstance(data, dict):
                        item = data
                    else:
                        continue

                    org_id = ""
                    user_id = ""
                    email = ""
                    if isinstance(item, dict):
                        org_id = item.get("orgId", "") or item.get("id", "")
                        user_id = item.get("userId", "") or item.get("id", "")
                        email = item.get("email", "")

                    if org_id and not self._org_id:
                        self._org_id = org_id
                    if user_id and not self._user_id:
                        self._user_id = user_id
                    if email and not self._email:
                        self._email = email

                    if self._user_id and self._org_id:
                        print(
                            f"[signoz-auth] Discovered IDs via {path}: "
                            f"user={self._user_id} org={self._org_id}",
                            file=sys.stderr,
                        )
                        return True
            except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError):
                continue

        return False

    def _try_register(self) -> bool:
        """Try to register a service user in SigNoz.

        Returns True if registration succeeded and user/org IDs were captured.
        On "self-registration disabled" or "user exists", returns False.
        """
        url = f"{self._endpoint}/api/v1/register"
        payload = json.dumps(
            {
                "email": _DEFAULT_EMAIL,
                "name": _DEFAULT_NAME,
                "orgName": _DEFAULT_ORG,
                "password": _DEFAULT_PASSWORD,
            }
        ).encode()

        req = Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")

        try:
            with urlopen(req, timeout=10) as resp:
                body = resp.read().decode()
                # Skip HTML responses (SPA catch-all)
                if body.strip().startswith("<!doctype") or body.strip().startswith("<html"):
                    return False
                data = json.loads(body)
                # Registration returns user info with id and orgId
                self._user_id = data.get("id", "") or data.get("userId", "")
                self._org_id = data.get("orgId", "")
                if self._user_id and self._org_id:
                    self._email = _DEFAULT_EMAIL
                    print(
                        f"[signoz-auth] Registered service user: {self._user_id}", file=sys.stderr
                    )
                    return True
                # Some versions return nested data
                user_data = data.get("data", {})
                if isinstance(user_data, dict):
                    self._user_id = user_data.get("id", "") or user_data.get("userId", "")
                    self._org_id = user_data.get("orgId", "")
                if self._user_id and self._org_id:
                    self._email = _DEFAULT_EMAIL
                    print(
                        f"[signoz-auth] Registered service user: {self._user_id}", file=sys.stderr
                    )
                    return True
                return False
        except HTTPError as e:
            body = ""
            try:
                body = e.read().decode()
            except Exception:
                pass
            if e.code == 400:
                # "self-registration is disabled" or "user already exists"
                # Both are expected — not an error
                pass
            else:
                print(
                    f"[signoz-auth] Registration failed ({e.code}): {body[:200]}", file=sys.stderr
                )
            return False
        except (URLError, OSError, ValueError) as exc:
            print(f"[signoz-auth] Registration request failed: {exc}", file=sys.stderr)
            return False

    def _sign_fresh_token(self) -> bool:
        """Sign a fresh JWT with current user/org IDs."""
        if not self._jwt_secret or not self._user_id or not self._org_id:
            return False

        now = int(time.time())
        email = self._email or _DEFAULT_EMAIL
        claims = {
            "id": self._user_id,
            "email": email,
            "role": "ADMIN",
            "orgId": self._org_id,
            "iat": now,
            "exp": now + _TOKEN_LIFETIME_S,
        }
        self._token = _sign_jwt(claims, self._jwt_secret)
        self._token_exp = claims["exp"]
        exp_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self._token_exp))
        print(f"[signoz-auth] Token signed, expires {exp_str}", file=sys.stderr)
        return True


# ------------------------------------------------------------------
# JWT helpers (stdlib only, no third-party dependencies)
# ------------------------------------------------------------------


def _b64url_encode(data: bytes) -> str:
    """Base64url-encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """Base64url-decode with padding restoration."""
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)


def _decode_jwt_claims(token: str) -> dict | None:
    """Decode JWT payload claims without signature verification."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        return json.loads(_b64url_decode(parts[1]))
    except (ValueError, json.JSONDecodeError):
        return None


def _sign_jwt(claims: dict, secret: str) -> str:
    """Create an HS256-signed JWT from claims and secret."""
    # Use compact JSON (no spaces) — standard JWT encoding that SigNoz expects.
    header = _b64url_encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode()
    )
    payload = _b64url_encode(json.dumps(claims, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url_encode(sig)}"
