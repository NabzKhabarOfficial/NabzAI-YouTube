# NabzAI-YouTube

English-first, free-first YouTube production pipeline for practical AI, productivity and automation content.

## Pipeline
- Curated English topic bank with non-repeating state.
- Distinct script structures instead of one fixed template.
- English neural narration through Edge TTS.
- Six-scene 16:9 video rendering with FFmpeg.
- Professional 1280x720 thumbnail generation.
- Metadata and keyword generation.
- H.264/AAC decode, stream, duration and resolution quality gate.
- Optional 9:16 Shorts rendering.
- GitHub Actions scheduled preview build.
- YouTube upload remains disabled until OAuth is deliberately configured.

The automation is intended to remove repetitive production work, not to publish large batches of near-identical videos. Each topic has a different angle and examples, and the quality gate must pass before an output is treated as ready.

## Test
```bash
pip install -r requirements.txt
python -m src.main --mode test
```

## Cost policy
No paid service is required by the current pipeline. Edge TTS is a network-based dependency and is not treated as a guaranteed unlimited commercial API. Any future paid service must be explicitly approved before integration.

## Publishing
The repository currently generates previews only. Upload is intentionally off until the rendering workflow has produced a successful GitHub Actions artifact and the YouTube OAuth setup is separately configured.
