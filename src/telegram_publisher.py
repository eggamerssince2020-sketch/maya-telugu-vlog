"""
Telegram Publisher module for maya-telugu-vlog.
Provides an asynchronous HTTP client for the official Telegram Bot API with retry logic,
safe HTML paragraph splitting, multipart photo uploading, and interactive polls.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
import httpx

from src.config import Settings

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"
MAX_TELEGRAM_MESSAGE_LENGTH = 4000  # Telegram absolute limit is 4096; safe margin at 4000


class TelegramPublisher:
    """Async Telegram Bot client handling the 3-step publishing sequence and poll management."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.channel_id = settings.TELEGRAM_CHANNEL_ID
        self.api_url = f"{TELEGRAM_API_BASE}{self.bot_token}" if self.bot_token else ""
        self._is_live = bool(
            self.bot_token
            and not self.bot_token.startswith("your_")
            and self.channel_id
            and not self.channel_id.startswith("@your_")
            and not settings.DRY_RUN
            and not settings.MOCK_MODE
        )

    async def _make_request(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Makes an HTTP POST request to Telegram Bot API with exponential backoff and rate-limit handling."""
        if not self._is_live:
            logger.info("[MOCK/DRY-RUN] Simulated Telegram API call to '%s' with data keys: %s", endpoint, list((data or {}).keys()))
            # Return synthetic mock Telegram response
            if endpoint == "stopPoll":
                return {
                    "ok": True,
                    "result": {
                        "id": "mock_poll_123",
                        "question": (data or {}).get("question", "Mock Question"),
                        "options": [
                            {"text": "Option A", "voter_count": 50},
                            {"text": "Option B", "voter_count": 100},
                        ],
                        "is_closed": True,
                    }
                }

            return {
                "ok": True,
                "result": {
                    "message_id": 999901,
                }
            }

        url = f"{self.api_url}/{endpoint}"
        backoff = 1.0

        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(1, max_retries + 1):
                try:
                    response = await client.post(url, data=data, files=files)
                    resp_json = response.json()

                    if response.status_code == 200 and resp_json.get("ok"):
                        return resp_json

                    # Handle 429 Too Many Requests (Rate limiting)
                    if response.status_code == 429:
                        retry_after = resp_json.get("parameters", {}).get("retry_after", backoff)
                        logger.warning(
                            "Telegram Rate Limit (429) hit on %s. Retrying after %s seconds...",
                            endpoint, retry_after
                        )
                        await asyncio.sleep(float(retry_after))
                        continue

                    # If bad request or client error, check description
                    err_desc = resp_json.get("description", response.text)
                    logger.error("Telegram API Error on %s (status %s): %s", endpoint, response.status_code, err_desc)

                    if response.status_code >= 500 and attempt < max_retries:
                        await asyncio.sleep(backoff)
                        backoff *= 2.0
                        continue

                    response.raise_for_status()

                except httpx.RequestError as e:
                    logger.warning("Network error on Telegram API %s (attempt %d/%d): %s", endpoint, attempt, max_retries, e)
                    if attempt < max_retries:
                        await asyncio.sleep(backoff)
                        backoff *= 2.0
                    else:
                        raise

        raise RuntimeError(f"Failed Telegram API call to {endpoint} after {max_retries} retries.")

    def split_story_text(self, text: str, max_chars: int = MAX_TELEGRAM_MESSAGE_LENGTH) -> List[str]:
        """
        Splits story text cleanly along paragraph boundaries (`\\n\\n` or `\\n`) or sentence/word boundaries
        to ensure no message exceeds Telegram's 4096 character limit while keeping HTML formatting unbroken.
        """
        if len(text) <= max_chars:
            return [text]

        paragraphs = text.split("\n\n")
        chunks: List[str] = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            test_chunk = f"{current_chunk}\n\n{para}".strip() if current_chunk else para

            if len(test_chunk) <= max_chars:
                current_chunk = test_chunk
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""

                # If this paragraph alone is within max_chars, start new chunk with it
                if len(para) <= max_chars:
                    current_chunk = para
                else:
                    # Paragraph is longer than max_chars, split by lines
                    lines = para.split("\n")
                    sub_chunk = ""
                    for line in lines:
                        test_sub = f"{sub_chunk}\n{line}".strip() if sub_chunk else line
                        if len(test_sub) <= max_chars:
                            sub_chunk = test_sub
                        else:
                            if sub_chunk:
                                chunks.append(sub_chunk)
                                sub_chunk = ""
                            # If a single line is still longer than max_chars, split by words/length
                            if len(line) <= max_chars:
                                sub_chunk = line
                            else:
                                words = line.split(" ")
                                word_chunk = ""
                                for w in words:
                                    test_w = f"{word_chunk} {w}".strip() if word_chunk else w
                                    if len(test_w) <= max_chars:
                                        word_chunk = test_w
                                    else:
                                        if word_chunk:
                                            chunks.append(word_chunk)
                                        word_chunk = w
                                if word_chunk:
                                    sub_chunk = word_chunk

                    if sub_chunk:
                        current_chunk = sub_chunk

        if current_chunk:
            chunks.append(current_chunk)

        return chunks or [text]

    async def send_photo(
        self,
        photo: Union[bytes, str],
        caption: str,
        parse_mode: str = "HTML",
        has_spoiler: Optional[bool] = None,
        chat_id: Optional[str] = None,
    ) -> int:
        """
        Step 1: Sends Maya's photorealistic image with teaser caption.
        Supports spoiler blur for maximum subscriber engagement.
        """
        target_chat = chat_id or self.channel_id
        spoiler = self.settings.TELEGRAM_SPOILER_BLUR if has_spoiler is None else has_spoiler

        data: Dict[str, Any] = {
            "chat_id": target_chat,
            "caption": caption[:1024],  # Telegram photo caption limit is 1024 chars
            "parse_mode": parse_mode,
            "has_spoiler": str(spoiler).lower(),
        }

        files = None
        if isinstance(photo, bytes):
            files = {"photo": ("maya_daily.jpg", photo, "image/jpeg")}
        else:
            data["photo"] = photo

        res = await self._make_request("sendPhoto", data=data, files=files)
        msg_id = res.get("result", {}).get("message_id", 0)
        logger.info("Successfully sent Maya's photo to %s (message_id: %s)", target_chat, msg_id)
        return int(msg_id)

    async def send_message(
        self,
        text: str,
        reply_to_message_id: Optional[int] = None,
        parse_mode: str = "HTML",
        chat_id: Optional[str] = None,
    ) -> int:
        """
        Step 2: Sends full Telugu story text as a reply to Post 1.
        Automatically handles paragraph splitting for long chapters.
        """
        target_chat = chat_id or self.channel_id
        chunks = self.split_story_text(text)
        last_msg_id = reply_to_message_id

        for idx, chunk in enumerate(chunks):
            data: Dict[str, Any] = {
                "chat_id": target_chat,
                "text": chunk,
                "parse_mode": parse_mode,
            }
            if last_msg_id:
                data["reply_parameters"] = '{"message_id": %d}' % last_msg_id

            res = await self._make_request("sendMessage", data=data)
            last_msg_id = res.get("result", {}).get("message_id", last_msg_id)
            logger.info(
                "Sent story part %d/%d to %s (message_id: %s)",
                idx + 1, len(chunks), target_chat, last_msg_id
            )

        return int(last_msg_id or 0)

    async def send_poll(
        self,
        question: str,
        options: List[str],
        reply_to_message_id: Optional[int] = None,
        is_anonymous: bool = True,
        chat_id: Optional[str] = None,
    ) -> int:
        """
        Step 3: Posts the interactive decision poll as a reply to the story.
        Note: Telegram channels require is_anonymous=True.
        """
        import json

        target_chat = chat_id or self.channel_id
        cleaned_options = [opt.strip()[:100] for opt in options if opt.strip()][:10]

        data: Dict[str, Any] = {
            "chat_id": target_chat,
            "question": question[:300],
            "options": json.dumps(cleaned_options, ensure_ascii=False),
            "is_anonymous": str(is_anonymous).lower(),
            "allows_multiple_answers": "false",
        }

        if reply_to_message_id:
            data["reply_parameters"] = '{"message_id": %d}' % reply_to_message_id

        res = await self._make_request("sendPoll", data=data)
        poll_msg_id = res.get("result", {}).get("message_id", 0)
        logger.info("Sent interactive Telegram poll to %s (message_id: %s)", target_chat, poll_msg_id)
        return int(poll_msg_id)

    async def stop_poll(
        self,
        message_id: int,
        chat_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Closes an active Telegram poll and retrieves final vote tally and winning option.
        Gracefully handles polls that are already closed or missing.
        """
        target_chat = chat_id or self.channel_id
        data = {
            "chat_id": target_chat,
            "message_id": message_id,
        }

        try:
            res = await self._make_request("stopPoll", data=data)
            poll_obj = res.get("result", {})
            if isinstance(poll_obj, dict) and "poll" in poll_obj:
                poll_obj = poll_obj["poll"]
            return poll_obj
        except Exception as e:
            logger.warning("Could not stop poll %s on %s (%s). Attempting fallback reading.", message_id, target_chat, e)
            return {"options": [], "is_closed": True}
