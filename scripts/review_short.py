"""Create a small human-review bundle for the latest mystery Short."""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "mystery-short"
REVIEW = ROOT / "review"

def run(*args):
    return subprocess.run(list(args), capture_output=True, text=True, check=False)

def num(s):
    try: return float(s)
    except Exception: return None

def video_metrics(video: Path) -> dict:
    p = run("ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(video))
    if p.returncode != 0: return {"error": p.stderr[-500:]}
    data = json.loads(p.stdout or "{}")
    streams = data.get("streams", [])
    v = next((x for x in streams if x.get("codec_type") == "video"), {})
    a = next((x for x in streams if x.get("codec_type") == "audio"), {})
    duration = num((data.get("format") or {}).get("duration")) or num(v.get("duration")) or 0
    return {"duration_seconds": round(duration, 2), "resolution": f"{v.get('width', 0)}x{v.get('height', 0)}", "video_codec": v.get("codec_name", ""), "audio_codec": a.get("codec_name", ""), "fps": v.get("r_frame_rate", ""), "audio_sample_rate": a.get("sample_rate", ""), "file_mb": round(video.stat().st_size / 1048576, 2)}

def audio_metrics(video: Path) -> dict:
    p = run("ffmpeg", "-hide_banner", "-i", str(video), "-af", "volumedetect", "-f", "null", "-")
    out = {}
    for key in ("mean_volume", "max_volume"):
        line = next((x for x in (p.stderr or "").splitlines() if key in x), "")
        if line: out[key] = line.split(":", 1)[-1].strip()
    return out

def extract_frames(video: Path, duration: float) -> list[Path]:
    frames = []
    for i, pct in enumerate((0, 25, 50, 75, 100)):
        target = REVIEW / f"frame_{i}.jpg"
        if pct == 0:
            args = ("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-frames:v", "1", str(target))
        else:
            at = max(0, duration * pct / 100 - 0.05)
            args = ("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1", str(target))
        run(*args)
        if target.exists() and target.stat().st_size: frames.append(target)
    return frames

def contact_sheet(frames: list[Path]):
    tw, th = 270, 480
    canvas = Image.new("RGB", (tw * len(frames), th + 48), (18, 18, 24))
    d = ImageDraw.Draw(canvas)
    for i, path in enumerate(frames):
        im = Image.open(path).convert("RGB")
        im.thumbnail((tw, th - 12))
        canvas.paste(im, (i * tw + (tw - im.width) // 2, 4))
        d.text((i * tw + 8, th + 12), f"{i * 25}%", fill=(240, 220, 150))
    canvas.save(REVIEW / "contact-sheet.jpg", quality=84, optimize=True)

def main():
    video = OUT / "final_short.mp4"
    if not video.exists(): raise SystemExit("latest mystery video not found")
    REVIEW.mkdir(exist_ok=True)
    metrics = video_metrics(video)
    metrics["audio"] = audio_metrics(video)
    story_path = OUT / "story.json"
    story = json.loads(story_path.read_text(encoding="utf-8")) if story_path.exists() else {}
    transcript = "\n\n".join(b.get("text", "") for b in story.get("beats", []))
    (REVIEW / "transcript.txt").write_text(transcript + "\n", encoding="utf-8")
    duration = metrics.get("duration_seconds", 0)
    frames = extract_frames(video, duration)
    contact_sheet(frames)
    (REVIEW / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checks = [("duration", 18 <= duration <= 59.5, f"{duration:.1f}s"), ("vertical", metrics.get("resolution") == "1080x1920", metrics.get("resolution", "")), ("audio", bool(metrics.get("audio", {}).get("mean_volume")), metrics.get("audio", {}).get("mean_volume", "unknown")), ("frames", len(frames) == 5, f"{len(frames)}/5 frames")]
    verdict = "PASS" if all(x[1] for x in checks) else "CHECK"
    lines = [f"# NABZ Mysteries review: {story.get('title', 'latest')}", "", f"**Automatic verdict: {verdict}**", "", "Open `contact-sheet.jpg` for the visual check and `transcript.txt` for the narration.", "", "| Check | Result |", "|---|---|"]
    lines += [f"| {name} | {'PASS' if ok else 'CHECK'}: {value} |" for name, ok, value in checks]
    lines += ["", "## Audio", f"- Mean: `{metrics.get('audio', {}).get('mean_volume', 'unknown')}`", f"- Peak: `{metrics.get('audio', {}).get('max_volume', 'unknown')}`"]
    (REVIEW / "review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"review report: {verdict}, {len(frames)} frames, {duration:.1f}s")
if __name__ == "__main__": main()
