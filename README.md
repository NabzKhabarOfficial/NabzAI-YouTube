# NabzAI-YouTube

Daily automated content for two channels, built from one fact-checked story bank.

## What it makes

- **NABZ Mysteries (YouTube Shorts, English)**: ~30 s hook-first vertical Shorts about real unsolved mysteries, uploaded and scheduled for 22:30 Tehran.
- **نبض معما (Instagram Reels, Persian)**: the same story, hand-translated, rebuilt as a Persian Reel and posted 20:00-23:30 Tehran.

## Files

| Path | Role |
|---|---|
| `src/mystery_short.py` | Builds the English Short (story pick, voice, images, captions, title hook). |
| `src/youtube_uploader.py` | Uploads + schedules the Short with title, description, hashtags. |
| `src/reel_fa.py` | Builds the Persian Reel, cover and caption from `content/mysteries_fa.json`. |
| `src/ig_publish.py` | Posts one Reel per day (saved session only, 24 h safety pause on refusal). |
| `scripts/guard_today.py` | Skips backup cron runs when today's Short is already built. |
| `scripts/review_short.py` | Post-build review report (timing, captions, bank stock warning at <=15). |
| `content/mysteries.json` | English story bank (fact-checked, never auto-generated). |
| `content/mysteries_fa.json` | Persian translations (keep ahead of the English queue). |
| `content/published.json` | Stories already used. |
| `content/ig_state.json` | Instagram posting state. |
| `tests/test_mystery.py` | Regression tests (run before every build). |

## Workflows

- `.github/workflows/youtube.yml`: daily build + upload (crons 08:30, 10:15, 12:00, 14:00 UTC; guard skips once built), then builds the Persian Reel and force-pushes it to the `ig-queue` branch.
- `.github/workflows/instagram.yml`: evening crons, publishes the queued Reel.

## Secrets

YouTube: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN` (or `YOUTUBE_TOKEN`).
Images: `HF_TOKEN`, `POLLINATIONS_TOKEN`.
Instagram: `IG_USERNAME`, `IG_SESSION_B64`.

## Requirements

- `requirements.txt`: core build + YouTube upload.
- `requirements-cinematic.txt`: image-generation clients used by the Short builder (name is historical).
- `requirements-instagram.txt`: Instagram publishing.
