"""
Comprehensive test suite for maya-telugu-vlog.
Mocks OpenRouter, Fal.ai, Supabase, and Telegram APIs to ensure 100% test coverage and reliability.
"""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.config import Settings
from src.db import DatabaseRepository
from src.image_engine import ImageEngine
from src.poll_resolver import PollResolver
from src.story_engine import EpisodePayload, StoryEngine
from src.telegram_publisher import TelegramPublisher
from src.main import run_pipeline, render_preview_html


@pytest.fixture
def mock_settings() -> Settings:
    """Provides test settings with mock mode enabled."""
    return Settings(
        OPENROUTER_API_KEY="mock_openrouter_key",
        STORY_ARCHITECT_MODEL="nousresearch/hermes-3-llama-3.1-70b",
        TELUGU_WRITER_MODEL="google/gemini-2.5-pro",
        FAL_KEY="mock_fal_key",
        MAYA_TRIGGER_WORD="maya_south_indian",
        SUPABASE_URL="https://mock.supabase.co",
        SUPABASE_SERVICE_KEY="mock_service_key",
        TELEGRAM_BOT_TOKEN="123456:MOCK_TOKEN",
        TELEGRAM_CHANNEL_ID="@test_maya_vlog",
        TELEGRAM_SPOILER_BLUR=True,
        DRY_RUN=True,
        MOCK_MODE=True,
    )


def test_settings_loading(mock_settings: Settings):
    """Verifies that configuration values load correctly."""
    assert mock_settings.MAYA_TRIGGER_WORD == "maya_south_indian"
    assert mock_settings.TELEGRAM_SPOILER_BLUR is True
    assert mock_settings.STORY_ARCHITECT_MODEL == "nousresearch/hermes-3-llama-3.1-70b"
    assert mock_settings.TELUGU_WRITER_MODEL == "google/gemini-2.5-pro"


def test_episode_payload_validation():
    """Tests Pydantic v2 validation and length trimming for EpisodePayload."""
    raw_teaser = "A" * 900  # Exceeds 850 max limit

    payload = EpisodePayload(
        episode_title_te="ఎపిసోడ్ 5: వర్షం మరియు కాఫీ ☕✨",
        teaser_caption_te=raw_teaser,
        full_story_te="ఇది పూర్తి స్టోరీ టెస్ట్...",
        image_prompt_en="maya_south_indian, candid portrait",
        outfit_used="Silk slip dress",
        summary_en="Summary of episode 5.",
        poll_question_te="ప్రశ్న: మాయ ఏం చేయాలి?" + ("?" * 300),  # Exceeds 250 limit
        poll_options_te=[
            "Option 1 " + ("x" * 120),  # Exceeds 95 chars limit
            "Option 2",
            "Option 3",
            "Option 4 (extra)",  # Should be trimmed to 3 options
        ],
    )

    # Teaser must be trimmed to <= 850
    assert len(payload.teaser_caption_te) <= 850
    assert "పూర్తి స్టోరీ కింద మెసేజ్లో చదవండి" in payload.teaser_caption_te

    # Poll question must be trimmed to <= 250
    assert len(payload.poll_question_te) <= 250

    # Poll options must be at most 3 options and each <= 95 chars
    assert len(payload.poll_options_te) == 3
    assert len(payload.poll_options_te[0]) <= 95


def test_telegram_publisher_split_text(mock_settings: Settings):
    """Verifies that story text is safely split along paragraph boundaries when exceeding 4000 chars."""
    publisher = TelegramPublisher(mock_settings)

    short_text = "ఇది చిన్న స్టోరీ. లైన్ 1.\n\nలైన్ 2."
    chunks = publisher.split_story_text(short_text)
    assert len(chunks) == 1
    assert chunks[0] == short_text

    # Create text exceeding 4000 characters across multiple paragraphs
    para1 = "Paragraph 1: " + ("కథ " * 600)  # ~1800 chars
    para2 = "Paragraph 2: " + ("మాయ " * 600)  # ~1800 chars
    para3 = "Paragraph 3: " + ("విక్రమ్ " * 600)  # ~1800 chars
    long_text = f"{para1}\n\n{para2}\n\n{para3}"

    split_chunks = publisher.split_story_text(long_text, max_chars=3000)
    assert len(split_chunks) >= 2
    for chunk in split_chunks:
        assert len(chunk) <= 3000


@pytest.mark.asyncio
async def test_telegram_publisher_api_calls(mock_settings: Settings):
    """Tests send_photo, send_message, send_poll, and stop_poll using TelegramPublisher."""
    publisher = TelegramPublisher(mock_settings)

    # Test send_photo in mock mode
    photo_id = await publisher.send_photo(
        photo=b"fake_image_bytes",
        caption="టెలిగ్రామ్ ఫోటో క్యాప్షన్",
    )
    assert photo_id > 0

    # Test send_message in mock mode
    msg_id = await publisher.send_message(
        text="పూర్తి తెలుగు స్టోరీ టెక్స్ట్",
        reply_to_message_id=photo_id,
    )
    assert msg_id > 0

    # Test send_poll in mock mode
    poll_id = await publisher.send_poll(
        question="మాయ ఏం చేయాలి?",
        options=["ఆప్షన్ 1", "ఆప్షన్ 2"],
        reply_to_message_id=msg_id,
    )
    assert poll_id > 0

    # Test stop_poll in mock mode
    stopped_poll = await publisher.stop_poll(message_id=poll_id)
    assert "options" in stopped_poll


@pytest.mark.asyncio
async def test_poll_resolver_winning_choice(mock_settings: Settings):
    """Tests PollResolver resolving Telegram poll and updating Supabase."""
    db = DatabaseRepository(mock_settings)
    publisher = TelegramPublisher(mock_settings)

    # Mock stop_poll response with realistic vote counts
    mock_poll_response = {
        "id": "poll_987",
        "question": "రేపు రాత్రి మాయ ఏం చేయాలి?",
        "options": [
            {"text": "అతని టెర్రస్ పైకి వెళ్లాలి", "voter_count": 45},
            {"text": "కర్టెన్స్ కొద్దిగా తెరిచి వైన్ తాగాలి", "voter_count": 128},
        ],
        "is_closed": True,
    }

    with patch.object(publisher, "stop_poll", new_callable=AsyncMock) as mock_stop:
        mock_stop.return_value = mock_poll_response
        resolver = PollResolver(db=db, publisher=publisher)

        winning_choice, pending_ep = await resolver.resolve_yesterday_poll()
        assert winning_choice == "కర్టెన్స్ కొద్దిగా తెరిచి వైన్ తాగాలి"

        # Verify DB was updated
        last_ep = db.get_last_episodes(limit=1)[0]
        assert last_ep.get("winning_poll_choice") == "కర్టెన్స్ కొద్దిగా తెరిచి వైన్ తాగాలి"


def test_image_engine_prompt_builder(mock_settings: Settings):
    """Verifies image prompt generation, trigger word inclusion, and softening logic."""
    engine = ImageEngine(mock_settings)

    raw_prompt = "{MAYA_TRIGGER_WORD}, wearing a sheer backless red saree in bedroom"
    built_prompt = engine.build_flux_prompt(raw_prompt)

    assert "maya_south_indian" in built_prompt
    assert "candid 35mm film photograph" in built_prompt
    assert "8k resolution" in built_prompt

    softened = engine.soften_prompt(built_prompt)
    assert "sheer" not in softened.lower()
    assert "backless" not in softened.lower()
    assert "fine translucent" in softened
    assert "open-back designer" in softened


@pytest.mark.asyncio
async def test_image_engine_generation_mock(mock_settings: Settings):
    """Tests image generation in mock mode returning valid bytes."""
    engine = ImageEngine(mock_settings)
    img_bytes, img_url = await engine.generate_image("maya_south_indian, test prompt")

    assert isinstance(img_bytes, bytes)
    assert len(img_bytes) > 50
    assert img_url.startswith("http")


def test_story_engine_mock_generation(mock_settings: Settings):
    """Tests StoryEngine mock episode generation for realistic colloquial Telugu."""
    engine = StoryEngine(mock_settings)
    arc = {
        "arc_number": 1,
        "arc_title": "Midnight Lights",
        "setting": "Penthouse",
        "love_interest_or_characters": "Maya & Vikram",
        "current_tension_level": 7,
    }

    payload = engine.generate_episode(
        episode_number=2,
        arc=arc,
        winning_poll_choice="కర్టెన్స్ కొద్దిగా తెరిచి వైన్ తాగాలి",
        past_summaries=["Past summary 1"],
        recent_outfits=["Emerald silk dress"],
    )

    assert isinstance(payload, EpisodePayload)
    assert "ఎపిసోడ్ 2" in payload.episode_title_te
    assert "హాయ్" in payload.teaser_caption_te
    assert "మాయ" in payload.full_story_te or "విక్రమ్" in payload.full_story_te
    assert len(payload.poll_options_te) >= 2
    assert "maya_south_indian" in payload.image_prompt_en


def test_database_repository_mock_fallback(mock_settings: Settings):
    """Tests DatabaseRepository methods with in-memory mock storage."""
    db = DatabaseRepository(mock_settings)

    active_arc = db.get_active_arc()
    assert active_arc is not None
    assert active_arc.get("arc_number") == 1

    episodes = db.get_last_episodes(limit=5)
    assert len(episodes) >= 1

    next_num = db.get_next_episode_number()
    assert next_num == 2

    # Insert a new episode
    new_ep = {
        "episode_number": next_num,
        "arc_id": active_arc["id"],
        "episode_title_te": "ఎపిసోడ్ 2",
        "teaser_caption_te": "టీజర్",
        "full_story_te": "పూర్తి స్టోరీ",
        "summary_en": "Summary 2",
        "outfit_used": "Black cocktail dress",
        "image_prompt_en": "prompt 2",
        "image_url": "https://example.com/2.jpg",
        "telegram_photo_msg_id": 201,
        "telegram_story_msg_id": 202,
        "telegram_poll_msg_id": 203,
        "poll_question_te": "ప్రశ్న?",
        "poll_options_json": [],
        "winning_poll_choice": None,
    }
    inserted = db.insert_episode(new_ep)
    assert inserted["episode_number"] == 2

    updated_next_num = db.get_next_episode_number()
    assert updated_next_num == 3


@pytest.mark.asyncio
async def test_full_pipeline_dry_run(mock_settings: Settings, tmp_path: Path):
    """End-to-end integration test verifying full dry-run execution and HTML generation."""
    out_html = tmp_path / "test_preview.html"

    exit_code = await run_pipeline(
        dry_run=True,
        mock_mode=True,
        output_html_path=str(out_html),
    )

    assert exit_code == 0
    assert out_html.exists()

    content = out_html.read_text(encoding="utf-8")
    assert "Maya Telugu Vlog" in content
    assert "Telegram Storytelling Engine Preview" in content
    assert "Tap to Reveal Maya's Photo" in content
    assert "data:image/jpeg;base64," in content
