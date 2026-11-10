"""Telegram Bot API: send and edit HTML messages."""

import httpx

MAX_LEN = 4096


class TelegramError(Exception):
    pass


class TelegramChannel:
    def __init__(self, token: str, chat_id: str, client: httpx.AsyncClient):
        self._base = f"https://api.telegram.org/bot{token}"
        self._chat_id = chat_id
        self._http = client

    async def _call(self, method: str, payload: dict) -> dict:
        try:
            resp = await self._http.post(f"{self._base}/{method}", json=payload, timeout=20)
        except httpx.HTTPError as e:
            raise TelegramError(f"{method}: {e}") from e
        if resp.status_code != 200:
            raise TelegramError(f"{method}: HTTP {resp.status_code}")
        body = resp.json()
        if not body.get("ok"):
            raise TelegramError(f"{method}: {body.get('description')}")
        return body.get("result") or {}

    async def send(self, html: str) -> int:
        result = await self._call(
            "sendMessage",
            {
                "chat_id": self._chat_id,
                "text": html[:MAX_LEN],
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )
        return int(result["message_id"])

    async def edit(self, message_id: int, html: str) -> None:
        await self._call(
            "editMessageText",
            {
                "chat_id": self._chat_id,
                "message_id": message_id,
                "text": html[:MAX_LEN],
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )
