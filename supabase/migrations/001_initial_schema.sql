-- ============================================================================
-- Supabase Schema Migration: 001_initial_schema.sql
-- Project: Maya Telugu Vlog (Automated Daily Telugu Storytelling & Visual Pipeline)
-- ============================================================================

-- Enable pgcrypto extension for UUID generation if not already active
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ----------------------------------------------------------------------------
-- Table 1: story_arcs
-- Manages high-level narrative arcs, settings, love interests, and tension levels
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS story_arcs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    arc_number INT NOT NULL UNIQUE,
    arc_title TEXT NOT NULL,
    setting TEXT NOT NULL,
    love_interest_or_characters TEXT NOT NULL,
    current_tension_level INT NOT NULL DEFAULT 5 CHECK (current_tension_level BETWEEN 1 AND 10),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- Index for quickly fetching active story arc
CREATE INDEX IF NOT EXISTS idx_story_arcs_active ON story_arcs (is_active);

-- ----------------------------------------------------------------------------
-- Table 2: episodes
-- Stores each daily published episode, prompts, image links, and Telegram metrics
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS episodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    episode_number INT NOT NULL UNIQUE,
    arc_id UUID REFERENCES story_arcs(id) ON DELETE SET NULL,
    episode_title_te TEXT NOT NULL,
    teaser_caption_te TEXT NOT NULL CHECK (char_length(teaser_caption_te) <= 850),
    full_story_te TEXT NOT NULL,
    summary_en TEXT NOT NULL,
    outfit_used TEXT NOT NULL,
    image_prompt_en TEXT NOT NULL,
    image_url TEXT NOT NULL,
    telegram_photo_msg_id BIGINT,
    telegram_story_msg_id BIGINT,
    telegram_poll_msg_id BIGINT,
    poll_question_te TEXT,
    poll_options_json JSONB,
    winning_poll_choice TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_episodes_episode_number ON episodes (episode_number DESC);
CREATE INDEX IF NOT EXISTS idx_episodes_arc_id ON episodes (arc_id);
CREATE INDEX IF NOT EXISTS idx_episodes_pending_poll ON episodes (telegram_poll_msg_id) WHERE winning_poll_choice IS NULL;

-- ----------------------------------------------------------------------------
-- Seed Data: Arc 1 - The Midnight Penthouse Encounters
-- ----------------------------------------------------------------------------
INSERT INTO story_arcs (
    arc_number,
    arc_title,
    setting,
    love_interest_or_characters,
    current_tension_level,
    is_active
)
VALUES (
    1,
    'Midnight Lights of Jubilee Hills (అర్ధరాత్రి వెలుగులు)',
    'Luxury 18th-floor penthouse in Jubilee Hills, Hyderabad featuring a private rain terrace and expansive glass balcony looking across to the neighboring terrace.',
    'Maya (24, independent fashion stylist & aesthetics curator) and Vikram (28, intense, reclusive international fashion photographer with an analog Leica camera and deep magnetic charm).',
    6,
    TRUE
)
ON CONFLICT (arc_number) DO UPDATE SET
    arc_title = EXCLUDED.arc_title,
    setting = EXCLUDED.setting,
    love_interest_or_characters = EXCLUDED.love_interest_or_characters,
    current_tension_level = EXCLUDED.current_tension_level,
    is_active = EXCLUDED.is_active;
