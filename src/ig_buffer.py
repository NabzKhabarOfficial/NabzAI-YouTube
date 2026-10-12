"""Hands the finished «نبض معما» reels to Buffer, which publishes them on Instagram through
Meta's official API. Nothing here logs in to Instagram, and the owner uploads nothing.

Every run:
 1. reads content/ig_pack_state.json and takes the reels that are built but not yet sent;
 2. puts the videos of every reel that is still waiting in Buffer on the public site of the
    repo nabz-reels (GitHub Pages; one fresh commit, so the repo never grows);
 3. creates one Buffer post per reel (Instagram Reel, exact Tehran time from the pack, caption +
    hashtags), never more than Buffer's free queue of 10 scheduled posts;
 4. records everything in content/ig_buffer_state.json.

A reel whose time already passed before it could be sent gets the next free slot (13:00-14:10 or
20:30-22:40 Tehran, never closer than 3 hours to another reel). The free plan's limits: 10 posts
waiting at a time (refilled as they go out) and 3,000 API calls a month (a run uses ~5).

Safety (Oct 10 2026):
 * STOP switch: while a file named STOP exists in the repo root, nothing new is sent to Buffer
   (reels already waiting there go out unless the owner presses "Pause queue" in Buffer).
 * Three failed runs in a row (Buffer refused / unreachable / videos not public) send the owner
   a Telegram message (TELEGRAM_BOT_TOKEN; the chat is found from the owner's /start).
Captions are built fresh from the story bank (+ content/ig_captions_fa.json overrides) when a
reel is sent; a waiting post whose caption changed is replaced in Buffer (same time, same video).
True stories that became films (content/ig_films_fa.json) get a "comment «فیلم»" line; Zaprep
DMs the films page (nabz-reels Pages /films/, rebuilt here; a reel's film shows up at its time).
Stats: once a day the metrics of sent reels (views, reach, likes, comments, saves, shares,
follows) are read from Buffer into content/ig_stats.json; every Monday a short report
(review/ig_weekly.md) ranks last week's reels and is sent to the owner on Telegram.

Slide posts (Oct 11 2026, src.ig_slides): three photo carousels a week (Tue/Thu/Sat ~17:00
Tehran) go the same way: their slides are put on the public site (v/c_<id>_<n>.jpg) and one Buffer
post per carousel is created. Reels and slide posts share Buffer's queue, nearest time first.

Secrets: BUFFER_API_KEY (Buffer, Settings > API) and REELS_PAT (fine-grained token, repo
nabz-reels, Contents read/write). GH_TOKEN reads the private pack release.
"""
from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
import time
import hashlib
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK_STATE = ROOT / "content" / "ig_pack_state.json"
STATE_FILE = ROOT / "content" / "ig_buffer_state.json"
WORK = ROOT / "output" / "ig-buffer"
TEHRAN = timezone(timedelta(hours=3, minutes=30))
REPO = os.getenv("GITHUB_REPOSITORY", "NabzKhabarOfficial/NabzAI-YouTube")
SITE_REPO = os.getenv("NABZ_REELS_REPO", "NabzKhabarOfficial/nabz-reels")
SITE_URL = os.getenv("NABZ_REELS_URL", "https://nabzkhabarofficial.github.io/nabz-reels")
API = "https://api.buffer.com"
QUEUE_MAX = int(os.getenv("NABZ_BUFFER_QUEUE_MAX", "10"))  # Buffer Free: 10 waiting posts
LEAD_MIN = 30  # a post is created at least this long before its time
STUCK_MIN = 20  # a post still in the Buffer queue this long after its time did not publish
MAX_NEW = int(os.getenv("NABZ_BUFFER_MAX_NEW", "10"))  # NABZ_BUFFER_MAX_NEW=1 for a first test
SLOTS = [(13 * 60, 14 * 60 + 10), (20 * 60 + 30, 22 * 60 + 40)]
GAP_MIN = 180
STOP_FILE = ROOT / "STOP"
CAPTIONS = ROOT / "content" / "ig_captions_fa.json"
FILMS = ROOT / "content" / "ig_films_fa.json"
FILM_CTA = "🎬 از این ماجرای واقعی فیلم ساختن! اسمش رو می‌خوای؟ کامنت بذار «فیلم» تا برات دایرکت بشه 👇"
FA_BANK = ROOT / "content" / "mysteries_fa.json"
STATS_FILE = ROOT / "content" / "ig_stats.json"
REPORT_MD = ROOT / "review" / "ig_weekly.md"
FAIL_ALERT = 3
PUSH_TRIES = 4  # GitHub now and then refuses a push for a moment ("fatal error in commit_refs", Oct 12 2026)


def log(msg: str) -> None:
    print(f"[ig-buffer] {msg}", flush=True)


def warn(title: str, msg: str) -> None:
    print(f"::warning title={title}::{msg}", flush=True)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- Buffer API
class BufferError(RuntimeError):
    pass


def gql(query: str, variables: dict | None = None) -> dict:
    key = os.getenv("BUFFER_API_KEY", "").strip()
    if not key:
        raise BufferError("BUFFER_API_KEY secret is missing")
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    for attempt in range(3):
        req = urllib.request.Request(API, data=body, method="POST", headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {key}",
            "User-Agent": "nabz-reels/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            text = exc.read().decode(errors="replace")[:400]
            if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(20 * (attempt + 1))
                continue
            raise BufferError(f"HTTP {exc.code}: {text}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt < 2:
                time.sleep(15)
                continue
            raise BufferError(f"network: {exc}") from None
        if data.get("errors"):
            raise BufferError("; ".join(str(e.get("message", e)) for e in data["errors"])[:500])
        return data.get("data") or {}
    raise BufferError("no answer")


def find_channel(state: dict) -> tuple[str, str]:
    if state.get("channel_id") and state.get("org_id"):
        return state["org_id"], state["channel_id"]
    orgs = gql("query { account { organizations { id name } } }")["account"]["organizations"]
    for org in orgs:
        chans = gql('query { channels(input: {organizationId: %s}) { id name service } }'
                    % json.dumps(org["id"]))["channels"]
        for ch in chans:
            if str(ch.get("service", "")).lower() == "instagram":
                state["org_id"], state["channel_id"], state["channel_name"] = org["id"], ch["id"], ch.get("name")
                log(f"Instagram channel in Buffer: {ch.get('name')}")
                return org["id"], ch["id"]
    raise BufferError("no Instagram channel is connected in Buffer")


def scheduled_posts(org: str, channel: str) -> list[dict]:
    q = """query { posts(first: 50, input: {organizationId: %s, filter: {status: [scheduled], channelIds: [%s]}}) {
        edges { node { id dueAt } } } }""" % (json.dumps(org), json.dumps(channel))
    return [e["node"] for e in gql(q)["posts"]["edges"]]


def post_status(org: str, channel: str, status: str) -> set:
    q = """query { posts(first: 50, input: {organizationId: %s, filter: {status: [%s], channelIds: [%s]}}) {
        edges { node { id } } } }""" % (json.dumps(org), status, json.dumps(channel))
    try:
        return {e["node"]["id"] for e in gql(q)["posts"]["edges"]}
    except BufferError as exc:
        log(f"could not read {status} posts: {exc}")
        return set()


CREATE = """mutation($input: CreatePostInput!) { createPost(input: $input) {
  ... on PostActionSuccess { post { id dueAt } }
  ... on MutationError { message } } }"""


def create_post(channel: str, text: str, video_url: str, due: datetime) -> dict:
    ig = {"type": "reel", "shouldShareToFeed": True, "isAiGenerated": True}
    video = {"url": video_url, "metadata": {"thumbnailOffset": 0}}
    base = {"text": text, "channelId": channel, "schedulingType": "automatic", "mode": "customScheduled",
            "dueAt": due.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")}
    # Optional extras are dropped one by one if this account/plan refuses them.
    tries = [(True, True), (False, True), (True, False), (False, False)]
    last = ""
    for ai, thumb in tries:
        meta = dict(ig) if ai else {k: v for k, v in ig.items() if k != "isAiGenerated"}
        asset = video if thumb else {"url": video_url}
        payload = dict(base, assets=[{"video": asset}], metadata={"instagram": meta})
        try:
            res = gql(CREATE, {"input": payload})["createPost"]
        except BufferError as exc:
            last = str(exc)
            if any(w in last for w in ("isAiGenerated", "thumbnailOffset", "metadata", "not defined", "Unknown")):
                continue
            raise
        if res.get("post"):
            return res["post"]
        last = res.get("message") or "unknown error"
        low = last.lower()
        if "limit" in low:
            raise BufferError(f"LIMIT: {last}")
        if not any(w in low for w in ("thumbnail", "ai", "cover")):
            break
    raise BufferError(last)


def create_carousel(channel: str, text: str, image_urls: list[str], due: datetime) -> dict:
    """An Instagram photo carousel (2-10 slides, 4:5). The slides are drawn text, not AI pictures."""
    payload = {"text": text, "channelId": channel, "schedulingType": "automatic", "mode": "customScheduled",
               "dueAt": due.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
               "assets": [{"image": {"url": u}} for u in image_urls],
               "metadata": {"instagram": {"type": "post", "shouldShareToFeed": True}}}
    res = gql(CREATE, {"input": payload})["createPost"]
    if res.get("post"):
        return res["post"]
    last = res.get("message") or "unknown error"
    if "limit" in last.lower():
        raise BufferError(f"LIMIT: {last}")
    raise BufferError(last)


# ---------------------------------------------------------------- the pack
def gh(*args, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args, "--repo", REPO], capture_output=True, text=True, check=check)


def stem(item: dict) -> str:
    """File name of a reel in the release. A plan item may name an already finished video
    ("file"), e.g. a reel moved to a new time without building it again (Oct 12 2026)."""
    if item.get("file"):
        return str(item["file"])
    return f"{item['n']:02d}_{item['date']}_{item['time'].replace(':', '')}_{item['id']}"


def built_reels() -> list[dict]:
    pack = load_json(PACK_STATE, {})
    out = []
    for week, info in sorted((pack.get("weeks") or {}).items()):
        built = info.get("built") or {}
        for item in info.get("plan") or []:
            if item["id"] in built:
                out.append(dict(item, week=week, stem=stem(item), tag=f"week-{week}",
                                audio_v=int((built[item["id"]] or {}).get("audio_v", 1))))
    return out


def built_carousels() -> list[dict]:
    """Planned slide posts whose slides are drawn (src.ig_slides), as queue items like the reels."""
    from src import ig_slides
    items = ((load_json(PACK_STATE, {}).get("carousels") or {}).get("plan")) or []
    return [dict(p, kind="carousel", stem=f"car_{p['id']}", tag=ig_slides.RELEASE)
            for p in items if p.get("slides")]


def slide_files(item: dict) -> list[Path]:
    from src import ig_slides
    folder = WORK / item["tag"]
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for k in range(1, int(item["slides"]) + 1):
        path = folder / ig_slides.file_name(item["id"], k)
        if not path.exists():
            gh("release", "download", item["tag"], "--dir", str(folder), "--pattern", path.name, "--skip-existing")
        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError(f"{path.name} is not in release {item['tag']}")
        out.append(path)
    return out


def item_files(item: dict) -> list[Path]:
    return slide_files(item) if item.get("kind") == "carousel" else [fetch(item, ".mp4")]


def carousel_caption(item: dict) -> str:
    from src import ig_slides
    post = ig_slides.posts_by_id().get(item["id"])
    if not post:
        raise RuntimeError(f"slide post {item['id']} is not in content/ig_carousels*.json")
    return str(post["caption"]).strip()


def fetch(reel: dict, kind: str) -> Path:
    folder = WORK / reel["tag"]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{reel['stem']}{kind}"
    if not path.exists():
        gh("release", "download", reel["tag"], "--dir", str(folder), "--pattern", path.name, "--skip-existing")
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"{path.name} is not in release {reel['tag']}")
    return path


def due_of(reel: dict) -> datetime:
    return datetime.fromisoformat(f"{reel['date']}T{reel['time']}:00").replace(tzinfo=TEHRAN)


def next_free_slot(taken: list[datetime], after: datetime, seed: str) -> datetime:
    rng = random.Random(seed)
    day = after.astimezone(TEHRAN).date()
    for _ in range(30):
        for lo, hi in SLOTS:
            t = datetime.combine(day, datetime.min.time(), TEHRAN) + timedelta(minutes=rng.randint(lo, hi))
            if t < after:
                continue
            if all(abs((t - x).total_seconds()) >= GAP_MIN * 60 for x in taken):
                return t
        day += timedelta(days=1)
    raise RuntimeError("no free slot in the next 30 days")


def next_carousel_slot(taken: list[datetime], due: datetime, after: datetime) -> datetime:
    """Same time on a following day, at least 2 hours from any other post."""
    t = due
    for _ in range(30):
        if t >= after and all(abs((t - x).total_seconds()) >= 120 * 60 for x in taken):
            return t
        t += timedelta(days=1)
    raise RuntimeError("no free slot for a slide post in the next 30 days")


# ---------------------------------------------------------------- public video site
def publish_site(files: list[Path], films_html: str = "", covers: dict | None = None) -> None:
    pat = os.getenv("REELS_PAT", "").strip()
    if not pat:
        raise RuntimeError("REELS_PAT secret is missing")
    site = WORK / "site"
    shutil.rmtree(site, ignore_errors=True)
    (site / "v").mkdir(parents=True)
    for f in files:
        shutil.copy2(f, site / "v" / f.name)
    (site / ".nojekyll").write_text("")
    (site / "README.md").write_text("Public video files for «نبض معما» reels, scheduled in Buffer. "
                                    "Rebuilt automatically; old videos are removed after they are posted.\n",
                                    encoding="utf-8")
    (site / "index.html").write_text("<!doctype html><meta charset=utf-8><title>nabz-reels</title>ok\n")
    if films_html:
        (site / "films").mkdir()
        (site / "films" / "index.html").write_text(films_html, encoding="utf-8")
        if covers:
            (site / "films" / "c").mkdir()
            for sid, path in covers.items():
                shutil.copy2(path, site / "films" / "c" / f"{sid}.jpg")
    env = dict(os.environ, GIT_AUTHOR_NAME="github-actions[bot]", GIT_COMMITTER_NAME="github-actions[bot]",
               GIT_AUTHOR_EMAIL="41898282+github-actions[bot]@users.noreply.github.com",
               GIT_COMMITTER_EMAIL="41898282+github-actions[bot]@users.noreply.github.com")
    run = lambda *a: subprocess.run(list(a), cwd=site, env=env, check=True, capture_output=True, text=True)
    run("git", "init", "-q", "-b", "main")
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", f"reels on {now_utc():%Y-%m-%d %H:%M} UTC")
    url = f"https://x-access-token:{pat}@github.com/{SITE_REPO}.git"
    err = ""
    for attempt in range(PUSH_TRIES):
        proc = subprocess.run(["git", "push", "-q", "--force", url, "main:main"], cwd=site, env=env,
                              capture_output=True, text=True)
        if proc.returncode == 0:
            if attempt:
                log(f"push to nabz-reels worked on try {attempt + 1}")
            return
        err = proc.stderr.replace(pat, "***")[:300]
        log(f"push to nabz-reels failed (try {attempt + 1}/{PUSH_TRIES}): {err[:200]}")
        if attempt < PUSH_TRIES - 1:
            time.sleep(30 * (attempt + 1))
    raise RuntimeError("push to nabz-reels failed: " + err)


def url_ready(url: str, size: int) -> bool:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "nabz-reels/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status == 200 and int(resp.headers.get("Content-Length", "0") or 0) == size
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


def wait_public(urls: dict[str, int], minutes: int = 12) -> bool:
    end = time.time() + minutes * 60
    while time.time() < end:
        if all(url_ready(u, s) for u, s in urls.items()):
            return True
        time.sleep(20)
    return False



# ---------------------------------------------------------------- captions
def caption_for(reel: dict) -> str:
    """Caption + hashtags from the bank, with the owner's question overrides."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("ig_pack_light", ROOT / "src" / "ig_pack.py")
    pack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pack)
    fa = dict((load_json(FA_BANK, {}).get("stories") or {}).get(reel["id"]) or {})
    if not fa.get("title"):
        raise RuntimeError(f"{reel['id']} is not in the Persian bank")
    q = (load_json(CAPTIONS, {}).get("questions") or {}).get(reel["id"])
    if q:
        fa["question"] = q
    text = pack.caption(fa)
    if reel["id"] in (load_json(FILMS, {}).get("films") or {}):
        title, _, rest = text.partition("\n\n")
        text = f"{title}\n\n{FILM_CTA}\n\n{rest}"
    return text + "\n\n" + " ".join(pack.hashtags(fa, reel["n"]))


FILMS_SHOWN = 15  # newest film reels on the page (keeps it light on slow connections)
FILMS_CSS = """
@font-face{font-family:V;src:url(https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/fonts/webfonts/Vazirmatn[wght].woff2) format('woff2');font-weight:100 900;font-display:swap}
*{box-sizing:border-box}
body{margin:0;font-family:V,Tahoma,sans-serif;color:#f3eee6;background:#07070b;min-height:100vh;
 background-image:radial-gradient(circle at 15% -10%,rgba(200,16,32,.35),transparent 45%),radial-gradient(circle at 110% 30%,rgba(205,155,58,.18),transparent 40%)}
.top{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:10px;padding:12px 16px;
 background:rgba(7,7,11,.72);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);border-bottom:1px solid rgba(255,255,255,.07)}
.logo{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;font-weight:900;font-size:22px;color:#ffe9b8;
 background:radial-gradient(circle at 35% 30%,#e3283a,#7a0b14);box-shadow:0 0 18px rgba(227,40,58,.6)}
.top b{font-size:17px}.top a{margin-right:auto;text-decoration:none;color:#111;background:linear-gradient(90deg,#ffd27a,#f0a93a);
 padding:8px 14px;border-radius:999px;font-weight:800;font-size:13px}
.hero{padding:30px 18px 8px;text-align:center}
.strip{height:14px;margin:0 auto 18px;max-width:340px;border-radius:3px;
 background:repeating-linear-gradient(90deg,#222 0 14px,#07070b 14px 22px);opacity:.9}
h1{margin:0;font-size:27px;line-height:1.5;font-weight:900;color:#ffe1a0;text-shadow:0 0 24px rgba(255,90,106,.35)}
@supports ((-webkit-background-clip:text) or (background-clip:text)){h1{background:linear-gradient(90deg,#fff,#ffd27a,#ff5a6a,#fff);
 background-size:300%;-webkit-background-clip:text;background-clip:text;color:transparent;-webkit-text-fill-color:transparent;animation:sh 7s linear infinite}}
@keyframes sh{to{background-position:300%}}
.sub{color:#b9b2a7;font-size:14px;margin:10px 0 0}
.grid{display:grid;gap:18px;padding:22px 16px 10px;max-width:980px;margin:auto;grid-template-columns:repeat(auto-fill,minmax(270px,1fr))}
.card{position:relative;border-radius:22px;overflow:hidden;aspect-ratio:4/5;background:linear-gradient(160deg,#2a0a10,#0d0d14 60%);
 box-shadow:0 18px 40px rgba(0,0,0,.55),inset 0 0 0 1px rgba(255,255,255,.08);opacity:0;transform:translateY(24px);animation:in .7s ease forwards}
@keyframes in{to{opacity:1;transform:none}}
.card img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;transform:scale(1.06);transition:transform 6s ease}
.card:hover img{transform:scale(1.14)}
.card:after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.15) 0%,rgba(0,0,0,.25) 35%,rgba(5,5,9,.96) 78%)}
.in{position:absolute;inset:auto 0 0 0;z-index:2;padding:18px}
.tag{position:absolute;z-index:3;top:14px;right:14px;font-size:12px;font-weight:800;padding:6px 11px;border-radius:999px;
 background:rgba(200,16,32,.92);box-shadow:0 0 14px rgba(200,16,32,.6)}
.new{position:absolute;z-index:3;top:14px;left:14px;font-size:12px;font-weight:900;padding:6px 11px;border-radius:999px;color:#111;
 background:#ffd27a;animation:pu 1.6s ease-in-out infinite;display:none}
.card.first .new{display:block}
@keyframes pu{50%{box-shadow:0 0 0 8px rgba(255,210,122,0)}0%{box-shadow:0 0 0 0 rgba(255,210,122,.7)}}
.s{margin:0 0 8px;color:#d8cfc2;font-size:13px}
.f{margin:0;font-size:25px;font-weight:900;line-height:1.35;text-shadow:0 2px 12px rgba(0,0,0,.8)}
.e{margin:6px 0 0;color:#ffd27a;font-size:14px;direction:ltr;text-align:right;font-weight:600}
.b{margin:8px 0 0;color:#cfc8bd;font-size:13px}
.h{margin:10px 0 0;font-size:13px;color:#f3eee6;background:rgba(255,255,255,.08);border-right:3px solid #e3283a;padding:8px 10px;border-radius:8px}
.empty{grid-column:1/-1;text-align:center;color:#b9b2a7;padding:60px 0}
.foot{text-align:center;padding:26px 16px 40px;color:#b9b2a7;font-size:13px}
.foot a{display:inline-block;margin-top:12px;text-decoration:none;color:#fff;font-weight:800;padding:12px 22px;border-radius:999px;
 background:linear-gradient(90deg,#c8102e,#e3283a);box-shadow:0 8px 24px rgba(200,16,46,.45)}
"""


def films_page(state: dict) -> str:
    """The page the comment-to-DM tool links: newest published film reel first, as cinematic cards
    with the reel's own cover (our AI picture, no film posters). Covers live in films/c/<id>.jpg."""
    import html
    films = load_json(FILMS, {}).get("films") or {}
    bank = load_json(FA_BANK, {}).get("stories") or {}
    rows = []
    for key, rec in state.get("sent", {}).items():
        sid = key.split("_", 3)[-1]
        if sid in films and rec.get("status") in ("scheduled", "sent"):
            rows.append((datetime.fromisoformat(rec["due"]), sid))  # future ones are hidden until their time
    rows.sort(reverse=True)
    cards = []
    for k, (due, sid) in enumerate(rows[:FILMS_SHOWN + 3]):
        f = films[sid]
        how = f"<p class=h>💡 {html.escape(f['how'])}</p>" if f.get("how") else ""
        by = f"<p class=b>🎥 کارگردان: {html.escape(f['by'])}</p>" if f.get("by") else ""
        cards.append(
            f"<article class=card data-due='{int(due.timestamp() * 1000)}' style='animation-delay:{0.08 * k:.2f}s'>"
            f"<img src='c/{html.escape(sid)}.jpg' alt='' loading=lazy onerror=\"this.remove()\">"
            "<span class=tag>ماجرای واقعی</span><span class=new>جدید</span>"
            f"<div class=in><p class=s>📍 ریلز: {html.escape((bank.get(sid) or {}).get('title', sid))}</p>"
            f"<p class=f>🎬 {html.escape(f['fa'])}</p>"
            f"<p class=e>{html.escape(f['en'])} · {f['year']}</p>{by}{how}</div></article>")
    body = "".join(cards) + "<p class=empty>🎞 به‌زودی اولین فیلم اینجاست...</p>"
    return ("<!doctype html><html lang=fa dir=rtl><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1,viewport-fit=cover'>"
            "<meta name=theme-color content='#07070b'><title>🎬 فیلم‌های نبض معما</title>"
            "<meta property=og:title content='فیلم‌هایی که از ماجراهای واقعی ساخته شدن'>"
            f"<style>{FILMS_CSS}</style></head><body>"
            "<header class=top><span class=logo>؟</span><b>نبض معما</b>"
            "<a href='https://www.instagram.com/nabz.moamma/'>+ فالو</a></header>"
            "<section class=hero><div class=strip></div><h1>فیلم‌هایی که از ماجراهای واقعی ساخته شدن</h1>"
            "<p class=sub>جدیدترین ریلز همیشه اول صفحه‌ست 👇</p></section>"
            f"<main class=grid>{body}</main>"
            "<footer class=foot>هر روز ظهر یه ماجرای واقعی که فیلم شده، هر شب یه معمای حل‌نشده.<br>"
            "<a href='https://www.instagram.com/nabz.moamma/'>📲 فالو کن @nabz.moamma</a></footer>"
            "<script>var n=Date.now(),c=document.querySelectorAll('.card'),k=0;c.forEach(function(e){"
            f"if(+e.dataset.due>n||k>={FILMS_SHOWN})e.remove();else{{if(!k)e.classList.add('first');k++}}}});"
            "if(k)document.querySelector('.empty').remove();</script></body></html>")


def small_cover(path: Path) -> Path:
    """A light copy of a reel cover for the films page (540 px wide); the original if no tool works."""
    out = path.with_name(path.stem + "_web.jpg")
    if out.exists():
        return out
    for cmd in (["convert", str(path), "-resize", "540x", "-quality", "78", str(out)],
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-vf", "scale=540:-2", "-q:v", "5", str(out)]):
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
            if out.exists() and out.stat().st_size > 1000:
                return out
        except (OSError, subprocess.SubprocessError):
            continue
    return path


def film_covers(state: dict) -> dict[str, Path]:
    """Cover pictures of the film reels on the page, from the weekly releases."""
    films = load_json(FILMS, {}).get("films") or {}
    by_stem = {r["stem"]: r for r in built_reels()}
    out = {}
    for key, rec in state.get("sent", {}).items():
        sid = key.split("_", 3)[-1]
        if sid in films and rec.get("status") in ("scheduled", "sent") and key in by_stem:
            try:
                out[sid] = small_cover(fetch(by_stem[key], "_cover.jpg"))
            except Exception as exc:  # the page still works, the card just has no picture
                log(f"cover of {sid} not available: {type(exc).__name__}: {str(exc)[:160]}")
    return out


def text_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


DELETE = """mutation($input: DeletePostInput!) { deletePost(input: $input) { __typename
  ... on MutationError { message } } }"""


def delete_post(post_id: str) -> None:
    res = gql(DELETE, {"input": {"id": post_id}})["deletePost"]
    if res.get("message"):
        raise BufferError(res["message"])


# ---------------------------------------------------------------- telegram
def telegram(state: dict, text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        log("no TELEGRAM_BOT_TOKEN: owner message not sent")
        return False
    base = f"https://api.telegram.org/bot{token}"
    chat = os.getenv("TELEGRAM_OWNER_CHAT", "").strip() or str(state.get("owner_chat") or "")
    if not chat:  # the owner sent /start to the bot once: take his private chat from the updates
        try:
            with urllib.request.urlopen(f"{base}/getUpdates?limit=100", timeout=30) as resp:
                ups = json.loads(resp.read().decode()).get("result", [])
            for u in reversed(ups):
                c = ((u.get("message") or {}).get("chat") or {})
                if c.get("type") == "private":
                    chat = str(c["id"])
                    state["owner_chat"] = chat
                    break
        except Exception as exc:
            log(f"telegram getUpdates failed ({type(exc).__name__})")
    if not chat:
        log("owner chat unknown: send /start to the bot once")
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000]}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{base}/sendMessage", data=data), timeout=30):
            return True
    except Exception as exc:
        log(f"telegram send failed ({type(exc).__name__})")
        return False


def note_run(state: dict, ok: bool, why: str = "") -> None:
    """Count failed runs in a row; on the third one, tell the owner (once per streak)."""
    if ok:
        state["fail_streak"], state["fail_alerted"] = 0, False
        return
    state["fail_streak"] = int(state.get("fail_streak", 0)) + 1
    state["last_fail"] = why[:300]
    if state["fail_streak"] >= FAIL_ALERT and not state.get("fail_alerted"):
        msg = (f"⚠️ نبض معما: ارسال ریلز به Buffer {state['fail_streak']} بار پشت هم خطا داد.\n"
               f"آخرین خطا: {why[:300]}\nتا وقتی درست نشه ریلز جدید به صف نمی‌ره (ریلزهای داخل صف سر جاشونن).")
        state["fail_alerted"] = telegram(state, msg)


# ---------------------------------------------------------------- stats + weekly report
METRICS_Q = """query { post(input: {id: %s}) { id metrics { type value } metricsUpdatedAt } }"""
KEYS = ("views", "reach", "impressions", "reactions", "comments", "saves", "shares", "follows")


def collect_stats(state: dict) -> None:
    """Once a day: metrics of reels sent at least 24 h ago (kept for 14 days)."""
    stats = load_json(STATS_FILE, {"posts": {}})
    today = datetime.now(TEHRAN).date().isoformat()
    if stats.get("collected") == today:
        return
    now = now_utc()
    for key, rec in state.get("sent", {}).items():
        due = datetime.fromisoformat(rec["due"])
        if rec.get("status") != "sent" or not now - timedelta(days=14) < due < now - timedelta(hours=24):
            continue
        try:
            post = gql(METRICS_Q % json.dumps(rec["post_id"]))["post"]
        except BufferError as exc:
            log(f"metrics for {key} not read ({str(exc)[:120]})")
            continue
        vals = {m["type"]: m["value"] for m in post.get("metrics") or []}
        if vals:
            stats["posts"][key] = {"due": rec["due"], **{k: vals[k] for k in vals if k in KEYS},
                                   "updated": post.get("metricsUpdatedAt")}
    stats["collected"] = today
    STATS_FILE.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def weekly_report(state: dict) -> None:
    """Mondays (Tehran): rank last week's reels and send the owner a short summary."""
    now = datetime.now(TEHRAN)
    week = (now.date() - timedelta(days=now.weekday())).isoformat()
    if now.weekday() != 0 or state.get("report_week") == week:
        return
    stats = load_json(STATS_FILE, {"posts": {}}).get("posts", {})
    start = datetime.fromisoformat(week + "T00:00:00+03:30") - timedelta(days=7)
    rows = [(k, v) for k, v in stats.items() if start <= datetime.fromisoformat(v["due"]) < start + timedelta(days=7)]
    if not rows:
        state["report_week"] = week
        return
    bank = load_json(FA_BANK, {}).get("stories") or {}

    def score(v):  # shares and saves weigh most: they are what spreads a page
        return v.get("views", v.get("reach", 0)) + 30 * v.get("shares", 0) + 20 * v.get("saves", 0) + 10 * v.get("comments", 0)

    rows.sort(key=lambda kv: score(kv[1]), reverse=True)
    lines = [f"# گزارش هفتگی نبض معما ({start.date()} تا {(start + timedelta(days=6)).date()})", "",
             "| ریلز | بازدید | لایک | کامنت | ذخیره | اشتراک | فالو |", "|---|---|---|---|---|---|---|"]
    def title_of(k):
        if k.startswith("car_"):
            return "🖼 " + k[4:]
        sid = k.split("_", 3)[-1]
        return (bank.get(sid) or {}).get("title", sid)

    for k, v in rows:
        title = title_of(k)
        lines.append(f"| {title} | {int(v.get('views', v.get('reach', 0)))} | {int(v.get('reactions', 0))} | "
                     f"{int(v.get('comments', 0))} | {int(v.get('saves', 0))} | {int(v.get('shares', 0))} | {int(v.get('follows', 0))} |")
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    best = [title_of(k) for k, _ in rows[:3]]
    worst = title_of(rows[-1][0])
    total = sum(int(v.get("views", v.get("reach", 0))) for _, v in rows)
    msg = (f"📊 گزارش هفتگی نبض معما: {len(rows)} ریلز، {total} بازدید\n\n🥇 بهترین‌ها:\n" +
           "\n".join(f"{i}. {t}" for i, t in enumerate(best, 1)) + f"\n\n🔻 ضعیف‌ترین: {worst}")
    telegram(state, msg)
    state["report_week"] = week

# ---------------------------------------------------------------- main
def main() -> int:
    if not os.getenv("BUFFER_API_KEY", "").strip():
        log("BUFFER_API_KEY is not set yet; nothing to do")
        return 0
    state = load_json(STATE_FILE, {})
    sent: dict = state.setdefault("sent", {})
    try:
        org, channel = find_channel(state)
    except BufferError as exc:
        warn("Buffer not reachable", str(exc)[:300])
        note_run(state, False, f"Buffer not reachable: {exc}")
        save_state(state)
        return 0
    try:
        run(state, org, channel)
    except Exception as exc:
        warn("Buffer run failed", f"{type(exc).__name__}: {str(exc)[:300]}")
        note_run(state, False, f"{type(exc).__name__}: {str(exc)[:200]}")
    finally:
        for step in (collect_stats, weekly_report):
            try:
                step(state)
            except Exception as exc:
                log(f"{step.__name__} skipped ({type(exc).__name__}: {str(exc)[:120]})")
        save_state(state)
    return 0


def refresh_captions(state: dict, channel: str, now: datetime) -> int:
    """A waiting post whose caption changed in the bank is replaced (same time and video)."""
    changed = 0
    by_stem = {r["stem"]: r for r in built_reels()}
    for key, rec in list(state["sent"].items()):
        reel = by_stem.get(key)
        due = datetime.fromisoformat(rec["due"])
        if rec.get("status") != "scheduled" or not reel or due < now + timedelta(minutes=LEAD_MIN):
            continue
        try:
            new = caption_for(reel)
            if not rec.get("cap"):
                rec["cap"] = text_hash(fetch(reel, "_caption.txt").read_text(encoding="utf-8").strip())
            if rec["cap"] == text_hash(new):
                continue
            post = create_post(channel, new, rec["url"], due)
            try:
                delete_post(rec["post_id"])
            except BufferError as exc:  # never leave two copies: undo the new one
                delete_post(post["id"])
                raise exc
            rec.update(post_id=post["id"], cap=text_hash(new))
            changed += 1
            log(f"caption updated in Buffer: {key}")
        except Exception as exc:
            log(f"caption of {key} not updated ({type(exc).__name__}: {str(exc)[:160]})")
    return changed


def rebuilt_reels(sent: dict, items: list[dict], now: datetime) -> list[tuple]:
    """Queued reels whose video was rebuilt after they went to Buffer (e.g. the Oct 11 voice fix)."""
    by_stem = {r["stem"]: r for r in items if r.get("kind") != "carousel"}
    out = []
    for key, rec in sent.items():
        reel = by_stem.get(key)
        if (reel and rec.get("status") == "scheduled" and rec.get("kind", "reel") != "carousel"
                and int(reel.get("audio_v", 1)) > int(rec.get("audio_v", 1))
                and datetime.fromisoformat(rec["due"]) > now + timedelta(minutes=LEAD_MIN)):
            out.append((key, rec, reel))
    return out


def replace_videos(state: dict, channel: str, upgrades: list[tuple]) -> None:
    """Swap a rebuilt reel into Buffer: same time and caption, the new video under a fresh link
    (so Buffer never reuses the old file). The old post is removed only once the new one exists."""
    if not upgrades:
        return
    want = {}
    for key, rec, reel in upgrades:
        f = fetch(reel, ".mp4")
        v = int(reel.get("audio_v", 1))
        want[key] = (f"{SITE_URL}/v/{f.name}?v={v}", f.stat().st_size, v)
    if not wait_public({u: size for u, size, _ in want.values()}):
        log("rebuilt videos are not public yet; the next run swaps them in")
        return
    for key, rec, reel in upgrades:
        url, _, v = want[key]
        due = datetime.fromisoformat(rec["due"])
        if due < now_utc() + timedelta(minutes=LEAD_MIN):
            continue
        try:
            cap = caption_for(reel)
            try:
                post = create_post(channel, cap, url, due)
            except BufferError as exc:
                if not str(exc).startswith("LIMIT"):
                    raise
                # Buffer's free queue is full: free the old post's place first, then add the new one
                # (twice; the old video link now serves the new file too, so nothing is lost).
                delete_post(rec["post_id"])
                rec["post_id"] = ""
                try:
                    post = create_post(channel, cap, url, due)
                except BufferError:
                    time.sleep(20)
                    post = create_post(channel, cap, url, due)
                rec.update(post_id=post["id"], url=url, cap=text_hash(cap), audio_v=v)
                save_state(state)
                log(f"new video swapped in Buffer (queue was full): {key}")
                continue
            try:
                delete_post(rec["post_id"])
            except BufferError as exc:  # never leave two copies: undo the new one
                delete_post(post["id"])
                raise exc
            rec.update(post_id=post["id"], url=url, cap=text_hash(cap), audio_v=v)
            save_state(state)
            log(f"new video swapped in Buffer: {key}")
        except Exception as exc:
            log(f"video of {key} not swapped ({type(exc).__name__}: {str(exc)[:160]})")
            if not rec.get("post_id"):  # the old post is gone and the new one failed: send it again next run
                state["sent"].pop(key, None)
                save_state(state)
                when = due.astimezone(TEHRAN)
                telegram(state, f"⚠️ نبض معما: ریل {when:%m-%d ساعت %H:%M} در بافر جایگزین نشد؛ "
                                "اجرای بعدی دوباره آن را به صف بافر می‌فرستد.")


def check_queue(state: dict, waiting: list[dict], now: datetime) -> None:
    """Tell the owner when Buffer holds a post past its time (it did not publish by itself)
    or when a queued post's time no longer matches ours (e.g. the Buffer time zone was changed)."""
    by_id = {v["post_id"]: (k, v) for k, v in state["sent"].items() if v.get("status") == "scheduled"}
    stuck, moved = [], []
    for p in waiting:
        if p.get("id") not in by_id or not p.get("dueAt"):
            continue
        key, rec = by_id[p["id"]]
        ours = datetime.fromisoformat(rec["due"])
        theirs = datetime.fromisoformat(str(p["dueAt"]).replace("Z", "+00:00"))
        if theirs < now - timedelta(minutes=STUCK_MIN) and not rec.get("stuck_alerted"):
            stuck.append((key, rec))
        elif abs((theirs - ours).total_seconds()) > 120 and rec.get("moved_alerted") != p["dueAt"]:
            moved.append((key, rec, theirs, p["dueAt"]))
    for key, rec in stuck:
        warn("Post stuck in Buffer", f"{key}: still waiting in Buffer after its time")
        when = datetime.fromisoformat(rec["due"]).astimezone(TEHRAN)
        rec["stuck_alerted"] = telegram(state, (
            f"⚠️ نبض معما: پستی که برای {when:%m-%d ساعت %H:%M} تهران بود هنوز در صف بافر مانده و خودکار منتشر نشده.\n"
            "در برنامه‌ی بافر دستی بزن «انتشار»، و بررسی کن حساب اینستاگرام حرفه‌ای و با انتشار خودکار وصل باشد.")) or True
    for key, rec, theirs, raw in moved:
        warn("Buffer time changed", f"{key}: ours {rec['due']}, Buffer {raw}")
        a = datetime.fromisoformat(rec["due"]).astimezone(TEHRAN)
        b = theirs.astimezone(TEHRAN)
        telegram(state, (f"⚠️ نبض معما: زمان یک پست در بافر عوض شده: قرار بود {a:%m-%d %H:%M} تهران باشد، "
                         f"الان {b:%m-%d %H:%M} تهران است. منطقه‌ی زمانی بافر را روی تهران بگذار."))
        rec["moved_alerted"] = raw


def run(state: dict, org: str, channel: str) -> None:
    sent = state["sent"]
    if STOP_FILE.exists():
        print("::notice title=STOP::the STOP file is in the repo: nothing new goes to Buffer", flush=True)
        return
    try:
        waiting = scheduled_posts(org, channel)
        known = True
    except BufferError as exc:  # fall back on our own record of what is waiting
        log(f"could not read the Buffer queue ({exc}); using our own record")
        waiting = [{"id": v["post_id"], "dueAt": v["due"]} for v in sent.values()
                   if v.get("status") == "scheduled" and datetime.fromisoformat(v["due"]) > now_utc()]
        known = False
    waiting_ids = {p["id"] for p in waiting}
    errored = post_status(org, channel, "error")
    now = now_utc()
    if known:
        check_queue(state, waiting, now)
    for key, rec in sent.items():
        if rec.get("status") != "scheduled":
            continue
        if rec["post_id"] in waiting_ids or not known:
            if not known and datetime.fromisoformat(rec["due"]) < now:
                rec["status"] = "sent"
            continue
        if rec["post_id"] in errored:
            rec["status"] = "error"
            warn("Reel failed in Buffer", f"{key}: Buffer could not publish it (see Buffer > Sent/Errors)")
        elif datetime.fromisoformat(rec["due"]) < now:
            rec["status"] = "sent"
    failed = ""
    refresh_captions(state, channel, now)
    items = built_reels() + built_carousels()
    pending = sorted((r for r in items if r["stem"] not in sent), key=due_of)
    upgrades = rebuilt_reels(sent, items, now)
    room = max(0, QUEUE_MAX - len(waiting))
    log(f"{len(waiting)} post(s) waiting in Buffer, room for {room}; {len(pending)} ready post(s) not sent yet")
    # reels keep 3 hours from other reels; a slide post keeps 2 hours from everything
    car_posts = {v["post_id"] for v in sent.values() if v.get("kind") == "carousel"}
    taken = [datetime.fromisoformat(v["due"]) for v in sent.values()
             if v.get("status") in ("scheduled", "sent") and v.get("kind") != "carousel"]
    taken += [datetime.fromisoformat(str(p["dueAt"]).replace("Z", "+00:00")) for p in waiting
              if p.get("dueAt") and p.get("id") not in car_posts]
    taken_all = taken + [datetime.fromisoformat(v["due"]) for v in sent.values()
                         if v.get("status") in ("scheduled", "sent") and v.get("kind") == "carousel"]
    batch = []
    for reel in pending[: min(room, MAX_NEW)]:
        due = due_of(reel)
        if reel.get("kind") == "carousel":
            moved = next_carousel_slot(taken_all, due, now + timedelta(minutes=LEAD_MIN + 15))
            if moved != due:
                log(f"{reel['stem']}: its time passed or is taken; new time {moved.astimezone(TEHRAN):%Y-%m-%d %H:%M} Tehran")
            due = moved
        else:
            if due < now + timedelta(minutes=LEAD_MIN) or any(abs((due - x).total_seconds()) < GAP_MIN * 60 for x in taken):
                due = next_free_slot(taken, now + timedelta(minutes=LEAD_MIN + 15), reel["stem"])
                log(f"{reel['stem']}: its time passed or is taken; new time {due.astimezone(TEHRAN):%Y-%m-%d %H:%M} Tehran")
            taken.append(due)
        taken_all.append(due)
        batch.append((reel, due))
    # Videos that must stay public: every reel still waiting in Buffer, plus the new ones.
    keep = [r for r in items if sent.get(r["stem"], {}).get("status") == "scheduled"]
    keep += [r for r, _ in batch]
    if not batch:
        log("nothing new to send")
        hosted = sorted(r["stem"] for r in keep)
        page = films_page(state)
        if upgrades or hosted != sorted(state.get("hosted", [])) or text_hash(page) != state.get("films_page"):
            files = [f for r in keep for f in item_files(r)]
            publish_site(files, page, film_covers(state))
            state["hosted"], state["films_page"] = hosted, text_hash(page)
        replace_videos(state, channel, upgrades)
        note_run(state, True)
        return
    files, urls, new_urls = [], {}, {}
    fresh = {r["stem"] for r, _ in batch}
    for reel in keep:
        for f in item_files(reel):
            files.append(f)
            urls[f"{SITE_URL}/v/{f.name}"] = f.stat().st_size
            if reel["stem"] in fresh:
                new_urls[f"{SITE_URL}/v/{f.name}"] = f.stat().st_size
    page = films_page(state)
    publish_site(files, page, film_covers(state))
    state["hosted"], state["films_page"] = sorted(r["stem"] for r in keep), text_hash(page)
    save_state(state)
    if not wait_public(new_urls):
        warn("Videos not public yet", "GitHub Pages of nabz-reels did not serve the videos in 12 minutes "
             "(is Pages on: Settings > Pages > main / root?). The next run tries again.")
        note_run(state, False, "videos not public on nabz-reels Pages")
        return
    replace_videos(state, channel, upgrades)
    made = 0
    for reel, due in batch:
        v = int(reel.get("audio_v", 1))
        # a fresh link per voice version: Buffer keeps the file it first fetched under a link
        url = f"{SITE_URL}/v/{reel['stem']}.mp4" + (f"?v={v}" if v > 1 else "")
        try:
            if reel.get("kind") == "carousel":
                from src import ig_slides
                pics = [f"{SITE_URL}/v/{ig_slides.file_name(reel['id'], k)}" for k in range(1, int(reel["slides"]) + 1)]
                url = pics[0]
                cap = carousel_caption(reel)
                post = create_carousel(channel, cap, pics, due)
            else:
                cap = caption_for(reel)
                post = create_post(channel, cap, url, due)
        except BufferError as exc:
            if str(exc).startswith("LIMIT"):
                log(f"Buffer queue is full: {exc}")
                break
            warn("Buffer refused a reel", f"{reel['stem']}: {str(exc)[:300]}")
            failed = f"Buffer refused {reel['stem']}: {str(exc)[:200]}"
            continue
        except Exception as exc:
            warn("Reel not sent", f"{reel['stem']}: {type(exc).__name__}: {str(exc)[:300]}")
            failed = f"{reel['stem']}: {type(exc).__name__}: {str(exc)[:200]}"
            continue
        sent[reel["stem"]] = {"post_id": post["id"], "due": due.isoformat(), "status": "scheduled",
                              "url": url, "cap": text_hash(cap), "kind": reel.get("kind", "reel"),
                              "audio_v": int(reel.get("audio_v", 1)),
                              "at": now.astimezone(TEHRAN).isoformat(timespec="minutes")}
        save_state(state)
        made += 1
        log(f"scheduled in Buffer: {reel['stem']} at {due.astimezone(TEHRAN):%a %Y-%m-%d %H:%M} Tehran")
    print(f"::notice title=Buffer::{made} new post(s) scheduled; {len(waiting) + made} waiting in Buffer", flush=True)
    note_run(state, not failed, failed)


if __name__ == "__main__":
    sys.exit(main())
