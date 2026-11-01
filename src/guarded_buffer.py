"""Fail-closed, claim-guarded Buffer entry point."""
from __future__ import annotations
import hashlib, json, os, urllib.error, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from src import ig_buffer
from src.idempotency import claim, finish, fingerprint, get
from src.ig_runtime_safety import install as install_runtime_safety
ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "content" / "publication_claims.json"
BUFFER_STATE = ROOT / "content" / "ig_buffer_state.json"
STATS_PER_RUN = 5  # metric reads per run; Buffer's API is rate limited (HTTP 429)

class BufferTransportAmbiguous(RuntimeError):
    """The provider may have accepted a mutation but the response was lost."""

def _identity(kind: str, *parts: object) -> str:
    raw = "\x1f".join(str(part or "").strip() for part in parts)
    return hashlib.sha256((kind + "\x1f" + raw).encode()).hexdigest()[:32]

def _reserve(kind, identity, metadata):
    key = fingerprint("buffer_" + kind, identity); current = get(CLAIMS, key)
    if current is not None:
        if current.status == "succeeded": return key, {"id": current.external_id, "_already_confirmed": True}
        # A clean rejection ('failed') may be sent again. 'pending' and 'ambiguous' mean the provider
        # may already have the post, so they wait for reconciliation.
        if current.status != "failed":
            raise RuntimeError(f"Buffer {kind} claim is {current.status}; manual reconciliation required: {key}")
    if not claim(CLAIMS, key, metadata): raise RuntimeError(f"Buffer {kind} claim appeared concurrently; manual reconciliation required: {key}")
    return key, None

def _confirmed(key, post_id):
    finish(CLAIMS, key, post_id, status="succeeded"); return {"id": post_id}

def _is_transport_ambiguous(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return isinstance(exc, (BufferTransportAmbiguous, TimeoutError, urllib.error.URLError)) or any(
        marker in text for marker in ("timeout", "timed out", "connection reset", "connection aborted", "broken pipe", "network:"))

def _finish_failure(key, exc: BaseException):
    status = "ambiguous" if _is_transport_ambiguous(exc) else "failed"
    finish(CLAIMS, key, "", status=status)
    return status

def _mutation_once(query, variables=None):
    key = os.getenv("BUFFER_API_KEY", "").strip()
    if not key: raise ig_buffer.BufferError("BUFFER_API_KEY secret is missing")
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(ig_buffer.API, data=body, method="POST", headers={"Content-Type":"application/json", "Authorization":f"Bearer {key}", "User-Agent":"nabz-reels/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp: data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise ig_buffer.BufferError(f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:400]}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise BufferTransportAmbiguous(f"mutation transport outcome ambiguous: {exc}") from None
    if data.get("errors"): raise ig_buffer.BufferError("; ".join(str(e.get("message", e)) for e in data["errors"])[:500])
    return data.get("data") or {}

def _query_once(query, variables=None):
    """One read from Buffer, no retries (a retry on 429 only makes the rate limit worse)."""
    key = os.getenv("BUFFER_API_KEY", "").strip()
    if not key: raise ig_buffer.BufferError("BUFFER_API_KEY secret is missing")
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(ig_buffer.API, data=body, method="POST", headers={"Content-Type":"application/json", "Authorization":f"Bearer {key}", "User-Agent":"nabz-reels/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp: data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise ig_buffer.BufferError(f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:200]}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ig_buffer.BufferError(f"network: {exc}") from None
    if data.get("errors"): raise ig_buffer.BufferError("; ".join(str(e.get("message", e)) for e in data["errors"])[:300])
    return data.get("data") or {}

def limited_collect_stats(state):
    """Replaces ig_buffer.collect_stats: at most STATS_PER_RUN posts per run, one try each, and it
    stops at the first rate limit. Oct 31 2026: the full pass retried every 429 and took 25 minutes."""
    stats = ig_buffer.load_json(ig_buffer.STATS_FILE, {"posts": {}})
    stats.setdefault("posts", {})
    today = datetime.now(ig_buffer.TEHRAN).date().isoformat()
    if stats.get("collected") == today:
        return
    now = datetime.now(timezone.utc)
    read, limited = 0, False
    for key, rec in state.get("sent", {}).items():
        if read >= STATS_PER_RUN or limited:
            break
        due = datetime.fromisoformat(rec["due"])
        if rec.get("status") != "sent" or key in stats["posts"] or not now - timedelta(days=14) < due < now - timedelta(hours=24):
            continue
        try:
            post = _query_once(ig_buffer.METRICS_Q % json.dumps(rec["post_id"]))["post"]
        except ig_buffer.BufferError as exc:
            if "429" in str(exc) or "Too many" in str(exc):
                limited = True
                break
            continue
        read += 1
        vals = {m["type"]: m["value"] for m in post.get("metrics") or []}
        if vals:
            stats["posts"][key] = {"due": rec["due"], **{k: vals[k] for k in vals if k in ig_buffer.KEYS},
                                   "updated": post.get("metricsUpdatedAt")}
    # The day counts as collected only when no rate limit stopped the pass; otherwise the next run continues.
    if not limited:
        stats["collected"] = today
    ig_buffer.STATS_FILE.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def _wrap_mutations():
    if getattr(ig_buffer, "_NABZ_GUARDED", False): return
    original_gql, original_post = ig_buffer.gql, ig_buffer.create_post
    original_story, original_carousel, original_delete = ig_buffer.create_story, ig_buffer.create_carousel, ig_buffer.delete_post
    def strict_gql(query, variables=None):
        return _mutation_once(query, variables) if str(query).lstrip().startswith("mutation") else original_gql(query, variables)
    def guard_queue_known():
        if not getattr(ig_buffer, "_buffer_queue_known", True):
            raise RuntimeError("Buffer queue state is unknown; provider reconciliation required before any mutation")
    def guarded_post(channel, text, video_url, due):
        guard_queue_known()
        key, cached = _reserve("reel", _identity("reel", video_url, due.isoformat(), text), {"provider":"buffer","kind":"reel","video_url":video_url,"due":due.isoformat()})
        if cached: return cached
        try: post = original_post(channel, text, video_url, due)
        except Exception as exc:
            status = _finish_failure(key, exc); raise RuntimeError(f"Buffer reel outcome {status} for claim {key}: {exc}") from exc
        pid = str((post or {}).get("id") or "")
        if not pid: finish(CLAIMS, key, "", status="ambiguous"); raise RuntimeError(f"Buffer reel returned no post id for claim {key}")
        return _confirmed(key, pid)
    def guarded_story(channel, video_url, due):
        guard_queue_known()
        key, cached = _reserve("story", _identity("story", video_url, due.isoformat()), {"provider":"buffer","kind":"story","video_url":video_url,"due":due.isoformat()})
        if cached: return cached
        try: post = original_story(channel, video_url, due)
        except Exception as exc:
            status = _finish_failure(key, exc); raise RuntimeError(f"Buffer story outcome {status} for claim {key}: {exc}") from exc
        pid = str((post or {}).get("id") or "")
        if not pid: finish(CLAIMS, key, "", status="ambiguous"); raise RuntimeError(f"Buffer story returned no post id for claim {key}")
        return _confirmed(key, pid)
    def guarded_carousel(channel, text, image_urls, due):
        guard_queue_known()
        key, cached = _reserve("carousel", _identity("carousel", "|".join(image_urls), due.isoformat(), text), {"provider":"buffer","kind":"carousel","images":list(image_urls),"due":due.isoformat()})
        if cached: return cached
        try: post = original_carousel(channel, text, image_urls, due)
        except Exception as exc:
            status = _finish_failure(key, exc); raise RuntimeError(f"Buffer carousel outcome {status} for claim {key}: {exc}") from exc
        pid = str((post or {}).get("id") or "")
        if not pid: finish(CLAIMS, key, "", status="ambiguous"); raise RuntimeError(f"Buffer carousel returned no post id for claim {key}")
        return _confirmed(key, pid)
    def guarded_delete(post_id):
        guard_queue_known()
        key, cached = _reserve("delete", _identity("delete", post_id), {"provider":"buffer","kind":"delete","post_id":str(post_id)})
        if cached: return None
        try: original_delete(post_id)
        except Exception as exc:
            status = _finish_failure(key, exc); raise RuntimeError(f"Buffer delete outcome {status} for claim {key}: {exc}") from exc
        finish(CLAIMS, key, str(post_id), status="succeeded"); return None
    ig_buffer.gql = strict_gql; ig_buffer.create_post = guarded_post; ig_buffer.create_story = guarded_story
    ig_buffer.create_carousel = guarded_carousel; ig_buffer.delete_post = guarded_delete; ig_buffer._NABZ_GUARDED = True
    ig_buffer.collect_stats = limited_collect_stats

def run():
    if not os.getenv("BUFFER_API_KEY", "").strip(): raise RuntimeError("BUFFER_API_KEY is missing; refusing to report a successful Buffer run")
    if not os.getenv("REELS_PAT", "").strip(): raise RuntimeError("REELS_PAT is missing; refusing to publish without public video hosting")
    install_runtime_safety(ig_buffer); _wrap_mutations(); result = ig_buffer.main(); state = ig_buffer.load_json(BUFFER_STATE, {})
    if int(state.get("fail_streak", 0) or 0) > 0: raise RuntimeError("Buffer recorded a failed run; claims require reconciliation")
    return int(result or 0)
if __name__ == "__main__": raise SystemExit(run())
