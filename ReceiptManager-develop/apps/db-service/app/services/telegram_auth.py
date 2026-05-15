import hashlib
import hmac
import json
import os
from urllib.parse import parse_qsl


def validate_telegram_init_data(init_data: str) -> dict | None:
    """Validate Telegram Mini App initData when TELEGRAM_BOT_TOKEN is configured.

    Returns the decoded Telegram user payload, or None when validation is unavailable/failed.
    This is intentionally side-effect free so routes can adopt it gradually without breaking
    local multi-user testing.
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token or not init_data:
        return None

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        return None

    user_raw = pairs.get("user")
    if not user_raw:
        return None
    try:
        return json.loads(user_raw)
    except json.JSONDecodeError:
        return None
