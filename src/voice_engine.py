import asyncio
from pathlib import Path
import edge_tts

async def _generate(text, output, voice, rate, volume):
    await edge_tts.Communicate(text, voice=voice, rate=rate, volume=volume).save(str(output))

def generate_voice(text, output_path, settings):
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(_generate(text, p, settings["voice"]["voice"], settings["voice"].get("rate", "+0%"), settings["voice"].get("volume", "+0%")))
    if not p.exists() or p.stat().st_size < 1024:
        raise RuntimeError("Voice generation failed.")
    return p
