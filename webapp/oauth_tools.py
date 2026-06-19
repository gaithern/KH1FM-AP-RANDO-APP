import base64
import hashlib
import hmac
import json
import time
import urllib.parse

import requests

from envr import (
    DISCORD_CLIENT_ID,
    DISCORD_CLIENT_SECRET,
    DISCORD_OAUTH_REDIRECT_URI,
    OAUTH_TOKEN_SECRET,
)

DISCORD_AUTHORIZE_URL = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
DISCORD_USER_URL = "https://discord.com/api/users/@me"

SESSION_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days
STATE_TTL_SECONDS = 60 * 5  # 5 minutes


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(payload_b64: str) -> str:
    return hmac.new(
        OAUTH_TOKEN_SECRET.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def _make_token(payload: dict) -> str:
    payload_b64 = _b64url_encode(json.dumps(payload).encode("utf-8"))
    signature = _sign(payload_b64)
    return f"{payload_b64}.{signature}"


def _verify_token(token: str) -> dict | None:
    try:
        payload_b64, signature = token.split(".", 1)
    except (ValueError, AttributeError):
        return None
    if not hmac.compare_digest(_sign(payload_b64), signature):
        return None
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, UnicodeDecodeError):
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload


def make_session_token(discord_id, discord_name) -> str:
    return _make_token(
        {
            "discord_id": discord_id,
            "discord_name": discord_name,
            "exp": time.time() + SESSION_TOKEN_TTL_SECONDS,
        }
    )


def verify_session_token(token: str):
    payload = _verify_token(token)
    if payload is None:
        return None, None
    return payload.get("discord_id"), payload.get("discord_name")


def make_state(return_to: str) -> str:
    return _make_token({"return_to": return_to, "exp": time.time() + STATE_TTL_SECONDS})


def verify_state(state: str):
    payload = _verify_token(state)
    if payload is None:
        return None
    return payload.get("return_to")


def build_authorize_url(return_to: str) -> str:
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify",
        "state": make_state(return_to),
        "prompt": "none",
    }
    return f"{DISCORD_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_user(code: str):
    token_response = requests.post(
        DISCORD_TOKEN_URL,
        data={
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": DISCORD_OAUTH_REDIRECT_URI,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token_response.raise_for_status()
    access_token = token_response.json()["access_token"]

    user_response = requests.get(
        DISCORD_USER_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    user_response.raise_for_status()
    user = user_response.json()
    return user["id"], user.get("username")
