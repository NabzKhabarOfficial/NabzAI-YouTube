# Brain handoff (NabzKhabarOfficial projects)

Read this whole file first, then continue the work. Updated: 2026-10-15 (18:20 Tehran).

## Important current change: Persian story bank
- `content/mysteries_fa.json` now contains all 77 Persian stories, preserved without ID loss.
- All 77 stories have entries in `content/story_notes_fa.json`, so the planner can use the complete bank.
- The 20 previously unrewritten Persian stories now use the owner's upgraded six-step retention arc: contrast hook, one question, concrete clue, twist, proven/probable/unknown boundary, and ending reinterpretation.
- The other unbuilt stories had their dry Beat 5 wording smoothed into natural spoken Persian while preserving the facts. Raw digits in the unbuilt spoken beats were replaced with Persian words for TTS.
- `review/pron_learned.json` now has 60 Persian pronunciation entries, including new names from the added rewrites: وینیچ, فلانان, تائوس, هرودوت, کرواتوان, سلست, ایسدال, گوبکلی‌تپه, دیاتلوف, تورنتو, والتز, ورنا, جویتا, والنتیچ and واراتا.
- Validation passed: all 77 FA entries match an English story ID, each has 6 beats, the rewritten/unbuilt beats have no Arabic digits, hooks are 14 words or fewer, and no joined verb-ending form `‌اند` or `‌است` remains in the changed beats.
- Existing queued/built reels were not rebuilt or rescheduled. Only future builds will use the improved scripts. Do not rebuild already queued reels unless the owner explicitly asks, because that would spend image and Gemini quota again.

## How to work with the owner (Younes)
- ALWAYS answer in Persian, short and clear. When he must do something by hand, give numbered step-by-step instructions (one action per step), never a dense summary; he asked "never confuse me".
- Free tools only, never break terms of service: no extra keys/projects/accounts to dodge quotas, nothing that needs a card.
- Push code yourself with GitHub tools; `.github/workflows` files are edited by the owner.
- Every check reads everything: code, logs, state and real recent posts/videos. Never claim to watch YouTube/Instagram when unavailable.
- Never invent facts. Fact-check stories and distinguish proven, probable and unknown.

## Repos
- `NabzKhabar`: Telegram news bot, Groq/Gemini/Mistral/OpenRouter pool, pace-aware quota handling, guard repair and no-source-name rules.
- `NabzAI-YouTube`: private YouTube Shorts + Instagram pack. Daily Shorts remain no-repeat; Instagram uses manual Meta scheduling only.
- `nabz-film`: catalog and public-domain film site.
- `nabz-tools`: public GitHub Pages utility site.

## Instagram schedule
- One film reel at the first daily slot, mystery reels later. Golden hours begin week `2026-10-19`; already planned weeks keep their times.
- Week `2026-10-19` is partially built and continues from state. Week `2026-10-26` is preplanned, not built yet.
- Never use unofficial Instagram posting or click bots.

## Keep this file updated
After every important change, update this file and the date at the top.
