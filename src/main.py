"""
Main entrypoint for maya-telugu-vlog.
Coordinates the entire daily pipeline:
  1. Resolves yesterday's Telegram audience vote
  2. Fetches continuity memory from Supabase
  3. Generates 2-stage Telugu episode & Flux LoRA prompt
  4. Generates photorealistic vertical portrait via Fal.ai
  5. Publishes 3-message sequence to Telegram Channel
  6. Saves new episode state to Supabase
Supports both `--dry-run` (local HTML/image preview) and `--live` execution.
"""

import argparse
import asyncio
import base64
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.config import Settings, get_settings
from src.db import DatabaseRepository
from src.image_engine import ImageEngine
from src.poll_resolver import PollResolver
from src.story_engine import EpisodePayload, StoryEngine
from src.telegram_publisher import TelegramPublisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("maya-pipeline")


def render_preview_html(
    payload: EpisodePayload,
    image_bytes: bytes,
    episode_num: int,
    winning_choice: Optional[str],
    out_path: str = "preview_output.html"
) -> str:
    """Generates an aesthetic Telegram-themed HTML preview file for local browser inspection."""
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    mime = "image/jpeg"

    # Convert newlines to breaks for HTML rendering
    story_html = payload.full_story_te.replace("\n", "<br>")
    teaser_html = payload.teaser_caption_te.replace("\n", "<br>")

    poll_options_markup = "".join(
        f'<div class="poll-option"><div class="circle"></div><span>{opt}</span></div>'
        for opt in payload.poll_options_te
    )

    html_content = f"""<!DOCTYPE html>
<html lang="te">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Maya Telugu Vlog - Episode {episode_num} Preview</title>
  <style>
    :root {{
      --tg-bg: #0f141c;
      --tg-bubble: #1e293b;
      --tg-reply: #131b26;
      --tg-accent: #38bdf8;
      --tg-text: #f1f5f9;
      --tg-muted: #94a3b8;
      --tg-gold: #f59e0b;
      --tg-red: #f43f5e;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--tg-bg);
      color: var(--tg-text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans Telugu", sans-serif;
      line-height: 1.6;
      padding: 24px 12px;
    }}
    .container {{
      max-width: 580px;
      margin: 0 auto;
    }}
    .header-badge {{
      display: inline-block;
      background: linear-gradient(135deg, #f43f5e, #fb923c);
      color: white;
      font-size: 12px;
      font-weight: 700;
      padding: 4px 12px;
      border-radius: 999px;
      margin-bottom: 8px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .meta-card {{
      background: rgba(30, 41, 59, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 24px;
      font-size: 13px;
    }}
    .meta-row {{ margin-bottom: 6px; }}
    .meta-row strong {{ color: var(--tg-accent); }}
    .telegram-channel {{
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}
    .message-card {{
      background: var(--tg-bubble);
      border-radius: 16px;
      padding: 14px 16px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      border: 1px solid rgba(255, 255, 255, 0.05);
      position: relative;
    }}
    .message-card.photo-card {{
      padding: 0;
      overflow: hidden;
    }}
    .photo-wrapper {{
      position: relative;
      cursor: pointer;
      overflow: hidden;
      max-height: 540px;
      background: #000;
      display: flex;
      justify-content: center;
      align-items: center;
    }}
    .photo-wrapper img {{
      width: 100%;
      height: auto;
      display: block;
      transition: filter 0.3s ease;
    }}
    .spoiler-overlay {{
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(15, 20, 28, 0.75);
      backdrop-filter: blur(18px);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      color: white;
      font-weight: bold;
      transition: opacity 0.3s ease;
      cursor: pointer;
    }}
    .photo-wrapper.revealed .spoiler-overlay {{
      opacity: 0;
      pointer-events: none;
    }}
    .caption-box {{
      padding: 14px 16px;
      font-size: 15px;
    }}
    .reply-header {{
      background: rgba(56, 189, 248, 0.1);
      border-left: 3px solid var(--tg-accent);
      padding: 6px 10px;
      border-radius: 4px;
      margin-bottom: 12px;
      font-size: 12px;
      color: var(--tg-accent);
      font-weight: 600;
    }}
    .story-body {{
      font-size: 15px;
      line-height: 1.7;
    }}
    .poll-card {{
      background: var(--tg-bubble);
      border-radius: 16px;
      padding: 18px;
    }}
    .poll-title {{
      font-size: 16px;
      font-weight: 700;
      margin-bottom: 14px;
      color: var(--tg-text);
    }}
    .poll-meta {{
      font-size: 12px;
      color: var(--tg-muted);
      margin-bottom: 16px;
    }}
    .poll-option {{
      display: flex;
      align-items: center;
      gap: 12px;
      background: rgba(255, 255, 255, 0.04);
      padding: 12px 14px;
      border-radius: 10px;
      margin-bottom: 10px;
      border: 1px solid rgba(255, 255, 255, 0.06);
      cursor: pointer;
      transition: background 0.2s ease;
    }}
    .poll-option:hover {{
      background: rgba(56, 189, 248, 0.1);
      border-color: var(--tg-accent);
    }}
    .circle {{
      width: 18px;
      height: 18px;
      border-radius: 50%;
      border: 2px solid var(--tg-accent);
      flex-shrink: 0;
    }}
    .prompt-box {{
      background: #000;
      border-radius: 8px;
      padding: 12px;
      font-family: monospace;
      font-size: 12px;
      color: #38bdf8;
      overflow-x: auto;
      margin-top: 10px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div style="text-align: center; margin-bottom: 20px;">
      <span class="header-badge">Telegram Storytelling Engine Preview</span>
      <h1 style="font-size: 24px; margin-top: 4px;">{payload.episode_title_te}</h1>
      <p style="color: var(--tg-muted); font-size: 13px;">Automated Episode Run • Character: Maya (24, Hyderabad)</p>
    </div>

    <!-- Metadata Panel -->
    <div class="meta-card">
      <div class="meta-row"><strong>Episode Number:</strong> #{episode_num}</div>
      <div class="meta-row"><strong>Yesterday's Subscriber Vote Decision:</strong> {winning_choice or "None (Opening Arc)"}</div>
      <div class="meta-row"><strong>Outfit Used:</strong> {payload.outfit_used}</div>
      <div class="meta-row"><strong>English Continuity Summary:</strong> {payload.summary_en}</div>
      <div class="meta-row"><strong>Teaser Character Count:</strong> {len(payload.teaser_caption_te)} / 850 max</div>
      <div class="meta-row"><strong>Full Story Character Count:</strong> {len(payload.full_story_te)} chars</div>
      <div class="meta-row" style="margin-top: 8px;">
        <strong>Flux.1 LoRA Image Prompt:</strong>
        <div class="prompt-box">{payload.image_prompt_en}</div>
      </div>
    </div>

    <!-- Telegram Channel Stream Simulator -->
    <div class="telegram-channel">
      
      <!-- Post 1: Photo + Teaser Hook -->
      <div class="message-card photo-card">
        <div class="photo-wrapper" id="photoWrapper" onclick="this.classList.toggle('revealed')">
          <img src="data:{mime};base64,{image_b64}" alt="Maya Daily Image">
          <div class="spoiler-overlay">
            <span style="font-size: 24px; margin-bottom: 6px;">🔞 👁️</span>
            <span>Tap to Reveal Maya's Photo</span>
            <span style="font-size: 11px; opacity: 0.8; margin-top: 4px;">(Simulating Telegram Spoiler Blur)</span>
          </div>
        </div>
        <div class="caption-box">
          {teaser_html}
        </div>
      </div>

      <!-- Post 2: Full Story Reply -->
      <div class="message-card">
        <div class="reply-header">
          ↩ In reply to Maya's Photo Post #1
        </div>
        <div class="story-body">
          {story_html}
        </div>
      </div>

      <!-- Post 3: Interactive Poll Reply -->
      <div class="poll-card">
        <div class="reply-header">
          ↩ In reply to Full Story Post #2
        </div>
        <div class="poll-title">📊 {payload.poll_question_te}</div>
        <div class="poll-meta">Anonymous Poll • Subscribed Voters Only</div>
        <div class="poll-options">
          {poll_options_markup}
        </div>
      </div>

    </div>
  </div>
</body>
</html>
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return out_path


async def run_pipeline(
    dry_run: bool = False,
    mock_mode: bool = False,
    output_html_path: str = "preview_output.html",
) -> int:
    """Executes the full automated Maya Telugu Vlog sequence."""
    settings = get_settings()

    # Override settings from CLI flags
    if dry_run:
        settings.DRY_RUN = True
    if mock_mode or not settings.is_fully_configured_for_live:
        settings.MOCK_MODE = True

    logger.info("=================================================================")
    logger.info("   MAYA TELUGU VLOG - DAILY EPISODE AUTOMATION")
    logger.info("   Mode: %s | Mock Mode: %s", "DRY-RUN" if settings.DRY_RUN else "LIVE", settings.MOCK_MODE)
    logger.info("=================================================================")

    # Initialize subsystems
    db = DatabaseRepository(settings)
    publisher = TelegramPublisher(settings)
    poll_resolver = PollResolver(db=db, publisher=publisher)
    story_engine = StoryEngine(settings)
    image_engine = ImageEngine(settings)

    # -------------------------------------------------------------------------
    # STEP 1: Resolve Yesterday's Subscriber Poll Decision
    # -------------------------------------------------------------------------
    logger.info("Step 1: Resolving yesterday's subscriber Telegram vote...")
    winning_choice, prev_episode = await poll_resolver.resolve_yesterday_poll()
    logger.info("Active Subscriber Choice: %s", winning_choice)

    # -------------------------------------------------------------------------
    # STEP 2: Gather Story Context and Continuity Memory
    # -------------------------------------------------------------------------
    logger.info("Step 2: Fetching story arc and recent episode history...")
    active_arc = db.get_active_arc() or {
        "arc_number": 1,
        "arc_title": "Midnight Lights of Jubilee Hills",
        "setting": "Luxury Penthouse in Jubilee Hills, Hyderabad",
        "love_interest_or_characters": "Maya and Vikram",
        "current_tension_level": 6,
    }
    last_episodes = db.get_last_episodes(limit=5)
    past_summaries = [ep.get("summary_en", "") for ep in last_episodes if ep.get("summary_en")]
    recent_outfits = db.get_recent_outfits(limit=7)
    next_episode_num = db.get_next_episode_number()

    logger.info(
        "Current Arc: '%s' | Episode #%d | Past Summaries: %d | Tracked Outfits: %d",
        active_arc.get("arc_title"), next_episode_num, len(past_summaries), len(recent_outfits)
    )

    # -------------------------------------------------------------------------
    # STEP 3: Run 2-Stage Story Engine
    # -------------------------------------------------------------------------
    logger.info("Step 3: Generating today's Telugu vlog episode & image prompt...")
    payload = story_engine.generate_episode(
        episode_number=next_episode_num,
        arc=active_arc,
        winning_poll_choice=winning_choice,
        past_summaries=past_summaries,
        recent_outfits=recent_outfits,
    )
    logger.info("Generated Title: %s", payload.episode_title_te)
    logger.info("Selected Outfit: %s", payload.outfit_used)

    # -------------------------------------------------------------------------
    # STEP 4: Generate Maya's Image via Fal.ai Flux LoRA
    # -------------------------------------------------------------------------
    logger.info("Step 4: Generating character-consistent image via Fal.ai...")
    image_bytes, image_url = await image_engine.generate_image(
        raw_prompt=payload.image_prompt_en,
        retry_on_error=True
    )
    logger.info("Image generated successfully. Byte size: %d bytes", len(image_bytes))

    # Save local preview image
    preview_img_path = Path(output_html_path).parent / "preview_image.jpg"
    try:
        preview_img_path.write_bytes(image_bytes)
        logger.info("Saved local image copy to: %s", preview_img_path.resolve())
    except Exception as e:
        logger.warning("Could not write preview image to disk: %s", e)

    # -------------------------------------------------------------------------
    # STEP 5: Publish or Render Preview
    # -------------------------------------------------------------------------
    if settings.DRY_RUN:
        logger.info("Step 5 (DRY-RUN): Generating local HTML preview...")
        rendered_path = render_preview_html(
            payload=payload,
            image_bytes=image_bytes,
            episode_num=next_episode_num,
            winning_choice=winning_choice,
            out_path=output_html_path,
        )
        logger.info("=================================================================")
        logger.info("✅ DRY-RUN COMPLETE!")
        logger.info("Open the following preview file in your browser:")
        logger.info("👉 file://%s", Path(rendered_path).resolve())
        logger.info("=================================================================")
        return 0

    # LIVE PUBLISHING
    logger.info("Step 5 (LIVE): Publishing 3-step sequence to Telegram Channel: %s...", settings.TELEGRAM_CHANNEL_ID)

    # Post 1: Photo + Teaser Hook
    photo_msg_id = await publisher.send_photo(
        photo=image_bytes,
        caption=payload.teaser_caption_te,
        parse_mode="HTML",
        has_spoiler=settings.TELEGRAM_SPOILER_BLUR,
    )

    # Post 2: Full Story Reply
    story_msg_id = await publisher.send_message(
        text=payload.full_story_te,
        reply_to_message_id=photo_msg_id,
        parse_mode="HTML",
    )

    # Post 3: Interactive Decision Poll Reply
    poll_msg_id = await publisher.send_poll(
        question=payload.poll_question_te,
        options=payload.poll_options_te,
        reply_to_message_id=story_msg_id,
        is_anonymous=True,
    )

    logger.info("Telegram Sequence Published: Photo #%s -> Story #%s -> Poll #%s", photo_msg_id, story_msg_id, poll_msg_id)

    # -------------------------------------------------------------------------
    # STEP 6: Save New Episode Record to Supabase
    # -------------------------------------------------------------------------
    logger.info("Step 6: Recording episode to Supabase database...")
    episode_record = {
        "episode_number": next_episode_num,
        "arc_id": active_arc.get("id"),
        "episode_title_te": payload.episode_title_te,
        "teaser_caption_te": payload.teaser_caption_te,
        "full_story_te": payload.full_story_te,
        "summary_en": payload.summary_en,
        "outfit_used": payload.outfit_used,
        "image_prompt_en": payload.image_prompt_en,
        "image_url": image_url,
        "telegram_photo_msg_id": photo_msg_id,
        "telegram_story_msg_id": story_msg_id,
        "telegram_poll_msg_id": poll_msg_id,
        "poll_question_te": payload.poll_question_te,
        "poll_options_json": [{"text": opt, "voter_count": 0} for opt in payload.poll_options_te],
        "winning_poll_choice": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    db.insert_episode(episode_record)
    logger.info("=================================================================")
    logger.info("🎉 EPISODE #%d PUBLISHED SUCCESSFULLY TO TELEGRAM & SUPABASE!", next_episode_num)
    logger.info("=================================================================")
    return 0


def cli() -> None:
    """CLI wrapper parsing command-line flags and running the async pipeline."""
    parser = argparse.ArgumentParser(description="Maya Telugu Vlog Automated Daily Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Generate local preview without posting to Telegram")
    parser.add_argument("--live", action="store_true", help="Force live publishing to Telegram and Supabase")
    parser.add_argument("--mock", action="store_true", help="Force mock LLM & image generation")
    parser.add_argument("--output-html", default="preview_output.html", help="Path for HTML preview output")

    args = parser.parse_args()

    # Default to dry-run if neither --live nor --dry-run is explicitly given and live keys are absent
    settings = get_settings()
    is_dry = args.dry_run or (not args.live and not settings.is_fully_configured_for_live)

    exit_code = asyncio.run(
        run_pipeline(
            dry_run=is_dry,
            mock_mode=args.mock,
            output_html_path=args.output_html,
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    cli()
