"""
Database module for maya-telugu-vlog.
Provides Supabase client wrapper with fallback mock storage for local testing and dry-run.
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import uuid4
from datetime import datetime, timezone

from src.config import Settings

logger = logging.getLogger(__name__)

try:
    from supabase import create_client, Client
except ImportError:
    Client = None
    create_client = None


class DatabaseRepository:
    """Repository pattern managing access to Supabase or in-memory fallback."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Optional[Client] = None
        self._mock_mode = False

        # In-memory mock storage for local testing/dry-run
        self._mock_arcs: List[Dict[str, Any]] = [
            {
                "id": str(uuid4()),
                "arc_number": 1,
                "arc_title": "Midnight Lights of Jubilee Hills (అర్ధరాత్రి వెలుగులు)",
                "setting": "Luxury 18th-floor penthouse in Jubilee Hills, Hyderabad with a private rain terrace and panoramic city skyline view.",
                "love_interest_or_characters": "Maya (24, independent fashion stylist) and Vikram (28, intense fashion photographer across the terrace).",
                "current_tension_level": 6,
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
        self._mock_episodes: List[Dict[str, Any]] = [
            {
                "id": str(uuid4()),
                "episode_number": 1,
                "arc_id": self._mock_arcs[0]["id"],
                "episode_title_te": "ఎపిసోడ్ 1: 18వ అంతస్తు వర్షం & ఎదురింటి కెమెరా 🌧️✨",
                "teaser_caption_te": "హాయ్... నిన్న రాత్రి నా బాల్కనీలో వర్షం కురుస్తుంటే, ఎదురింటి టెర్రస్ పై ఒక షాడో కనిపించింది...",
                "full_story_te": "నిన్న రాత్రి సరిగ్గా 11:30 గంటలకు వర్షం ప్రారంభమైంది...",
                "summary_en": "Maya moved into her luxury Jubilee Hills penthouse and noticed Vikram on the opposite terrace observing her in the rain. An electric stare passed between them before Vikram picked up his camera.",
                "outfit_used": "Emerald green silk slip dress with spaghetti straps",
                "image_prompt_en": "maya_south_indian, candid 35mm photograph of a 24yo South Indian woman in emerald silk slip dress on penthouse balcony",
                "image_url": "https://example.com/mock_ep1.jpg",
                "telegram_photo_msg_id": 101,
                "telegram_story_msg_id": 102,
                "telegram_poll_msg_id": 103,
                "poll_question_te": "రేపు రాత్రి మాయ ఏం చేయాలి?",
                "poll_options_json": [
                    {"text": "టెర్రస్ పైకి వెళ్లి అతనితో మాట్లాడాలి", "voter_count": 84},
                    {"text": "కర్టెన్స్ కొద్దిగా తెరిచి అతన్ని గమనిస్తూ వైన్ తాగాలి", "voter_count": 142}
                ],
                "winning_poll_choice": None,  # Pending resolution!
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]

        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initializes Supabase client if valid credentials exist."""
        has_creds = (
            bool(self.settings.SUPABASE_URL)
            and bool(self.settings.SUPABASE_SERVICE_KEY)
            and not self.settings.SUPABASE_URL.startswith("https://your-project")
            and not self.settings.SUPABASE_SERVICE_KEY.startswith("your_")
        )

        if has_creds and create_client is not None and not self.settings.MOCK_MODE:
            try:
                self.client = create_client(
                    self.settings.SUPABASE_URL,
                    self.settings.SUPABASE_SERVICE_KEY
                )
                logger.info("Successfully connected to Supabase.")
            except Exception as e:
                logger.warning("Failed to initialize live Supabase client (%s). Falling back to mock DB.", e)
                self._mock_mode = True
        else:
            logger.info("Supabase credentials not configured or MOCK_MODE enabled. Using in-memory repository.")
            self._mock_mode = True

    def get_active_arc(self) -> Optional[Dict[str, Any]]:
        """Retrieves the current active story arc."""
        if not self._mock_mode and self.client:
            try:
                res = (
                    self.client.table("story_arcs")
                    .select("*")
                    .eq("is_active", True)
                    .order("arc_number", desc=True)
                    .limit(1)
                    .execute()
                )
                if res.data:
                    return res.data[0]
            except Exception as e:
                logger.error("Supabase error in get_active_arc: %s. Falling back to mock.", e)

        # Fallback
        for arc in self._mock_arcs:
            if arc.get("is_active"):
                return arc
        return self._mock_arcs[0] if self._mock_arcs else None

    def get_last_episodes(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetches the latest published episodes for LLM continuity context."""
        if not self._mock_mode and self.client:
            try:
                res = (
                    self.client.table("episodes")
                    .select("*")
                    .order("episode_number", desc=True)
                    .limit(limit)
                    .execute()
                )
                return res.data or []
            except Exception as e:
                logger.error("Supabase error in get_last_episodes: %s. Falling back to mock.", e)

        # Fallback sorted by episode_number descending
        sorted_episodes = sorted(
            self._mock_episodes,
            key=lambda ep: ep.get("episode_number", 0),
            reverse=True
        )
        return sorted_episodes[:limit]

    def get_recent_outfits(self, limit: int = 7) -> List[str]:
        """Returns list of outfits worn in recent episodes to prevent repetition."""
        episodes = self.get_last_episodes(limit=limit)
        outfits = [
            ep.get("outfit_used", "").strip()
            for ep in episodes
            if ep.get("outfit_used")
        ]
        return outfits

    def get_latest_episode_with_pending_poll(self) -> Optional[Dict[str, Any]]:
        """Finds the most recent episode whose poll has not yet been resolved."""
        if not self._mock_mode and self.client:
            try:
                res = (
                    self.client.table("episodes")
                    .select("*")
                    .not_.is_("telegram_poll_msg_id", "null")
                    .is_("winning_poll_choice", "null")
                    .order("episode_number", desc=True)
                    .limit(1)
                    .execute()
                )
                if res.data:
                    return res.data[0]
                return None
            except Exception as e:
                logger.error("Supabase error in get_latest_episode_with_pending_poll: %s", e)

        # Fallback search
        for ep in sorted(self._mock_episodes, key=lambda x: x.get("episode_number", 0), reverse=True):
            if ep.get("telegram_poll_msg_id") and not ep.get("winning_poll_choice"):
                return ep
        return None

    def update_winning_poll_choice(self, episode_id: str, winning_choice: str) -> None:
        """Updates winning poll option for a resolved episode."""
        if not self._mock_mode and self.client:
            try:
                self.client.table("episodes").update({
                    "winning_poll_choice": winning_choice
                }).eq("id", episode_id).execute()
                logger.info("Updated winning_poll_choice in Supabase for episode %s: %s", episode_id, winning_choice)
                return
            except Exception as e:
                logger.error("Supabase error in update_winning_poll_choice: %s", e)

        # Fallback update
        for ep in self._mock_episodes:
            if str(ep.get("id")) == str(episode_id):
                ep["winning_poll_choice"] = winning_choice
                logger.info("Updated mock episode %s with winning choice: %s", episode_id, winning_choice)
                break

    def get_next_episode_number(self) -> int:
        """Determines the next episode number."""
        last_episodes = self.get_last_episodes(limit=1)
        if last_episodes:
            return int(last_episodes[0].get("episode_number", 0)) + 1
        return 1

    def insert_episode(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Inserts a new episode record into the database."""
        if not self._mock_mode and self.client:
            try:
                res = self.client.table("episodes").insert(data).execute()
                if res.data:
                    logger.info("Inserted episode %s to Supabase successfully.", data.get("episode_number"))
                    return res.data[0]
            except Exception as e:
                logger.error("Failed to insert episode into Supabase: %s. Storing in mock memory.", e)

        # Fallback insert
        inserted = dict(data)
        if "id" not in inserted:
            inserted["id"] = str(uuid4())
        if "created_at" not in inserted:
            inserted["created_at"] = datetime.now(timezone.utc).isoformat()
        self._mock_episodes.append(inserted)
        logger.info("Stored episode %s in mock memory.", inserted.get("episode_number"))
        return inserted
