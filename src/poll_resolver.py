"""
Poll Resolver module for maya-telugu-vlog.
Closes yesterday's Telegram subscriber poll via `stopPoll`, extracts the winning option,
updates Supabase, and feeds the audience's decision directly into today's story generator.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from src.db import DatabaseRepository
from src.telegram_publisher import TelegramPublisher

logger = logging.getLogger(__name__)

DEFAULT_FALLBACK_CHOICE = "మాయ బాల్కనీలో నిలబడి వర్షంలో తడుస్తూ విక్రమ్ వైపు కళ్లలోకి సూటిగా చూసింది (Maya stayed on the rain-soaked balcony, meeting Vikram's gaze directly)."


class PollResolver:
    """Manages Telegram poll resolution and database synchronization."""

    def __init__(self, db: DatabaseRepository, publisher: TelegramPublisher):
        self.db = db
        self.publisher = publisher

    async def resolve_yesterday_poll(self) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Finds the latest episode with an unresolved poll, queries Telegram to stop the poll
        and tally votes, records the winning choice in Supabase, and returns the decision.

        Returns:
            Tuple of (winning_poll_choice: str, episode_dict: dict)
        """
        pending_episode = self.db.get_latest_episode_with_pending_poll()

        if not pending_episode:
            logger.info("No pending unresolved polls found in database.")
            return DEFAULT_FALLBACK_CHOICE, None

        poll_msg_id = pending_episode.get("telegram_poll_msg_id")
        episode_id = pending_episode.get("id")
        stored_options = pending_episode.get("poll_options_json") or []

        logger.info(
            "Resolving poll for Episode #%s (poll_msg_id: %s)...",
            pending_episode.get("episode_number"), poll_msg_id
        )

        winning_choice: Optional[str] = None

        if poll_msg_id:
            try:
                poll_result = await self.publisher.stop_poll(message_id=int(poll_msg_id))
                options = poll_result.get("options") or []

                if options:
                    # Sort options by voter_count descending
                    sorted_options = sorted(
                        options,
                        key=lambda opt: opt.get("voter_count", 0),
                        reverse=True
                    )
                    top_option = sorted_options[0]
                    top_text = top_option.get("text", "").strip()
                    vote_count = top_option.get("voter_count", 0)

                    winning_choice = top_text
                    logger.info(
                        "Winning poll choice determined from Telegram: '%s' with %d votes.",
                        winning_choice, vote_count
                    )

            except Exception as e:
                logger.warning(
                    "Error while calling Telegram stopPoll on message %s: %s. Using fallback options.",
                    poll_msg_id, e
                )

        # Fallback if Telegram call returned no valid options
        if not winning_choice:
            if isinstance(stored_options, list) and len(stored_options) > 0:
                first_opt = stored_options[0]
                if isinstance(first_opt, dict):
                    winning_choice = first_opt.get("text", DEFAULT_FALLBACK_CHOICE)
                elif isinstance(first_opt, str):
                    winning_choice = first_opt
            else:
                winning_choice = DEFAULT_FALLBACK_CHOICE
            logger.info("Selected fallback winning choice: '%s'", winning_choice)

        # Update Supabase database
        if episode_id and winning_choice:
            self.db.update_winning_poll_choice(str(episode_id), winning_choice)

        return winning_choice, pending_episode
