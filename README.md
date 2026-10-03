# NabzAI-YouTube

English-first, free-first YouTube production pipeline. The main product is **NABZ Mysteries**: a daily vertical Short about a real unsolved mystery. A cinematic short-film mode is also available.

## NABZ Mysteries (default, daily)

`python -m src.mystery_short` builds one ~45 s vertical Short (1080x1920, 30 fps):

- Curated scripts in `content/mysteries.json` (7 beats, ~110-125 words each). Stories are used oldest-first and recorded in `content/published.json`.
- AI images per beat. Provider order: FLUX.1-schnell Hugging Face Space (free ZeroGPU quota), Pollinations (needs `POLLINATIONS_TOKEN`), Hugging Face Inference Providers.
- Edge TTS narration (`en-US-ChristopherNeural`) with word timings.
- Procedural dark ambient music with heartbeat, ducked under the voice.
- Ken Burns motion, crossfades, word-by-word captions with highlighted current word, red `UNSOLVED` badge for the first 3 s, subtle `NABZ MYSTERIES` watermark.
- Thumbnail, `metadata.json` (title + `#Shorts`), and a quality gate (resolution, duration, codecs, all images, captions).
- YouTube credentials are checked **before** any image is generated, so a bad token never wastes GPU quota.
- On failure, the reason is written to `output/mystery-short/error.txt` and shown as a GitHub Actions error annotation.

## Workflow

`.github/workflows/youtube.yml`

- Schedule: daily at 08:30 UTC (12:00 Tehran), mode `mystery`, always **private**.
- Manual run: choose `mode` (`mystery`, `cinematic`, `test`, `short`), `visibility`, and an optional `story_id`.
- Steps: fonts, dependencies, tests, build, upload, persist story state, upload artifacts for review.

### Secrets

| Secret | Purpose |
|---|---|
| `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN` | YouTube upload (OAuth, scope `youtube.upload`). The refresh token must be issued for the same client ID (OAuth Playground → "Use your own OAuth credentials"). |
| `HF_TOKEN` | Hugging Face Space / Inference images |
| `POLLINATIONS_TOKEN` | Backup image provider (secret `sk_` key, image-only, small budget) |
| `AGNES_API_KEY` | Cinematic mode video provider |
| `YOUTUBE_TOKEN` | Legacy single-JSON credential (still accepted) |

Uploads from an unaudited Google API project stay private; review each video in YouTube Studio and publish it yourself.

## Cinematic mode

`python -m src.cinematic_short`: six-shot 1280x720 live-action-style short with a character reference, four dialogue beats, per-scene motion gate, thumbnail, and synthetic-media disclosure. Agnes first, then free Hugging Face video fallbacks.

## Test locally

```bash
pip install -r requirements.txt
pip install -r requirements-cinematic.txt
python -m unittest discover -s tests -v
```

## Adding mysteries

Append to `content/mysteries.json`: unique `id`, `title` (≤ 60 chars), `tags`, and 6-8 `beats` each with `text` and `visual`. Total narration must be 95-150 words; the tests enforce this.

## Cost policy

No paid service is required. Free quotas (Hugging Face ZeroGPU, Pollinations budget) limit how many videos can be built per day; one per day fits comfortably.
