# Brain handoff (NabzKhabarOfficial projects)

Read this whole file first, then continue the work. Updated: 2026-10-14 (18:55 Tehran).

## How to work with the owner (Younes)
- ALWAYS answer in Persian (English angers him), short and clear. When he must do something by hand, give numbered step-by-step instructions (one action per step, exact button names), never a dense summary; he asked "never confuse me".
- Free tools only, never break any terms of service: no extra keys/projects/accounts to dodge quotas, nothing that needs a card (Cerebras = out, GitHub Models retired).
- Push code yourself with the GitHub tools (full file + blob sha). Files in .github/workflows the owner edits by hand: give him the COMPLETE file, every text he must paste in its own code block.
- Every check reads EVERYTHING (code, logs, state AND the real recent posts/videos). Health checks: read reports yourself, only tell him what is broken and what you fixed. The GitHub tools cannot open YouTube/Instagram pages: say so instead of claiming you watched them.
- Never invent facts; fact-check every story. Verify a helper's "bug" claim in the real code before fixing (Oct 14: two claimed bugs were false, see below).

## Repos (GitHub account NabzKhabarOfficial)
1. NabzKhabar: Telegram news bot «نبض خبر». bot.yml runs `python v13_ai_extra.py` (imports run_bot, installs patches, runs its main). Self-chains every 10 min + cron-job.org job "NabzKhabar" every 30 min (workflow_dispatch, fine-grained PAT). Python 3.11 (no backslash inside f-string expressions).
   - AI: Groq -> Gemini (AI_API_KEY) -> OpenRouter, cooldown-aware ask_pool, batched editor verdicts (8 per call, each verdict must echo its story's first title words "h", mismatches dropped), daily-quota 429 rests the model until reset (Gemini resets ~10:35 Tehran), meter _ai_usage/_ai_extra_log. No-AI holds 20 min.
   - Rules: no outlet/source name in posts (v13_final_guard + v13_chrome_scrub, log docs/guard_log.json); posts open «💓 نبض خبر ▰▰▰▱▱» (v13_text_polish moves the pulse line from the post_design footer to the top); no region/topic labels; neutral wording (اسرائیل, not رژیم صهیونیستی/هلاکت/صهیونی) via v13_byline_cleaner NEUTRAL table; WAR_ZONE rule in editor gate; dedup chain text_polish -> incident_dedup -> event judge + importance rescue. «نبض آموزش» card 19:00, 30-bank, no repeats. Daily boards: weather 07, cars 11, education 19.
   - Prefer cutting junk out of the text over refusing the whole post (refusals of the same story repeat every run: final-guard refusals are NOT remembered, only policy_scope / ai_unavailable blocks are).
   - Editorial blocks (policy_scope_blocked / ai_unavailable_foreign) are remembered 6 h (run_bot _EDITORIAL_BLOCK_TTL_SECONDS); the monitor then lists them as "important missed" with reason recent-editorial-block. Check items.json before calling it a miss.
2. NabzAI-YouTube (PRIVATE): channel "NABZ Mysteries" (@NabzMysteries) + Instagram «نبض معما».
   - Daily Short: cron-job.org 12:00 Tehran -> workflow_dispatch; src/mystery_short.py; published 22:30 Tehran; guard_today; a story never repeats. First comment: src/yt_comment.py via yt-comment.yml + cron-job.org 22:45 (owner pins it). Daily stats: src/yt_stats.py -> review/yt_stats.md (retention needs a refresh token with yt-analytics.readonly; today it reports invalid_scope).
   - Shorts ~30 s hook-first loops (the last beat may end open, e.g. «چون» / «:», so it loops into beat 1; by design). Hook beat <= 14 words, strangest fact first, dramatic first picture. Owner's 6-step template: contrast hook -> one question -> clue -> twist -> proven/probable/unknown -> ending reinterprets hook. Validate every story: 6-8 beats, 50-95 words.
   - Voice: Gemini 3.8 Flash TTS, voice Algenib, +1 semitone deeper, ONE take never spliced (audio_v 3), whisper-checked (src/voice_check.py). Only ONE key GEMINI_API_KEY (never add more).
   - Pronunciation: PRONOUNCE (mystery_short.py), FA_PRONOUNCE (reel_fa.py), review/pron_learned.json. Simple spoken language in all narration.
   - Music moods: src/music_mood.py (sea/crime/sky/ancient/vanish/cold), set one per new story.
   - Pictures: hfspace -> Cloudflare (CF_ACCOUNT_ID/CF_API_TOKEN, 10k free neurons/day) -> pollinations -> huggingface -> AI Horde. Instagram reel pictures: Nano Banana hook + FLUX.2 klein 768x1344 portrait (src/__init__.py, Oct 14). Max 6 reels built per day.
   - Instagram: NEVER unofficial posting. ig-pack.yml (cron 08:00/13:00/19:00 Tehran) = pack job (src/ig_pack.py, release week-YYYY-MM-DD, 15 reels/week from Oct 19, GOLDEN hours) + buffer job (src/ig_buffer.py, Buffer free API <= 10 queued, story teasers, films page). OWNER RULE: exactly ONE film reel a day, at noon; night = mystery. A rebuilt/replacement reel must never land on a day that already has a film reel (Oct 14: db-cooper rebuild at 17:20 made two film reels; owner unhappy). Slide posts src/ig_slides.py Tue/Thu/Sat ~17:00, no music.
   - Films page (nabz-reels /films/, from content/ig_films_fa.json): use the title people can find (international English title, original in brackets), e.g. hinterkaifeck = "مزرعه‌ی قتل" / The Murder Farm (Tannöd). Each card appears only when its reel's time has passed.
   - Story banks: content/mysteries.json (EN base, 51; 13 used by Oct 14), mysteries_add.json (extra EN, IG only), mysteries_fa.json (mysteries_fa_add.json is auto-merged into it and then deleted; recreate it for a new batch), only ids in story_notes_fa.json get planned, mysteries_override.json, ig_carousels*.json (later file overrides by id; a post needs caption + slides), ig_films_fa.json.
3. nabz-film: film site, updates every 6 h (data/status.json; scripts/build_catalog.py translates overviews with Groq, cache data/fa_ai.json). Missing Persian overviews 21 -> 11 -> 7 (Oct 14 15:26), no errors.
4. nabz-tools: https://nabzkhabarofficial.github.io/nabz-tools/ . rates.yml every 2 h (commits data/rates.json only when it changed) + cron-job.org backup job "nabz-tools" every 2 h at :17 (owner, Oct 14, verified: runs 14:52 and 18:17 Tehran). A karaoke tool + AI models were added on Oct 14 14:03-14:21 UTC (not by Brain); site validation still passes.

## Done on Oct 14
- NabzKhabar v13_final_guard.py: outlet spelling variants («اسکای نوز»), DETAIL lines naming an outlet dropped (lead kept), «صهیونی» -> «اسرائیلی», AI sense check: a name form is never a contradiction.
- NabzKhabar v13_chrome_scrub.py (evening): fararu's related-headline strip («از ماجرای ... تا ماجرای ...») is cut out by strip_teasers() instead of refusing the post (it had refused the Riyadh blasts and the IRGC spokesman again and again).
- NabzKhabar v13_ai_extra.py (evening): batch verdict echo check "h" (the FT Starlink story had been given a car-import story's verdict).
- Checked and NOT bugs (do not "fix"): post_design footer pulse (text_polish moves it); nabz-tools USDT converter (rialPer uses market.usdt first).
- NabzAI-YouTube: content/ig_carousels_4.json, 6 fact-checked slide posts: kaaba-zartosht (Oct 27), oxus-treasure (Oct 29), behistun (Oct 31), chogha-zanbil (Nov 3), marlik (Nov 5), shapur-cave (Nov 7). review/pron_learned.json: respellings for week 2026-10-19 names. ig_films_fa.json: hinterkaifeck title fixed.
- Plan checked: week Oct 15-18 and week 2026-10-19 have exactly one film reel per day at noon.

## Open work (as of Oct 14 2026, evening)
- Confirm the first NabzKhabar runs after the 15:19/15:21 UTC pushes are healthy (none had run by 15:23 UTC; last state commit 14:54 UTC). If the gap grows past 40 min, check bot.yml / cron-job.org.
- Confirm the 19:00 Tehran ig-pack run: next week's reels start building, the films page shows «مزرعه‌ی قتل».
- Retention data: the YouTube refresh token lacks yt-analytics.readonly. No token script in the repo; prepare simple step-by-step re-authorization for the owner before asking him.
- Check the first FLUX.2 klein reel pictures (oak-island Sat Oct 17 21:34, max-headroom Sun Oct 18).
- Persian bank: 53 FA stories not yet aired (to mid-November at 15/week); film share ~51% (target ~40%): next batch mostly non-film mysteries, with respellings + music mood.
- nabz-film: if 429 returns, cap per run + Retry-After backoff + failure cooldown in translate_overviews (build_catalog.py, 61 KB).
- Watch: AI pool runs low in the evening (10/18 models cooling at 18:24 Tehran, some stories blocked for no AI); final-guard refusals repeat every run for the same story (consider remembering them like editorial blocks); Mehrestan-style casualty updates skipped as duplicates; monitor counts retired models (cosmetic).

## Keep this file updated
After every important change, update this file (and the date at the top).
