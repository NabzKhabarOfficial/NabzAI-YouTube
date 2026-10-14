# Brain handoff (NabzKhabarOfficial projects)

Read this whole file first, then continue the work. Updated: 2026-10-14 (13:55 Tehran).

## How to work with the owner (Younes)
- ALWAYS answer in Persian (English angers him), short and clear.
- Free tools only, never break any terms of service: no extra keys/projects/accounts to dodge quotas, nothing that needs a card (Cerebras = out, GitHub Models retired).
- Push code yourself with the GitHub tools (full file + blob sha). Files in .github/workflows the owner edits by hand: give him the COMPLETE file, every text he must paste in its own code block.
- Every check reads EVERYTHING (code, logs, state AND the real recent posts/videos). Health checks: read reports yourself, only tell him what is broken and what you fixed.
- Never invent facts; fact-check every story. Verify a helper's "bug" claim in the real code before fixing (Oct 14: two claimed bugs were false, see below).

## Repos (GitHub account NabzKhabarOfficial)
1. NabzKhabar: Telegram news bot «نبض خبر». bot.yml runs `python v13_ai_extra.py` (imports run_bot, installs patches, runs its main). Self-chains every 10 min + cron-job.org job "NabzKhabar" every 30 min (workflow_dispatch, fine-grained PAT). Python 3.11 (no backslash inside f-string expressions).
   - AI: Groq -> Gemini (AI_API_KEY) -> OpenRouter, cooldown-aware ask_pool, batched editor verdicts (8 per call), daily-quota 429 rests the model until reset (Gemini resets ~10:35 Tehran), meter _ai_usage/_ai_extra_log. No-AI holds 20 min.
   - Rules: no outlet/source name in posts (v13_final_guard, log docs/guard_log.json); posts open «💓 نبض خبر ▰▰▰▱▱» (v13_text_polish moves the pulse line from the post_design footer to the top); no region/topic labels; neutral wording (اسرائیل, not رژیم صهیونیستی/هلاکت/صهیونی) via v13_byline_cleaner NEUTRAL table; WAR_ZONE rule in editor gate; dedup chain text_polish -> incident_dedup -> event judge + importance rescue. «نبض آموزش» card 19:00, 30-bank, no repeats. Daily boards: weather 07, cars 11, education 19.
   - Editorial blocks (policy_scope_blocked / ai_unavailable_foreign) are remembered 6 h (run_bot _EDITORIAL_BLOCK_TTL_SECONDS) so the same title is not retried every run; the monitor then lists it as "important missed" with reason recent-editorial-block. Check items.json before calling it a miss (Oct 14: the Hormuz/Trump threat was already covered by the Syracuse-speech post).
2. NabzAI-YouTube (PRIVATE): channel "NABZ Mysteries" (@NabzMysteries) + Instagram «نبض معما».
   - Daily Short: cron-job.org 12:00 Tehran -> workflow_dispatch; src/mystery_short.py; published 22:30 Tehran; guard_today; a story never repeats. First comment: src/yt_comment.py via yt-comment.yml + cron-job.org 22:45 (owner pins it). Daily stats: src/yt_stats.py -> review/yt_stats.md (retention needs a refresh token with yt-analytics.readonly; today it reports invalid_scope).
   - Shorts ~30 s hook-first loops (the last beat may end open, e.g. «چون» / «:», so it loops into beat 1; that is by design). Hook beat <= 14 words, strangest fact first, dramatic first picture. Owner's 6-step template: contrast hook -> one question -> clue -> twist -> proven/probable/unknown -> ending reinterprets hook. Validate every story: 6-8 beats, 50-95 words.
   - Voice: Gemini 3.8 Flash TTS, voice Algenib, +1 semitone deeper, ONE take never spliced (audio_v 3), whisper-checked (src/voice_check.py). Only ONE key GEMINI_API_KEY (never add more).
   - Pronunciation: PRONOUNCE (mystery_short.py), FA_PRONOUNCE (reel_fa.py), review/pron_learned.json. Simple spoken language in all narration.
   - Music moods: src/music_mood.py (sea/crime/sky/ancient/vanish/cold), set one per new story.
   - Pictures: hfspace -> Cloudflare (CF_ACCOUNT_ID/CF_API_TOKEN, 10k free neurons/day) -> pollinations -> huggingface -> AI Horde. Instagram reel pictures: Nano Banana for the hook picture, then FLUX.2 klein 768x1344 portrait (src/__init__.py, added Oct 14; the state does not record which provider made a picture, so check the first klein reels by eye). Max 6 reels built per day.
   - Instagram: NEVER unofficial posting. src/ig_pack.py builds a weekly pack (release week-YYYY-MM-DD, 15 reels/week from Oct 19, owner's golden hours in GOLDEN); src/ig_buffer.py schedules via Buffer free API (<= 10 queued) + story teasers. Noon = true story that became a film («فیلم» comment CTA -> Zaprep DM -> nabz-reels /films/), night = mystery. Slide posts src/ig_slides.py Tue/Thu/Sat ~17:00, no music.
   - Story banks: content/mysteries.json (EN base, 51; 13 used by Oct 14), mysteries_add.json (extra EN, IG only), mysteries_fa.json (mysteries_fa_add.json is auto-merged into it and then deleted; recreate it for a new batch), only ids in story_notes_fa.json get planned, mysteries_override.json, ig_carousels*.json (later file overrides by id; a post needs caption + slides), ig_films_fa.json.
3. nabz-film: film site, updates every 6 h (data/status.json; scripts/build_catalog.py translates overviews with Groq, cache data/fa_ai.json).
4. nabz-tools: tools site, rates.yml every 2 h (commits data/rates.json only when it changed).

## Done on Oct 14 (deep review, session 2)
- NabzKhabar v13_final_guard.py: outlet names accept spelling variants («اسکای نوز» leaked in the Gaza post of 10:51), a DETAIL line naming an outlet is dropped before the caption is built (lead kept, story still published), «صهیونی» -> «اسرائیلی» added to the NEUTRAL table at install («آمریکایی-صهیونی» leaked) and refused if left, AI sense check told that a different name form (Donald vs Trump) is never a contradiction (it had blocked a Trump post). First run after the change (10:23 UTC): healthy, no errors.
- Checked and NOT bugs (do not "fix"): post_design footer pulse (text_polish moves it to the top); nabz-tools USDT converter (rialPer already uses market.usdt first).
- NabzAI-YouTube: content/ig_carousels_4.json, 6 fact-checked Iranian history slide posts in the six-step arc: kaaba-zartosht (Oct 27), oxus-treasure (Oct 29), behistun (Oct 31), chogha-zanbil (Nov 3), marlik (Nov 5), shapur-cave (Nov 7). Slide bank now runs to Nov 7.
- review/pron_learned.json: FA respellings for names narrated in week 2026-10-19 (گلن, کونیگسبرگ, وایت‌چپل, اینویت, نورنبرگ).
- State seen: Shorts built/published Oct 8-14 (lead-masks today); week 2026-10-12 pack done 14/14; week 2026-10-19 planned (15 reels, first build today), Buffer queue full (10/10) and healthy; nabz-film missing Persian overviews 21 -> 11, last run no 429.

## Open work (as of Oct 14 2026)
- nabz-tools: GitHub skipped several 2-hourly runs (gaps 12:47-20:16 Oct 13, 04:59-10:20+ Oct 14). Owner should add a cron-job.org backup job (same as the other repos: POST https://api.github.com/repos/NabzKhabarOfficial/nabz-tools/actions/workflows/rates.yml/dispatches, body {"ref":"main"}, every 2 h at :17; the fine-grained PAT needs nabz-tools with Actions read/write).
- nabz-film: let the 6-hourly runs finish the 11 missing Persian overviews; if 429 comes back, add a per-run cap + Retry-After backoff + failure cooldown in translate_overviews (build_catalog.py, 61 KB, edit carefully). 2 titles (s334351, s336036) have no overview at all in any language (frontend shows the Persian placeholder; fine).
- Retention data: owner must re-authorize the YouTube refresh token with yt-analytics.readonly (yt_stats.md says invalid_scope). Weakest Shorts by views: dyatlov 6, somerton 8, dancing-plague 12; best: flight-19 112, roanoke 106, tunguska 96.
- Check the first FLUX.2 klein reel pictures (oak-island Sat Oct 17 21:34, max-headroom Sun Oct 18).
- Persian bank: 53 FA stories not yet aired, lasts to mid-November at 15/week; film share ~51% (target ~40%), so the next batch should be mostly non-film mysteries. Add respellings + music mood for every new story.
- Mehrestan (Oct 14): the later report «شهادت یک مامور پلیس» was skipped as a duplicate of «شکست حمله تروریست ها به خودروی پلیس». If this pattern repeats (first post says no casualties, later report has a death), let incident_dedup pass a casualty update when the earlier post had no casualties.
- Monitor ai_pool counts retired models still present in ai_model_health.json (cerebras, github); cosmetic.
- Optional: deep audit of the ~30 NabzKhabar v13 modules for dead code.

## Keep this file updated
After every important change, update this file (and the date at the top).
