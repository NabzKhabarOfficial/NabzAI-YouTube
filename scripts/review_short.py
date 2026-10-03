"""Create a small private review bundle for the latest mystery Short.

Writes review/contact-sheet.jpg, review/transcript.txt, review/metrics.json and
review/review.md. Uses the ffmpeg binary bundled with imageio-ffmpeg (no system
ffprobe needed). It also reports how many mystery stories are left in the bank
and raises a workflow warning when 15 or fewer remain.
It NEVER fails the workflow: any error is reported and the script exits 0, so
the YouTube upload step always runs.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "mystery-short"
REVIEW = ROOT / "review"
BANK_ALERT_AT = 15


def ffmpeg_exe() -> str:
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


FF = ffmpeg_exe()


def run(*args):
    try:
        return subprocess.run([FF, "-hide_banner", *args], capture_output=True, text=True, timeout=180)
    except Exception as exc:  # binary missing, timeout, ...
        return subprocess.CompletedProcess(args, 1, "", str(exc))


def probe(video: Path) -> dict:
    text = run("-i", str(video)).stderr or ""
    info = {"duration_seconds": 0.0, "resolution": "", "video_codec": "", "audio_codec": "",
            "file_mb": round(video.stat().st_size / 1048576, 2)}
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", text)
    if m:
        info["duration_seconds"] = round(int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]), 2)
    m = re.search(r"Video: (\w+).*?(\d{3,4})x(\d{3,4})", text)
    if m:
        info["video_codec"], info["resolution"] = m[1], f"{m[2]}x{m[3]}"
    m = re.search(r"Audio: (\w+)", text)
    if m:
        info["audio_codec"] = m[1]
    return info


def audio_levels(video: Path) -> dict:
    text = run("-i", str(video), "-af", "volumedetect", "-f", "null", "-").stderr or ""
    out = {}
    for key in ("mean_volume", "max_volume"):
        m = re.search(key + r":\s*(-?[\d.]+) dB", text)
        if m:
            out[key] = float(m[1])
    return out


def frames(video: Path, duration: float) -> list[Path]:
    got = []
    for i, pct in enumerate((0, 25, 50, 75, 97)):
        target = REVIEW / f"frame_{i}.jpg"
        at = max(0.0, duration * pct / 100)
        run("-loglevel", "error", "-y", "-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1",
            "-vf", "scale=360:640", "-q:v", "4", str(target))
        if target.exists() and target.stat().st_size:
            got.append(target)
    return got


def contact_sheet(paths: list[Path]) -> None:
    from PIL import Image, ImageDraw
    if not paths:
        return
    tw, th = 360, 640
    sheet = Image.new("RGB", (tw * len(paths), th + 40), (18, 18, 24))
    d = ImageDraw.Draw(sheet)
    for i, p in enumerate(paths):
        sheet.paste(Image.open(p).convert("RGB").resize((tw, th)), (i * tw, 0))
        d.text((i * tw + 10, th + 12), ["start", "25%", "50%", "75%", "end"][i], fill=(240, 220, 150))
    sheet.save(REVIEW / "contact-sheet.jpg", quality=82, optimize=True)
    for p in paths:  # keep the repo light: only the sheet is committed
        p.unlink(missing_ok=True)


def bank_status() -> dict:
    """How many unpublished mystery stories are left in the bank."""
    bank = json.loads((ROOT / "content" / "mysteries.json").read_text(encoding="utf-8"))
    ids = [s["id"] for s in bank.get("stories", [])]
    pub_path = ROOT / "content" / "published.json"
    done = set()
    if pub_path.exists():
        done = set(json.loads(pub_path.read_text(encoding="utf-8")).get("mysteries", []))
    left = [i for i in ids if i not in done]
    return {"total": len(ids), "remaining": len(left), "next": left[:3], "low": len(left) <= BANK_ALERT_AT}


def report_bank() -> str:
    try:
        b = bank_status()
    except Exception as exc:
        print(f"::warning title=Story bank check skipped::{type(exc).__name__}: {exc}")
        return ""
    line = f"Story bank: {b['remaining']} of {b['total']} stories left (next: {', '.join(b['next'])})"
    print("review: " + line)
    if b["low"]:
        print(f"::warning title=Story bank low::Only {b['remaining']} mystery stories left. "
              "Add a new batch to content/mysteries.json.")
        line = "LOW: " + line
    return line


def build() -> None:
    bank_line = report_bank()
    video = OUT / "final_short.mp4"
    if not video.exists():
        print("review: no video to review")
        return
    REVIEW.mkdir(exist_ok=True)
    info = probe(video)
    info["audio"] = audio_levels(video)
    q = OUT / "quality.json"
    if q.exists():
        quality = json.loads(q.read_text(encoding="utf-8"))
        info["image_sources"] = quality.get("image_sources", [])
        info["quality_passed"] = quality.get("passed")
    story_path = OUT / "story.json"
    story = json.loads(story_path.read_text(encoding="utf-8")) if story_path.exists() else {}
    info["story_id"] = story.get("id", "")
    info["story_bank"] = bank_line
    (REVIEW / "transcript.txt").write_text(
        "\n".join(b.get("text", "") for b in story.get("beats", [])) + "\n", encoding="utf-8")
    contact_sheet(frames(video, info["duration_seconds"]))
    (REVIEW / "metrics.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dur, mean = info["duration_seconds"], info["audio"].get("mean_volume")
    checks = [
        ("duration 20-40s", 20 <= dur <= 40, f"{dur:.1f}s"),
        ("vertical 1080x1920", info["resolution"] == "1080x1920", info["resolution"]),
        ("audio not too quiet", mean is not None and mean > -22, f"{mean} dB"),
        ("no clipping", info["audio"].get("max_volume", 0) < 0, f"{info['audio'].get('max_volume')} dB"),
    ]
    lines = [f"# Review: {story.get('title', 'latest')}", "", "| Check | Result |", "|---|---|"]
    lines += [f"| {n} | {'OK' if ok else 'CHECK'} ({v}) |" for n, ok, v in checks]
    lines += ["", f"Images: {', '.join(info.get('image_sources', []))}", "", bank_line]
    (REVIEW / "review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("review: " + "; ".join(f"{n}={'OK' if ok else 'CHECK'}" for n, ok, _ in checks))


if __name__ == "__main__":
    try:
        build()
    except Exception as exc:
        print(f"::warning title=Review report skipped::{type(exc).__name__}: {exc}")
    sys.exit(0)
