import json
import os
from typing import Optional

from dotenv import load_dotenv


load_dotenv()


class Config:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    user_tokens_file: str = os.getenv("USER_TOKENS_FILE", "api_tokens.json")
    skip_verify: str = bool(os.getenv("SKIP_VERIFY", False))
    web_server_host: str = os.getenv("WEB_SERVER_HOST", "0.0.0.0")
    web_server_port: int = os.getenv("WEB_SERVER_PORT", 8080)
    webhooks_api_key: str = os.getenv("WEBHOOK_API_KEY")

    merchant_api_url_start: str = os.getenv("MERCHANT_API_URL_START", "http://127.0.0.1:8000/zenithion/api/v1/")

    try:
        with open(user_tokens_file, "r", encoding="utf-8") as f:
            _raw = json.load(f)
    except Exception:
        _raw = {}

    api_tokens: dict[str, list[str]] = {
        token: [str(x) for x in user_ids]
        for token, user_ids in (_raw.items() if isinstance(_raw, dict) else [])
        if isinstance(token, str) and isinstance(user_ids, list)
    }

    @classmethod
    def get_api_token(cls, user_id: Optional[str]) -> Optional[str]:
        if not user_id:
            return None

        for token, user_ids in cls.api_tokens.items():
            if user_id in user_ids:
                return token

        return None


config = Config
