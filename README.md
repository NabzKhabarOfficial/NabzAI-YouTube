# NabzAI-YouTube

English-first, free-first YouTube production pipeline for realistic AI-assisted cinematic short films and practical AI content.

## Current cinematic pipeline

- Six-shot live-action cinematic structure (24 seconds nominal).
- Photorealistic two-character reference image with identity anchoring.
- Explicit continuity for face, hair, age, body proportions and wardrobe.
- Real camera language: dolly, lateral movement, rack focus, push-in, arc and pull-back.
- Four spoken dialogue beats plus two silent visual breathing beats.
- English neural narration through Edge TTS.
- H.264/AAC final delivery at true 1280x720.
- Per-scene motion quality gate so static/slideshow-like shots fail before delivery.
- Automatic publish-ready thumbnail.
- YouTube metadata, thumbnail upload and synthetic-media disclosure support.
- Agnes first, then free Hugging Face video fallbacks.
- No paid service is required by the pipeline.

## Quality policy

A cinematic run is not considered ready merely because FFmpeg produced a file. The delivery gate requires:

1. six generated shots;
2. a valid character reference;
3. 24-second-class duration;
4. real temporal motion in every shot;
5. audio and video streams;
6. true 1280x720 output;
7. H.264/AAC delivery;
8. a generated thumbnail.

The actual generated artifact should still be reviewed before public release.

## YouTube publishing

Manual cinematic runs support three visibility choices:

- `public`
- `unlisted`
- `private`

Public/unlisted publishing requires the `YOUTUBE_TOKEN` GitHub Actions secret containing an authorized YouTube OAuth token JSON. The uploader also sends the generated thumbnail and marks the upload as synthetic/altered media.

Scheduled runs remain private when a YouTube token is configured, so an automatic schedule cannot unexpectedly publish a public video.

## Test locally

```bash
pip install -r requirements.txt
pip install -r requirements-cinematic.txt
python -m unittest discover -s tests -v
```

## Cost policy

No paid service is required by the current pipeline. Edge TTS is a network-based dependency and is not treated as a guaranteed unlimited commercial API. Any future paid service must be explicitly approved before integration.
