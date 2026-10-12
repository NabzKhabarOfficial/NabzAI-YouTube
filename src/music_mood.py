"""Background music that fits each story (owner, Oct 12 2026).

Every Short and reel used to get the same dark ambient score (only its random seed changed).
Now each story has a mood, and the score is built for that mood:

  sea      waves breathing under slow minor chords (ships, islands, lighthouses, crews)
  crime    a tense heartbeat pulse and dark half-step chords (murders, killers, ciphers)
  sky      wide shimmering pads, floating and open (planes, signals, lights, space)
  ancient  a frame drum and plucked strings over a drone (old kingdoms, manuscripts, treasure)
  vanish   near silence: soft wind, single piano notes (people who disappeared)

The mood comes from MOODS (set by hand per story id) or, for a story not listed, from words in
its title, tags and pictures. Everything is made with numpy (free, offline, no quota), in the
range phone speakers can play. src.mystery_short.make_music asks score(seconds, seed); the
story is found from the seed (the Short uses sha1(id), the Persian reel sha1(id) + 11), so no
caller has to change. Any problem returns None and the old score is used.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "content" / "mysteries.json"
SR = 44100

MOODS = {
    # sea
    "flannan-isles": "sea", "carroll-deering": "sea", "kaz-ii": "sea", "mv-joyita": "sea",
    "ss-baychimo": "sea", "alcatraz-escape": "sea", "ss-waratah": "sea", "fletcher-christian": "sea",
    "franklin-expedition": "sea", "solway-firth-spaceman": "sky",
    # crime
    "somerton-man": "crime", "zodiac-killer": "crime", "hinterkaifeck": "crime", "lead-masks": "crime",
    "db-cooper": "crime", "jack-the-ripper": "crime", "jimmy-hoffa": "crime", "lake-bodom": "crime",
    "villisca-axe-murders": "crime", "isdal-woman": "crime", "max-headroom-hijack": "crime",
    "black-dahlia": "crime", "lizzie-borden": "crime", "sodder-children": "crime", "lord-lucan": "crime",
    "babushka-lady": "crime", "peter-bergmann": "crime",
    # sky
    "flight-19": "sky", "mh370": "sky", "amelia-earhart": "sky", "glenn-miller": "sky",
    "frederick-valentich": "sky", "wow-signal": "sky", "tunguska-event": "sky", "hessdalen-lights": "sky",
    "marfa-lights": "sky", "taos-hum": "sky", "hindenburg": "sky", "travis-walton": "sky", "mothman": "sky",
    # ancient
    "voynich-manuscript": "ancient", "antikythera-mechanism": "ancient", "nazca-lines": "ancient",
    "princes-in-the-tower": "ancient", "dancing-plague-1518": "ancient", "green-children-of-woolpit": "ancient",
    "beale-ciphers": "ancient", "amber-room": "ancient", "oak-island": "ancient", "rongorongo": "ancient",
    "linear-a": "ancient", "phaistos-disc": "ancient", "gobekli-tepe": "ancient", "ninth-legion": "ancient",
    "lost-army-of-cambyses": "ancient", "cambyses-army": "ancient", "lost-dutchmans-mine": "ancient",
    "toynbee-tiles": "vanish", "anastasia": "ancient",
    # vanish
    "paula-welden": "vanish", "kaspar-hauser": "vanish", "dorothy-arnold": "vanish", "ambrose-small": "vanish",
    "percy-fawcett": "vanish", "mallory-irvine": "vanish", "walter-collins": "vanish", "brian-shaffer": "vanish",
    "yuba-county-five": "vanish", "lars-mittank": "vanish",
}
_WORDS = [  # first match wins (checked in this order)
    ("crime", r"murder|killer|killed|axe|ripper|crime|police|detective|mafia|poison|stab|suspect|victim"),
    ("sea", r"\bship|\bboat|\bsea\b|ocean|sailor|lighthouse|\bisland|\bcrew\b|voyage|harbou?r|\bwaves?\b"),
    ("sky", r"plane|aircraft|pilot|\bsky\b|signal|\bspace\b|\bstars?\b|\blights?\b|meteor|radio|ufo|alien|telescope"),
    ("ancient", r"ancient|manuscript|temple|tomb|ruin|roman|legion|tablet|medieval|pyramid|\bking|prince|castle|treasure|script"),
]
_SEEDS: dict | None = None


def mood_of(story: dict) -> str:
    sid = str(story.get("id", ""))
    if sid in MOODS:
        return MOODS[sid]
    text = " ".join([story.get("title", ""), " ".join(story.get("tags", []))]
                    + [str(b.get("visual", "")) + " " + str(b.get("text", "")) for b in story.get("beats", [])]).lower()
    for mood, pattern in _WORDS:
        if re.search(pattern, text):
            return mood
    return "vanish"


def _seed_map() -> dict:
    global _SEEDS
    if _SEEDS is None:
        _SEEDS = {}
        try:
            stories = json.loads(BANK.read_text(encoding="utf-8"))["stories"]
        except Exception:
            stories = []
        for s in stories:
            base = int(hashlib.sha1(s["id"].encode()).hexdigest()[:6], 16)
            mood = mood_of(s)
            for k in (0, 11):  # the Short, the Persian reel
                _SEEDS.setdefault(base + k, mood)
    return _SEEDS


def mood_for_seed(seed: int) -> str | None:
    return _seed_map().get(int(seed))


# ---------------------------------------------------------------- building blocks
def _lp(x, cutoff):
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(spec / (1 + (f / cutoff) ** 4), n=len(x))


def _hp(x, cutoff):
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(spec * (1 - 1 / (1 + (f / cutoff) ** 4)), n=len(x))


def _fade(n, a, r):
    e = np.ones(n)
    ai, ri = min(n // 2, int(a * SR)), min(n // 2, int(r * SR))
    if ai:
        e[:ai] = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, ai))
    if ri:
        e[-ri:] = 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, ri))
    return e


def _hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def _pad(freq, n, rng, harmonics=8):
    t = np.arange(n) / SR
    out = np.zeros(n)
    for det in (-0.07, 0.0, 0.06):
        f = freq * 2 ** (det / 12)
        ph = rng.uniform(0, 2 * np.pi)
        for h in range(1, harmonics + 1):
            if f * h > 6000:
                break
            out += np.sin(2 * np.pi * f * h * t + ph * h) / h
    return out / 6.0


def _reverb(st, rng, seconds, wet):
    m = int(seconds * SR)
    kk = np.arange(m) / SR
    size = len(st) + m
    out = np.empty_like(st)
    for ch in range(2):
        ir = _lp(rng.standard_normal(m) * np.exp(-kk * (5.5 / seconds)), 5200.0)
        ir[: int(0.012 * SR)] = 0.0
        ir /= np.sqrt(np.sum(ir ** 2)) or 1
        w = np.fft.irfft(np.fft.rfft(st[:, ch], size) * np.fft.rfft(ir, size), size)[: len(st)]
        out[:, ch] = (1 - wet) * st[:, ch] + wet * w
    return out


def _add(L, R, sig, start, pan=0.0):
    st = int(start * SR)
    if st >= len(L):
        return
    en = min(len(L), st + len(sig))
    L[st:en] += sig[: en - st] * (1 - pan)
    R[st:en] += sig[: en - st] * (1 + pan)


def _piano(f, seconds=2.8, decay=2.4):
    t = np.arange(int(seconds * SR)) / SR
    note = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t) + 0.12 * np.sin(6 * np.pi * f * t))
    return note * np.exp(-t * decay) * _fade(len(t), 0.006, 0.4)


def _pluck(f, rng):  # santur-like: two slightly detuned bright strings, fast decay
    t = np.arange(int(1.6 * SR)) / SR
    out = np.zeros_like(t)
    for det in (0.0, 0.004):
        ff = f * (1 + det)
        for h in range(1, 7):
            out += np.sin(2 * np.pi * ff * h * t + rng.uniform(0, 6.28)) * np.exp(-t * (3.0 + 1.6 * h)) / h
    return out * _fade(len(t), 0.002, 0.2) * 0.6


def _drum(low=True):  # frame drum: pitched body + skin noise, audible on phones (90-400 Hz + slap)
    t = np.arange(int(0.45 * SR)) / SR
    f = (95 if low else 170) * (1 + 0.6 * np.exp(-t * 30))
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * (9 if low else 14))
    slap = np.random.default_rng(7).standard_normal(len(t)) * np.exp(-t * 60) * 0.25
    return (body + _hp(slap, 900)) * _fade(len(t), 0.001, 0.05)


def _heart():
    t = np.arange(int(0.3 * SR)) / SR
    f = 75 * (1 + 0.8 * np.exp(-t * 40))
    beat = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.5 * np.sin(4 * np.pi * np.cumsum(f) / SR)
    return beat * np.exp(-t * 16) * _fade(len(t), 0.002, 0.05)


def _noise_bed(n, rng, cutoff, low=120.0):
    x = rng.standard_normal(n)
    return _hp(_lp(x, cutoff), low)


# ---------------------------------------------------------------- moods
SETTINGS = {
    #          progression (semitones, minor)                      chord s  pad cut  notes: (gap lo, hi, level)
    "sea":     ([(0, True), (5, True), (3, False), (10, False)],    6.5,     800,     (1.8, 3.2, 0.13)),
    "crime":   ([(0, True), (1, True), (0, True), (6, True)],       5.0,     650,     (1.4, 2.6, 0.10)),
    "sky":     ([(0, False), (5, False), (7, False), (3, False)],   6.0,     1500,    (1.3, 2.4, 0.12)),
    "ancient": ([(0, True), (1, False), (0, True), (10, False)],    5.0,     900,     (0.45, 0.9, 0.16)),
    "vanish":  ([(0, True), (8, False), (5, True), (3, False)],     7.0,     600,     (2.6, 4.2, 0.12)),
}


def _build(seconds, seed, mood):
    rng = np.random.default_rng(seed)
    prog, chord_s, cut, (glo, ghi, nlev) = SETTINGS[mood]
    n_total = int(seconds * SR)
    L = np.zeros(n_total + int(3 * SR))
    R = np.zeros_like(L)
    parts = max(1, int(round(seconds / chord_s)))
    dur = seconds / parts
    key = int(rng.choice([45, 47, 48, 50]))
    xf = min(1.5, dur / 2)
    pad_level = {"vanish": 0.6, "crime": 0.8, "sky": 0.9}.get(mood, 1.0)
    for k in range(parts):
        lv = 0.55 + 0.45 * k / max(1, parts - 1)
        off, minor = prog[k % len(prog)]
        root = key + off
        third = 3 if minor else 4
        a = max(0, int((k * dur - xf / 2) * SR))
        b = min(len(L), int((k * dur + dur + xf / 2) * SR))
        n = b - a
        notes = [root, root + 7, root + 12, root + 12 + third]
        if mood == "sky":
            notes += [root + 14, root + 19]  # open, suspended colour
        elif mood != "vanish":
            notes += [root + 19]
        pad = np.zeros(n)
        for j, mm in enumerate(notes):
            pad += _pad(_hz(mm), n, rng, 5 if mood == "vanish" else 8) * (0.9 if j < 2 else 0.6)
        pad = _lp(pad * _fade(n, xf, xf) * (0.5 + 0.5 * lv) * pad_level, cut + 900 * lv)
        pan = (0.35 if mood == "sky" else 0.15) * np.sin(2 * np.pi * 0.07 * np.arange(n) / SR)
        L[a:b] += pad * (1 - pan)
        R[a:b] += pad * (1 + pan)
        tones = [root + 12, root + 19, root + 24, root + 24 + third, root + 31]
        if mood == "crime":
            tones = [root + 12, root + 13, root + 19, root + 24]
        pos = k * dur + 0.6
        while pos < k * dur + dur - 0.7:
            f = _hz(int(rng.choice(tones)))
            if mood == "ancient":
                sig = _pluck(f, rng) * (nlev + 0.06 * lv)
            else:
                sig = _piano(f, 3.6 if mood == "vanish" else 2.8, 1.6 if mood == "vanish" else 2.4) * (nlev + 0.08 * lv)
            _add(L, R, sig, pos, float(rng.uniform(-0.4, 0.4)))
            pos += float(rng.uniform(glo, ghi) - (0.25 if mood != "vanish" else 0.0) * lv)
    n = len(L)
    t = np.arange(n) / SR
    if mood == "sea":  # waves: filtered noise that breathes every ~7 s
        for ch, shift in ((L, 0.0), (R, 1.3)):
            swell = 0.5 - 0.5 * np.cos(2 * np.pi * (t + shift) / 7.0)
            ch += 0.55 * _noise_bed(n, rng, 650) * swell ** 1.5
    elif mood == "crime":  # heartbeat, a little faster towards the end
        heart, pos = _heart(), 0.8
        while pos < seconds - 0.5:
            lv = 0.6 + 0.4 * pos / seconds
            _add(L, R, heart * 0.55 * lv, pos)
            _add(L, R, heart * 0.35 * lv, pos + 0.24)
            pos += 1.05 - 0.2 * pos / seconds
    elif mood == "sky":  # high shimmer with slow tremolo, wide
        for ch, ph in ((L, 0.0), (R, 1.7)):
            sh = np.zeros(n)
            for mm in (key + 36, key + 43, key + 48):
                sh += np.sin(2 * np.pi * _hz(mm) * t + ph)
            ch += 0.05 * sh * (0.6 + 0.4 * np.sin(2 * np.pi * 0.23 * t + ph))
    elif mood == "ancient":  # frame drum pattern
        low, high = _drum(True), _drum(False)
        pattern = [(0.0, low, 0.9), (0.75, high, 0.45), (1.125, high, 0.35), (1.5, low, 0.7), (2.25, high, 0.45)]
        start = 1.0
        while start < seconds - 0.5:
            lv = 0.6 + 0.4 * start / seconds
            for off, hit, amp in pattern:
                _add(L, R, hit * amp * lv * 0.8, start + off, 0.1 if hit is high else 0.0)
            start += 3.0
    elif mood == "vanish":  # soft wind
        for ch, shift in ((L, 0.0), (R, 2.1)):
            gust = 0.6 + 0.4 * np.sin(2 * np.pi * (t + shift) / 9.0)
            ch += 0.18 * _noise_bed(n, rng, 1800, 400) * gust
    st = np.stack([L, R], axis=1)
    st = _reverb(st, rng, {"sky": 3.6, "vanish": 3.2, "sea": 3.0}.get(mood, 2.4),
                 {"sky": 0.45, "vanish": 0.42}.get(mood, 0.34))
    out = st[:n_total]
    out = np.tanh(1.4 * out / (np.max(np.abs(out)) or 1)) / np.tanh(1.4)
    env = _fade(n_total, min(1.0, seconds / 4), min(1.5, seconds / 4))
    return out * env[:, None]


def score(seconds: float, seed: int, mood: str | None = None):
    """Stereo float (n, 2) for this story's mood, or None when the story is unknown."""
    mood = mood or mood_for_seed(seed)
    if mood not in SETTINGS:
        return None
    return _build(seconds, seed, mood)
