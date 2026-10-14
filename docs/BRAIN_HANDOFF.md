# Brain handoff (NabzKhabarOfficial projects)

Read this whole file first, then continue the work. Updated: 2026-10-14.

## How to work with the owner (Younes)
- ALWAYS answer in Persian (English angers him), short and clear.
- Free tools only, never break any terms of service: no extra keys/projects/accounts to dodge quotas, nothing that needs a card (Cerebras = out, GitHub Models retired).
- Push code yourself with the GitHub tools (full file + blob sha). Files in .github/workflows the owner edits by hand: give him the COMPLETE file, every text he must paste in its own code block.
- Every check reads EVERYTHING (code, logs, state AND the real recent posts/videos). Health checks: read reports yourself, only tell him what is broken and what you fixed.
- Never invent facts; fact-check every story.

## Repos (GitHub account NabzKhabarOfficial)
1. NabzKhabar: Telegram news bot «نبض خبر». bot.yml runs `python v13_ai_extra.py` (imports run_bot, installs patches, runs its main). Self-chains every 10 min + cron-job.org job "NabzKhabar" every 30 min (workflow_dispatch, fine-grained PAT). Python 3.11 (no backslash inside f-string expressions).
   - AI: Groq -> Gemini (AI_API_KEY) -> OpenRouter, cooldown-aware ask_pool, batched editor verdicts (8 per call), daily-quota 429 rests the model until reset (Gemini resets ~10:35 Tehran), meter _ai_usage/_ai_extra_log. No-AI holds 20 min.
   - Rules: no outlet/source name in posts (v13_final_guard, log docs/guard_log.json); posts open «💓 نبض خبر ▰▰▰▱▱»; no region/topic labels; neutral wording (اسرائیل, not رژیم صهیونیستی/هلاکت) via v13_byline_cleaner; WAR_ZONE rule in editor gate; dedup chain text_polish -> incident_dedup -> event judge + importance rescue. «نبض آموزش» card 19:00, 30-bank, no repeats. Daily boards: weather, cars, education.
2. NabzAI-YouTube (PRIVATE): channel "NABZ Mysteries" (@NabzMysteries) + Instagram «نبض معما».
   - Daily Short: cron-job.org 12:00 Tehran -> workflow_dispatch; src/mystery_short.py; published 22:30 Tehran; guard_today; a story never repeats. First comment: src/yt_comment.py via yt-comment.yml + cron-job.org 22:45 (owner pins it). Daily stats: src/yt_stats.py -> review/yt_stats.md (retention needs a refresh token with yt-analytics.readonly).
   - Shorts ~30 s hook-first loops. Hook beat <= 14 words, strangest fact first, dramatic first picture. Owner's 6-step template: contrast hook -> one question -> clue -> twist -> proven/probable/unknown -> ending reinterprets hook. Validate every story: 6-8 beats, 50-95 words.
   - Voice: Gemini 3.8 Flash TTS, voice Algenib, +1 semitone deeper, ONE take never spliced (audio_v 3), whisper-checked (src/voice_check.py). Only ONE key GEMINI_API_KEY (never add more).
   - Pronunciation: PRONOUNCE (mystery_short.py), FA_PRONOUNCE (reel_fa.py), review/pron_learned.json. Simple spoken language in all narration.
   - Music moods: src/music_mood.py (sea/crime/sky/ancient/vanish/cold), set one per new story.
   - Pictures: hfspace -> Cloudflare (CF_ACCOUNT_ID/CF_API_TOKEN, 10k free neurons/day) -> pollinations -> huggingface -> AI Horde. Instagram reel pictures: Nano Banana for the hook picture, then FLUX.2 klein 768x1344 portrait (src/__init__.py, added Oct 14; check the first klein reels look sharp). Max 6 reels built per day.
   - Instagram: NEVER unofficial posting. src/ig_pack.py builds a weekly pack (release week-YYYY-MM-DD, 15 reels/week from Oct 19, owner's golden hours in GOLDEN); src/ig_buffer.py schedules via Buffer free API (<= 10 queued) + story teasers. Noon = true story that became a film («فیلم» comment CTA -> Zaprep DM -> nabz-reels /films/), night = mystery. Slide posts src/ig_slides.py Tue/Thu/Sat ~17:00, no music.
   - Story banks: content/mysteries.json (EN base), mysteries_add.json (extra EN, IG only), mysteries_fa.json + mysteries_fa_add.json (auto-merged), only ids in story_notes_fa.json get planned, mysteries_override.json, ig_carousels*.json, ig_films_fa.json.
3. nabz-film: film site, updates every 6 h (data/status.json).
4. nabz-tools: tools site, updates every 2 h.

## Open work (as of Oct 14 2026)
- After ~10:35 Tehran: check NabzKhabar runs (_ai_usage, batching works, posts go out; openrouter once gave no usable verdict).
- nabz-film: 21 overviews missing Persian + 429 translation errors.
- Check the first FLUX.2 klein reel pictures (first one: oak-island, Sat Oct 17 21:34).
- Carousel bank ends Oct 24: write a new batch (same 6-step arc).
- Keep the Persian bank ahead (15 stories/week, ~40% film stories); add respellings + music mood for every new story.
- Optional: deep audit of the ~30 NabzKhabar v13 modules for dead code.

## Keep this file updated
After every important change, update this file (and the date at the top).
