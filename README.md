# NabzAI-YouTube

Daily automated content for two channels, built from one fact-checked story bank.

## What it makes

- **NABZ Mysteries (YouTube Shorts, English)**: ~30-40 s hook-first vertical Shorts about real unsolved mysteries, uploaded and scheduled for 22:30 Tehran.
- **نبض معما (Instagram, Persian)**: Persian Reels (2 a day) and slide posts (3 a week), scheduled through the official Buffer API. No unofficial posting of any kind.

## Files

| Path | Role |
|---|---|
| `src/mystery_short.py` | Builds the English Short (story pick, voice, images, music, captions, title hook). |
| `src/youtube_uploader.py` | Uploads + schedules the Short with title, description, hashtags. |
| `src/yt_comment.py` | Posts the first comment on each Short. |
| `src/gemini_tts.py` | Narrator voice. |
| `src/voice_check.py` | Per-beat pronunciation check (never blocks). |
| `src/reel_fa.py` | Builds a Persian Reel, cover and caption from `content/mysteries_fa.json`. |
| `src/ig_pack.py` | Builds the weekly Instagram pack (GitHub release) using the full daily quota. |
| `src/ig_slides.py` + `src/carousel_fa.py` | Plans and renders slide posts from `content/ig_carousels*.json`. |
| `src/ig_buffer.py` | Schedules built Reels and slide posts in Buffer (max 10 queued). |
| `scripts/guard_today.py` | Skips later runs when today's Short is already built. |
| `scripts/review_short.py` | Post-build review report (timing, captions, bank stock warning at <=15). |
| `content/mysteries.json` | English story bank (fact-checked, never auto-generated). |
| `content/mysteries_fa.json` | Persian stories (fact-checked, never auto-generated). |
| `content/published.json` | Stories already used. |
| `tests/test_mystery.py` | Regression tests (run before every build). |

## Workflows

- `.github/workflows/youtube.yml`: daily build + upload, started by cron-job.org (workflow_dispatch, 12:00 Tehran).
- `.github/workflows/ig-pack.yml`: builds the Instagram pack and schedules it in Buffer.
- `.github/workflows/yt-comment.yml`: first comment on the day's Short.

## Secrets

YouTube: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`.
Voice: `GEMINI_API_KEY` (+ `_2`, `_3`).
Images: `HF_TOKEN`, `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `POLLINATIONS_TOKEN`.
Instagram via Buffer: `BUFFER_API_KEY`, `REELS_PAT`.

## Requirements

- `requirements.txt`: core build + YouTube upload.
- `requirements-cinematic.txt`: image-generation clients used by the Short builder (name is historical).
