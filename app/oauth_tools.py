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

SECONDS_PER_MINUTE = 60
SECONDS_PER_DAY = 24 * 60 * 60
SESSION_TOKEN_LIFETIME_SECONDS = 7 * SECONDS_PER_DAY
STATE_LIFETIME_SECONDS = 5 * SECONDS_PER_MINUTE


def encode_base64_url(data: bytes) -> str:
    encoded = base64.urlsafe_b64encode(data)
    encoded_without_padding = encoded.rstrip(b"=")
    return encoded_without_padding.decode("ascii")


def decode_base64_url(text: str) -> bytes:
    leftover_characters = len(text) % 4
    padding = ""
    if leftover_characters != 0:
        padding = "=" * (4 - leftover_characters)
    return base64.urlsafe_b64decode(text + padding)


def sign(encoded_payload: str) -> str:
    secret_bytes = OAUTH_TOKEN_SECRET.encode("utf-8")
    payload_bytes = encoded_payload.encode("ascii")
    signature = hmac.new(secret_bytes, payload_bytes, hashlib.sha256)
    return signature.hexdigest()


def make_token(payload: dict) -> str:
    payload_json = json.dumps(payload)
    encoded_payload = encode_base64_url(payload_json.encode("utf-8"))
    signature = sign(encoded_payload)
    return f"{encoded_payload}.{signature}"


def read_token(token: str) -> dict | None:
    if not isinstance(token, str):
        return None
    if "." not in token:
        return None

    encoded_payload, signature = token.split(".", 1)
    expected_signature = sign(encoded_payload)
    if not hmac.compare_digest(expected_signature, signature):
        return None

    try:
        payload = json.loads(decode_base64_url(encoded_payload))
    except (ValueError, UnicodeDecodeError):
        return None

    expiry_time = payload.get("exp", 0)
    if expiry_time < time.time():
        return None
    return payload


def make_session_token(discord_id, discord_name) -> str:
    payload = {
        "discord_id": discord_id,
        "discord_name": discord_name,
        "exp": time.time() + SESSION_TOKEN_LIFETIME_SECONDS,
    }
    return make_token(payload)


def verify_session_token(token: str):
    payload = read_token(token)
    if payload is None:
        return None, None
    return payload.get("discord_id"), payload.get("discord_name")


def make_state(return_to: str) -> str:
    payload = {
        "return_to": return_to,
        "exp": time.time() + STATE_LIFETIME_SECONDS,
    }
    return make_token(payload)


def verify_state(state: str):
    payload = read_token(state)
    if payload is None:
        return None
    return payload.get("return_to")


def build_authorize_url(return_to: str) -> str:
    parameters = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify",
        "state": make_state(return_to),
        "prompt": "none",
    }
    query_string = urllib.parse.urlencode(parameters)
    return f"{DISCORD_AUTHORIZE_URL}?{query_string}"


def exchange_code_for_user(code: str):
    token_request_data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_OAUTH_REDIRECT_URI,
    }
    token_response = requests.post(
        DISCORD_TOKEN_URL,
        data=token_request_data,
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
