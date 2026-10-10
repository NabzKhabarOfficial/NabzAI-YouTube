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
import urllib.error
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
MAX_NEW = int(os.getenv("NABZ_BUFFER_MAX_NEW", "10"))  # NABZ_BUFFER_MAX_NEW=1 for a first test
SLOTS = [(13 * 60, 14 * 60 + 10), (20 * 60 + 30, 22 * 60 + 40)]
GAP_MIN = 180


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


# ---------------------------------------------------------------- the pack
def gh(*args, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args, "--repo", REPO], capture_output=True, text=True, check=check)


def stem(item: dict) -> str:
    return f"{item['n']:02d}_{item['date']}_{item['time'].replace(':', '')}_{item['id']}"


def built_reels() -> list[dict]:
    pack = load_json(PACK_STATE, {})
    out = []
    for week, info in sorted((pack.get("weeks") or {}).items()):
        built = info.get("built") or {}
        for item in info.get("plan") or []:
            if item["id"] in built:
                out.append(dict(item, week=week, stem=stem(item), tag=f"week-{week}"))
    return out


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


# ---------------------------------------------------------------- public video site
def publish_site(files: list[Path]) -> None:
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
    env = dict(os.environ, GIT_AUTHOR_NAME="github-actions[bot]", GIT_COMMITTER_NAME="github-actions[bot]",
               GIT_AUTHOR_EMAIL="41898282+github-actions[bot]@users.noreply.github.com",
               GIT_COMMITTER_EMAIL="41898282+github-actions[bot]@users.noreply.github.com")
    run = lambda *a: subprocess.run(list(a), cwd=site, env=env, check=True, capture_output=True, text=True)
    run("git", "init", "-q", "-b", "main")
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", f"reels on {now_utc():%Y-%m-%d %H:%M} UTC")
    url = f"https://x-access-token:{pat}@github.com/{SITE_REPO}.git"
    proc = subprocess.run(["git", "push", "-q", "--force", url, "main:main"], cwd=site, env=env,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("push to nabz-reels failed: " + proc.stderr.replace(pat, "***")[:300])


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
        save_state(state)
        return 0
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
    pending = [r for r in built_reels() if r["stem"] not in sent]
    room = max(0, QUEUE_MAX - len(waiting))
    log(f"{len(waiting)} reel(s) waiting in Buffer, room for {room}; {len(pending)} built reel(s) not sent yet")
    taken = [datetime.fromisoformat(v["due"]) for v in sent.values() if v.get("status") in ("scheduled", "sent")]
    taken += [datetime.fromisoformat(str(p["dueAt"]).replace("Z", "+00:00")) for p in waiting if p.get("dueAt")]
    batch = []
    for reel in pending[: min(room, MAX_NEW)]:
        due = due_of(reel)
        if due < now + timedelta(minutes=LEAD_MIN) or any(abs((due - x).total_seconds()) < GAP_MIN * 60 for x in taken):
            due = next_free_slot(taken, now + timedelta(minutes=LEAD_MIN + 15), reel["stem"])
            log(f"{reel['stem']}: its time passed or is taken; new time {due.astimezone(TEHRAN):%Y-%m-%d %H:%M} Tehran")
        taken.append(due)
        batch.append((reel, due))
    # Videos that must stay public: every reel still waiting in Buffer, plus the new ones.
    keep = [r for r in built_reels() if sent.get(r["stem"], {}).get("status") == "scheduled"]
    keep += [r for r, _ in batch]
    if not batch:
        log("nothing new to send")
        hosted = sorted(r["stem"] for r in keep)
        if hosted != sorted(state.get("hosted", [])) and hosted:
            files = [fetch(r, ".mp4") for r in keep]
            publish_site(files)
            state["hosted"] = hosted
        save_state(state)
        return 0
    files, urls = [], {}
    for reel in keep:
        f = fetch(reel, ".mp4")
        files.append(f)
        urls[f"{SITE_URL}/v/{f.name}"] = f.stat().st_size
    publish_site(files)
    state["hosted"] = sorted(r["stem"] for r in keep)
    save_state(state)
    if not wait_public({u: s for u, s in urls.items() if any(u.endswith(f"{r['stem']}.mp4") for r, _ in batch)}):
        warn("Videos not public yet", "GitHub Pages of nabz-reels did not serve the videos in 12 minutes "
             "(is Pages on: Settings > Pages > main / root?). The next run tries again.")
        return 0
    made = 0
    for reel, due in batch:
        cap = fetch(reel, "_caption.txt").read_text(encoding="utf-8").strip()
        url = f"{SITE_URL}/v/{reel['stem']}.mp4"
        try:
            post = create_post(channel, cap, url, due)
        except BufferError as exc:
            if str(exc).startswith("LIMIT"):
                log(f"Buffer queue is full: {exc}")
                break
            warn("Buffer refused a reel", f"{reel['stem']}: {str(exc)[:300]}")
            continue
        sent[reel["stem"]] = {"post_id": post["id"], "due": due.isoformat(), "status": "scheduled",
                              "url": url, "at": now.astimezone(TEHRAN).isoformat(timespec="minutes")}
        save_state(state)
        made += 1
        log(f"scheduled in Buffer: {reel['stem']} at {due.astimezone(TEHRAN):%a %Y-%m-%d %H:%M} Tehran")
    print(f"::notice title=Buffer::{made} new reel(s) scheduled; {len(waiting) + made} waiting in Buffer", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
