"""Daily YouTube performance check for NABZ Mysteries, fully automatic (owner wants no screenshots).

Runs at the end of the daily upload (src.youtube_uploader, after the comment catch-up), so its
files land in review/, which that workflow already commits. Two layers:

1. YouTube Data API (works with the current token): views, likes, comments per Short.
2. YouTube Analytics API (needs the yt-analytics.readonly scope in YOUTUBE_REFRESH_TOKEN):
   average % viewed (over 100 = loops), average view seconds, engaged views, shares,
   subscribers gained/lost, daily trend and traffic sources. Analytics data lags ~2 days.

Each Short is matched to its story (id, music mood, hook length) so the report can say which
hooks and moods hold viewers. Never fails the run; problems become warnings in the report.
Files: review/yt_stats.json (latest), review/yt_stats_history.json (daily snapshots),
review/yt_stats.md (readable report with automatic findings).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "review" / "yt_stats.json"
OUT_HIST = ROOT / "review" / "yt_stats_history.json"
OUT_MD = ROOT / "review" / "yt_stats.md"
ANALYTICS_SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly"]
VIDEO_METRICS = ("views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
                 "likes,comments,shares,subscribersGained,subscribersLost")


# ------------------------------------------------------------------ helpers (pure)
def _f(x, default=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def rows_to_dicts(resp: dict) -> list[dict]:
    """Analytics API answer -> list of {column: value}."""
    cols = [h.get("name") for h in (resp or {}).get("columnHeaders") or []]
    return [dict(zip(cols, r)) for r in (resp or {}).get("rows") or []]


def hook_words(story: dict | None) -> int | None:
    try:
        return len(str(story["beats"][0]["text"]).split())
    except Exception:
        return None


def mood_of(story_id: str | None) -> str | None:
    if not story_id:
        return None
    try:
        from src import music_mood
        moods = getattr(music_mood, "MOODS", {}) or {}
        val = moods.get(story_id)
        return val if isinstance(val, str) else None
    except Exception:
        return None


def group_avg(videos: list[dict], key: str, metric: str, min_n: int = 1) -> dict:
    groups: dict = {}
    for v in videos:
        k, m = v.get(key), v.get(metric)
        if k is None or m is None:
            continue
        groups.setdefault(k, []).append(_f(m))
    return {k: round(sum(ms) / len(ms), 1) for k, ms in groups.items() if len(ms) >= min_n}


def findings(videos: list[dict], daily: list[dict], has_analytics: bool) -> list[str]:
    """Plain-language takeaways the owner never has to compute."""
    out: list[str] = []
    pub = [v for v in videos if v.get("views") is not None]
    if not pub:
        return ["No public Shorts with numbers yet."]
    total = sum(int(_f(v.get("views"))) for v in pub)
    out.append(f"{len(pub)} Shorts, {total} views in total, {round(total / len(pub))} per Short on average.")
    best = max(pub, key=lambda v: _f(v.get("views")))
    worst = min(pub, key=lambda v: _f(v.get("views")))
    out.append(f"Most views: {best.get('title')} ({best.get('views')}); fewest: {worst.get('title')} ({worst.get('views')}).")
    if has_analytics:
        held = [v for v in pub if v.get("avg_view_pct") is not None]
        if held:
            top = max(held, key=lambda v: _f(v["avg_view_pct"]))
            low = min(held, key=lambda v: _f(v["avg_view_pct"]))
            avg = sum(_f(v["avg_view_pct"]) for v in held) / len(held)
            out.append(f"Average % viewed: {avg:.0f}% (target 70%+; over 100% means people loop it). "
                       f"Best hold: {top.get('title')} {top['avg_view_pct']}%; weakest: {low.get('title')} {low['avg_view_pct']}%.")
            eng = [v for v in held if v.get("engaged_views") and _f(v.get("views"))]
            if eng:
                r = sum(_f(v["engaged_views"]) for v in eng) / max(1.0, sum(_f(v["views"]) for v in eng))
                out.append(f"Engaged views are {r * 100:.0f}% of views (rough 'did not swipe away' signal).")
            by_mood = group_avg(held, "mood", "avg_view_pct")
            if len(by_mood) >= 2:
                order = sorted(by_mood.items(), key=lambda kv: -kv[1])
                out.append("Hold by mood: " + ", ".join(f"{k} {v}%" for k, v in order) + ".")
            short_h = [_f(v["avg_view_pct"]) for v in held if v.get("hook_words") and v["hook_words"] <= 10]
            long_h = [_f(v["avg_view_pct"]) for v in held if v.get("hook_words") and v["hook_words"] > 10]
            if short_h and long_h:
                out.append(f"Hooks of 10 words or fewer hold {sum(short_h) / len(short_h):.0f}% vs "
                           f"{sum(long_h) / len(long_h):.0f}% for longer hooks.")
        subs = sum(int(_f(v.get("subs_gained"))) - int(_f(v.get("subs_lost"))) for v in pub)
        if total:
            out.append(f"Net subscribers from Shorts: {subs} ({subs * 1000 / total:.1f} per 1,000 views).")
        if len(daily) >= 8:
            last7 = sum(_f(d.get("views")) for d in daily[-7:])
            prev7 = sum(_f(d.get("views")) for d in daily[-14:-7])
            if prev7:
                out.append(f"Channel views last 7 days: {int(last7)} ({(last7 / prev7 - 1) * 100:+.0f}% vs the week before).")
    likes = sum(int(_f(v.get("likes"))) for v in pub)
    comments = sum(int(_f(v.get("comments"))) for v in pub)
    if total:
        out.append(f"Likes per 100 views: {likes * 100 / total:.1f}; comments in total: {comments}.")
    return out


def render_md(report: dict) -> str:
    lines = [f"# YouTube stats ({report['at'][:16]} UTC)", ""]
    if report.get("warning"):
        lines += [f"> {report['warning']}", ""]
    lines += ["## Findings", ""] + [f"- {x}" for x in report.get("findings", [])] + ["", "## Per Short", ""]
    lines.append("| published | title | views | avg % viewed | avg s | engaged | likes | comments | subs+ | mood | hook words |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for v in sorted(report.get("videos", []), key=lambda x: x.get("published", ""), reverse=True):
        lines.append("| {} | [{}](https://youtu.be/{}) | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            str(v.get("published", ""))[:10], str(v.get("title", "")).replace("|", "/"), v.get("id"),
            v.get("views", ""), v.get("avg_view_pct", ""), v.get("avg_view_sec", ""), v.get("engaged_views", ""),
            v.get("likes", ""), v.get("comments", ""), v.get("subs_gained", ""), v.get("mood") or "",
            v.get("hook_words") or ""))
    if report.get("traffic"):
        lines += ["", "## Where views come from", ""]
        lines += [f"- {t['source']}: {t['views']}" for t in report["traffic"]]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ API calls
def all_uploads(youtube, limit: int = 200):
    ch = youtube.channels().list(part="contentDetails,statistics", mine=True).execute()
    items = ch.get("items") or []
    if not items:
        raise RuntimeError("no channel for this token")
    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, token = [], None
    while len(ids) < limit:
        pl = youtube.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=50,
                                          pageToken=token).execute()
        ids += [i["contentDetails"]["videoId"] for i in pl.get("items") or []]
        token = pl.get("nextPageToken")
        if not token:
            break
    videos = []
    for i in range(0, len(ids), 50):
        videos += youtube.videos().list(part="snippet,status,statistics,contentDetails",
                                        id=",".join(ids[i:i + 50])).execute().get("items") or []
    return videos, (items[0].get("statistics") or {})


def analytics_client():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from src.youtube_uploader import load_credential_info
    creds = Credentials.from_authorized_user_info(load_credential_info(), ANALYTICS_SCOPES)
    return build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)


def analytics(start: str, end: str) -> dict:
    yta = analytics_client()
    q = dict(ids="channel==MINE", startDate=start, endDate=end)
    per_video = rows_to_dicts(yta.reports().query(metrics=VIDEO_METRICS, dimensions="video",
                                                  sort="-views", maxResults=200, **q).execute())
    engaged = {}
    try:
        for r in rows_to_dicts(yta.reports().query(metrics="engagedViews", dimensions="video",
                                                   sort="-engagedViews", maxResults=200, **q).execute()):
            engaged[r.get("video")] = r.get("engagedViews")
    except Exception as exc:
        print(f"YT STATS: engaged views unavailable ({type(exc).__name__})")
    daily = rows_to_dicts(yta.reports().query(metrics="views,estimatedMinutesWatched,subscribersGained,subscribersLost",
                                              dimensions="day", sort="day", **q).execute())
    traffic = []
    try:
        traffic = [{"source": r.get("insightTrafficSourceType"), "views": r.get("views")}
                   for r in rows_to_dicts(yta.reports().query(metrics="views", dimensions="insightTrafficSourceType",
                                                              sort="-views", **q).execute())]
    except Exception as exc:
        print(f"YT STATS: traffic sources unavailable ({type(exc).__name__})")
    return {"per_video": {r.get("video"): r for r in per_video}, "engaged": engaged,
            "daily": daily, "traffic": traffic}


# ------------------------------------------------------------------ main
def build_report(now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    from src.yt_comment import client, find_story
    youtube = client()
    raw, channel = all_uploads(youtube)
    videos = []
    for v in raw:
        if (v.get("status") or {}).get("privacyStatus") != "public":
            continue
        sn, st = v.get("snippet") or {}, v.get("statistics") or {}
        story = find_story(sn.get("title", ""))
        sid = (story or {}).get("id")
        videos.append({"id": v["id"], "title": re.sub(r"\s*#\w+", "", sn.get("title", "")).strip(),
                       "published": sn.get("publishedAt", ""), "story_id": sid, "mood": mood_of(sid),
                       "hook_words": hook_words(story), "views": int(_f(st.get("viewCount"))),
                       "likes": int(_f(st.get("likeCount"))), "comments": int(_f(st.get("commentCount")))})
    report = {"at": now.isoformat(), "channel": {k: channel.get(k) for k in ("subscriberCount", "viewCount", "videoCount")},
              "videos": videos, "daily": [], "traffic": [], "analytics": False}
    if videos:
        start = min(v["published"][:10] for v in videos if v["published"]) or "2026-09-01"
        try:
            a = analytics(start, now.date().isoformat())
            for v in videos:
                r = a["per_video"].get(v["id"]) or {}
                if r:
                    v.update({"avg_view_pct": round(_f(r.get("averageViewPercentage")), 1),
                              "avg_view_sec": int(_f(r.get("averageViewDuration"))),
                              "shares": int(_f(r.get("shares"))),
                              "subs_gained": int(_f(r.get("subscribersGained"))),
                              "subs_lost": int(_f(r.get("subscribersLost")))})
                if a["engaged"].get(v["id"]) is not None:
                    v["engaged_views"] = int(_f(a["engaged"][v["id"]]))
            report.update(daily=a["daily"], traffic=a["traffic"], analytics=True)
        except Exception as exc:
            text = f"{type(exc).__name__}: {exc}"
            report["warning"] = ("Retention/subscriber numbers missing: the refresh token needs the "
                                 "yt-analytics.readonly scope. " if re.search(r"scope|insufficient|403|invalid_grant|accessNotConfigured|disabled", text, re.I)
                                 else "Analytics call failed. ") + text[:200]
    report["findings"] = findings(videos, report["daily"], report["analytics"])
    return report


def save(report: dict) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_MD.write_text(render_md(report), encoding="utf-8")
    try:
        hist = json.loads(OUT_HIST.read_text(encoding="utf-8"))
        if not isinstance(hist, dict):
            hist = {}
    except Exception:
        hist = {}
    day = report["at"][:10]
    hist[day] = {"channel": report.get("channel"),
                 "videos": {v["id"]: {k: v.get(k) for k in ("views", "avg_view_pct", "engaged_views", "likes",
                                                             "comments", "subs_gained") if v.get(k) is not None}
                            for v in report.get("videos", [])}}
    keep = dict(sorted(hist.items())[-120:])
    OUT_HIST.write_text(json.dumps(keep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> int:
    try:
        report = build_report()
        save(report)
        print("YT STATS:", " | ".join(report["findings"][:3]))
        if report.get("warning"):
            print(f"::warning title=YouTube stats partial::{report['warning'][:300]}")
    except Exception as exc:
        print(f"::warning title=YouTube stats skipped::{type(exc).__name__}: {str(exc)[:300]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
