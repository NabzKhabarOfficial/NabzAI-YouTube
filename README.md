NabzAI-YouTube

Automated Persian educational YouTube video pipeline.

The base pipeline is free-first and does not require paid services. It creates an original Persian lesson, narration, a video preview and a thumbnail, then runs quality checks. YouTube upload stays disabled until OAuth is configured.

Run locally: pip install -r requirements.txt && python -m src.main --mode test

The workflow is intentionally dry-run first. This protects the channel while the rendering pipeline is validated.