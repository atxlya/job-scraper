"""Telegram Bot API: send and edit HTML messages, read button presses."""

import asyncio

import httpx

MAX_LEN = 4096

# Rows of (label, callback data). Telegram allows at most 64 bytes of data per button.
Buttons = list[list[tuple[str, str]]]


class TelegramError(Exception):
    pass


def _markup(buttons: Buttons) -> dict:
    return {
        "inline_keyboard": [
            [{"text": label, "callback_data": data} for label, data in row] for row in buttons
        ]
    }


class TelegramChannel:
    def __init__(self, token: str, chat_id: str, client: httpx.AsyncClient):
        self._base = f"https://api.telegram.org/bot{token}"
        self.chat_id = chat_id
        self._http = client
        # Held while an alert is re-drawn from the database and edited, so of two edits
        # (eligibility result, button press) the later one always carries both changes.
        self.message_lock = asyncio.Lock()

    async def _call(self, method: str, payload: dict, http_wait_s: float = 20) -> dict | list:
        try:
            resp = await self._http.post(
                f"{self._base}/{method}", json=payload, timeout=http_wait_s
            )
        except httpx.HTTPError as e:
            raise TelegramError(f"{method}: {e}") from e
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code != 200 or not body.get("ok"):
            detail = body.get("description") or f"HTTP {resp.status_code}"
            raise TelegramError(f"{method}: {detail}")
        return body.get("result") or {}

    async def send(self, html: str, buttons: Buttons | None = None) -> int:
        payload = {
            "chat_id": self.chat_id,
            "text": html[:MAX_LEN],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if buttons:
            payload["reply_markup"] = _markup(buttons)
        result = await self._call("sendMessage", payload)
        return int(result["message_id"])

    async def edit(self, message_id: int, html: str, buttons: Buttons | None = None) -> None:
        """Replaces the text, and the buttons. Without `buttons` the message loses them."""
        payload = {
            "chat_id": self.chat_id,
            "message_id": message_id,
            "text": html[:MAX_LEN],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if buttons:
            payload["reply_markup"] = _markup(buttons)
        try:
            await self._call("editMessageText", payload)
        except TelegramError as e:
            if "message is not modified" not in str(e):
                raise  # an identical edit is Telegram saying "already like that"

    async def get_updates(self, offset: int | None, hold_s: int) -> list[dict]:
        """Long-polls for button presses: Telegram holds the request up to `hold_s` seconds
        until one arrives."""
        payload: dict = {"timeout": hold_s, "allowed_updates": ["callback_query"]}
        if offset is not None:
            payload["offset"] = offset
        result = await self._call("getUpdates", payload, http_wait_s=hold_s + 15)
        return list(result) if isinstance(result, list) else []

    async def answer_callback(self, callback_id: str, text: str) -> None:
        """The small notice Telegram shows after a button press (and stops its spinner)."""
        await self._call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})
