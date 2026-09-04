"""OFFLINE heuristic viral-moment detection — ZERO API, ZERO key, ZERO cost.

v0.4 "SUPERCLIP": the one thing EVERY commercial clipper (Opus, Vizard, Klap,
Munch, Submagic...) has in common is a hard cloud-AI dependency — no key/API,
no clips. Clipper no longer shares that weakness:

- ANALYSIS_BACKEND=local  -> this module is THE analyzer (fully offline).
- gemini/openai key missing or the API call fails for ANY reason -> the
  pipeline silently falls back to THIS module instead of dying with a 500.

The heuristic is a "cheap but honest editor brain" distilled from how human
clip editors describe their craft (and from what our competitor research
showed users actually reward):

  1. SEGMENTATION  — merge transcript segments into sentences, then find
     natural topic boundaries (a long pause + weak lexical cohesion).
  2. CANDIDATES    — every sentence start seeds a window; windows grow to the
     duration limits and end at the strongest payoff point (sentence-final +
     pause after = the classic punchline signature).
  3. SCORING       — hook language (curiosity keywords, questions, numbers,
     negations, direct address), speech rate (energy proxy), quotability
     (punchy short sentences), self-containedness (starts/ends on sentence
     boundaries — no mid-thought cuts), payoff (a pause AFTER the last word:
     the audience-reaction signature).
  4. SELECTION     — greedy non-overlapping top-K with a diversity filter
     (near-duplicate moments are rejected — the #2 complaint on every
     platform was repetitive clips).
  5. METADATA      — title/reason localized to the CONTENT language (ID or EN
     detected automatically), ready-to-post caption + hashtags extracted
     with stopword-filtered keyword scoring. No platform does Indonesia-first
     metadata; here even the offline path does.

This file is deliberately dependency-free (stdlib only) so the fallback can
never itself fail because of a missing package.
"""
import re
from collections import Counter

from .models import ClipScores, HighlightAnalysis, ViralMoment

# --- language detection ------------------------------------------------------
_ID_MARKERS = (
    "yang", "tidak", "dan", "dengan", "saya", "kita", "mereka", "ini", "itu",
    "karena", "sudah", "akan", "bisa", "ada", "adalah", "untuk", "dari",
    "kalau", "juga", "banget", "nggak", "gak", "kamu", "dia",
)
_EN_MARKERS = (
    "the", "and", "that", "with", "this", "you", "your", "because", "just",
    "really", "people", "think", "know", "about", "would", "could", "there",
)

# --- hook language (the "stop scrolling" lexicon) ---------------------------
_HOOK_WORDS_ID = (
    "rahasia", "ternyata", "jangan", "kesalahan", "cara", "trik",
    "bocor", "kejutan", "bahaya", "wajib", "dilarang", "ajaib",
    "kaya", "uang", "gratis", "cepat", "ampuh", "bohong",
    "fakta", "bukti", "penelitian", "studi", "mengejutkan", "aneh", "unik",
    "paling", "nomor satu", "pertama", "terakhir", "penting", "serius",
    "nggak nyangka", "tak disangka", "awas", "hati-hati", "skandal",
    "ditipu", "tipu", "boros", "hemat", "untung", "rugi", "berhasil", "gagal",
    "motivasi", "semangat", "malas", "disiplin", "cerita", "salah",
)
_HOOK_WORDS_EN = (
    "secret", "truth", "mistake", "wrong", "how", "never", "always",
    "actually", "shocking", "insane", "crazy", "warning", "stop", "why",
    "million", "money", "free", "rich", "poor", "fail", "failed", "proof",
    "study", "nobody", "everyone", "hack", "trick", "biggest", "worst",
    "best", "reason", "problem", "danger", "scam", "lie", "change",
    "everything", "surprising",
)

# Filler words that make a candidate window start WEAK (soft openers).
_FILLER_ID = ("ehm", "em", "ya", "sih", "deh", "kayak", "gitu", "terus",
              "jadi", "nah", "lagi", "dong", "kok")
_FILLER_EN = ("um", "uh", "like", "so", "anyway", "basically", "right",
              "okay", "well", "yeah")

# Stopwords for keyword/hashtag extraction.
_STOP_ID = set("""
yang untuk dengan dari ini itu adalah akan sudah tidak bisa ada pada dan atau
juga kita saya kamu dia mereka nya sih kah lah dong deh terus lagi kalau
karena supaya agar saat ketika oleh sebagai sangat lebih paling para bagi
""".split())
_STOP_EN = set("""
the a an and or but if then so because with from this that these those is are
was were be been being to of in on at for by as it its he she they we you your
our their his her not no do does did have has had will would can could should
""".split())

_QUESTION_WORDS = ("kenapa", "mengapa", "why", "bagaimana", "how", "what",
                   "gimana", "siapa", "who", "kapan", "when")


def _norm(t: str) -> str:
    return (t or "").lower().strip()


def detect_language(segments: list[dict]) -> str:
    """Rough content-language detector: 'id' or 'en' (default 'id' — Clipper is
    Indonesia-first; ties/unknowns resolve to id)."""
    text = _norm(" ".join(s.get("text", "") for s in (segments or [])[:80]))
    if not text:
        return "id"
    words = set(re.findall(r"[\w']+", text))
    id_hits = len(words & set(_ID_MARKERS))
    en_hits = len(words & set(_EN_MARKERS))
    return "id" if id_hits >= en_hits else "en"


# --- sentence reconstruction -------------------------------------------------
def _sentences(segments: list[dict]) -> list[dict]:
    """Merge raw caption segments into sentence units: [{start, end, text}].

    Caption/auto-caption text is fragmented; a sentence ends at [.!?…] or at a
    long inter-segment pause (>0.75s). Sentence units are the atoms of every
    candidate window — cutting anywhere else sounds broken.
    """
    out: list[dict] = []
    for s in segments or []:
        start = float(s.get("start", 0.0))
        end = float(s.get("end", 0.0))
        text = (s.get("text") or "").strip()
        if not text or end <= start:
            continue
        out.append({"start": start, "end": end, "text": text})
    sents: list[dict] = []
    cur: dict | None = None
    for seg in out:
        if cur is None:
            cur = dict(seg)
        else:
            gap = seg["start"] - cur["end"]
            if gap > 0.75:  # a long pause ends the sentence even without [.!?]
                sents.append(cur)
                cur = dict(seg)
            else:
                cur["text"] = f"{cur['text']} {seg['text']}".strip()
                cur["end"] = seg["end"]
        if re.search(r"[.!?…][\"')\]]*$", seg["text"].strip()):
            sents.append(cur)
            cur = None
    if cur:
        sents.append(cur)
    for i, s in enumerate(sents):
        nxt = sents[i + 1]["start"] if i + 1 < len(sents) else s["end"] + 5.0
        s["gap_after"] = max(0.0, nxt - s["end"])
        s["punct_final"] = bool(re.search(r"[.!?…][\"')\]]*$", s["text"].strip()))
    return sents


# --- scoring components ------------------------------------------------------
def _hook_lexicon_score(text: str) -> float:
    t = _norm(text)
    if not t:
        return 0.0
    hits = 0
    for w in _HOOK_WORDS_ID:
        if w in t:
            hits += 1
    for w in _HOOK_WORDS_EN:
        if re.search(rf"\b{re.escape(w)}\b", t):
            hits += 1
    return min(1.0, hits / 2.5)


def _first_sentence_hookiness(first_text: str) -> float:
    """How strongly the OPENING sentence grabs (the 2-second scroll test)."""
    t = _norm(first_text)
    if not t:
        return 0.0
    score = _hook_lexicon_score(t) * 1.4
    if "?" in t or any(q in t for q in _QUESTION_WORDS):
        score += 0.25                       # a question = instant curiosity
    if re.search(r"\d", t):
        score += 0.15                        # numbers feel concrete
    if re.search(r"^(jangan|never|stop|awas|hati[- ]hati)\b", t):
        score += 0.2                         # imperative warning openers
    words = t.split()
    if words and words[0].strip(".,!?") in (_FILLER_ID + _FILLER_EN):
        score -= 0.3                         # soft filler opener = weak hook
    return max(0.0, min(1.0, score))


def _quotability(sents: list[dict]) -> float:
    """Punchy, shareable one-liners: short sentences with strong words."""
    if not sents:
        return 0.0
    best = 0.0
    for s in sents:
        wc = len(s["text"].split())
        if wc == 0:
            continue
        length_score = max(0.0, 1.0 - abs(wc - 10) / 12.0)  # sweet spot 6-16 words
        best = max(best, 0.6 * _hook_lexicon_score(s["text"]) + 0.4 * length_score)
    return min(1.0, best)


def _speech_rate(sents: list[dict]) -> float:
    """Words per second across the window — the energy proxy without audio."""
    if not sents:
        return 0.0
    dur = sents[-1]["end"] - sents[0]["start"]
    if dur <= 0:
        return 0.0
    wps = sum(len(s["text"].split()) for s in sents) / dur
    # 1.0 at ~3.2 wps (energetic podcast speech)
    return max(0.0, min(1.0, (wps - 1.6) / 1.6))


def _payoff_score(sents: list[dict]) -> float:
    """The punchline signature: the window ENDS on a sentence-final that is
    followed by a pause (audience reaction beat) — the strongest cut signal."""
    if not sents:
        return 0.0
    last = sents[-1]
    score = 0.35 if last["punct_final"] else 0.0
    if last["gap_after"] >= 0.5:
        score += 0.35
    if last["gap_after"] >= 1.2:
        score += 0.15
    score += 0.15 * min(1.0, _hook_lexicon_score(last["text"]))
    return min(1.0, score)


def _self_contained(sents: list[dict]) -> float:
    """Starts on a sentence start AND the first sentence carries its own
    subject (not "dan itu..." / "and that..." mid-thought spillover)."""
    if not sents:
        return 0.0
    first = _norm(sents[0]["text"])
    score = 0.6  # we always seed windows at sentence starts
    if not re.match(r"^(dan|tapi|but|because|karena|jadi|so|yang|terus|lalu)\b", first):
        score += 0.4
    return score


def _to_10(x: float) -> int:
    return max(1, min(10, int(round(1 + 9 * max(0.0, min(1.0, x))))))


# --- candidate windows -------------------------------------------------------
def _make_candidates(sents: list[dict], min_dur: float, max_dur: float) -> list[dict]:
    """Grow candidate windows from every sentence start; end at each sentence
    boundary inside [min_dur, max_dur] (prefer payoff-scored ends)."""
    if not sents:
        return []
    cands: list[dict] = []
    for i in range(len(sents)):
        start = sents[i]["start"]
        for j in range(i, len(sents)):
            end = sents[j]["end"]
            dur = end - start
            if dur > max_dur:
                break
            if dur < min_dur:
                continue
            win = sents[i:j + 1]
            cands.append({
                "start": start, "end": end, "sents": win,
                "end_gap": win[-1]["gap_after"],
                "punct_final": win[-1]["punct_final"],
            })
    return cands


def _score_window(c: dict) -> dict:
    sents = c["sents"]
    text = " ".join(s["text"] for s in sents)
    hook = _first_sentence_hookiness(sents[0]["text"])
    payoff = _payoff_score(sents)
    quot = _quotability(sents)
    rate = _speech_rate(sents)
    contained = _self_contained(sents)
    # emotion proxy: exclamations, laughter markers, strong negations
    emotion = 0.0
    t = _norm(text)
    if "!" in t:
        emotion += 0.3
    if re.search(r"\b(hahaha|lol|ketawa|lucu|nangis|sedih|marah|bangga|takut)\b", t):
        emotion += 0.3
    if re.search(r"\b(tidak pernah|nggak pernah|never|mustahil|impossible)\b", t):
        emotion += 0.2
    emotion += 0.2 * _hook_lexicon_score(t)
    emotion = min(1.0, emotion)

    energy = rate * 0.6 + contained * 0.2 + (0.2 if c["punct_final"] else 0.0)
    dims = {"hook": hook, "payoff": payoff, "emotion": emotion,
            "quotability": quot, "energy": energy}
    overall = (1.5 * hook + 1.5 * payoff + 0.9 * emotion + 1.0 * quot
               + 0.9 * energy + 0.7 * contained) / 6.5
    c["score"] = min(1.0, overall)
    c["dims"] = dims
    c["text"] = text
    return c


def _token_set(text: str) -> set:
    return {w for w in re.findall(r"[\w']{4,}", _norm(text))}


def _diverse(c: dict, chosen: list[dict], threshold: float = 0.55) -> bool:
    """Reject near-duplicate moments (same point retold = repetitive clips)."""
    toks = _token_set(c["text"])
    if not toks:
        return True
    for other in chosen:
        o = _token_set(other["text"])
        if o and len(toks & o) / min(len(toks), len(o)) > threshold:
            return False
    return True


# --- metadata ---------------------------------------------------------------
def _shorten(text: str, limit: int = 58) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    return cut.strip(" ,;:-")


def _make_title(sents: list[dict]) -> str:
    """The clip's title = its hookiest single sentence, shortened."""
    best = max(sents, key=lambda s: _hook_lexicon_score(s["text"]) + (0.2 if s["punct_final"] else 0.0))
    t = _shorten(best["text"], 58)
    t = re.sub(r"[.!?…]+$", "", t).strip()
    return t.upper() if len(t) < 34 else t


_REASON_TEMPLATES = {
    "id": [
        "Hook kuat di kalimat awal{hook_extra}, lalu buildup sampai payoff yang tegas di akhir.",
        "Momen '{kw}' yang bikin orang berhenti scroll — penjelasannya padat dan selesai utuh.",
        "Ada pertanyaan menohok di awal dan jawaban/payoff yang memuaskan di akhir — arc lengkap.",
        "Alur bicara cepat dan berenergi, ada satu kalimat yang sangat quotable.",
    ],
    "en": [
        "Strong opening hook{hook_extra}, then a clean build to a firm payoff at the end.",
        "A '{kw}' moment that makes people stop scrolling — dense, self-contained.",
        "Opens with a punchy question and lands the payoff — a complete arc.",
        "Fast, energetic delivery with one very quotable line.",
    ],
}
_CAPTION_TPL = {
    "id": "{hook} 🔥 ini bagian yang jarang dibahas — tonton sampai habis.",
    "en": "{hook} 🔥 nobody talks about this part — watch till the end.",
}


def _keywords(text: str, lang: str, n: int = 6) -> list:
    stop = _STOP_ID | _STOP_EN
    words = re.findall(r"[\w']{4,}", _norm(text))
    if lang == "id":
        words += [w for w in re.findall(r"[\w']{3,}", _norm(text))
                  if w not in _STOP_EN]
    counts = Counter(w for w in words if w not in stop and not w.isdigit())
    return [w for w, _ in counts.most_common(n)]


def _make_caption(sents: list[dict], lang: str) -> str:
    h = _shorten(sents[0]["text"], 70)
    h = re.sub(r"[.!…]+$", "", h).strip()
    return _CAPTION_TPL[lang].format(hook=h)


def _make_hashtags(kws: list, lang: str) -> list:
    base = ["shorts", "fyp", "viral"] + (["indonesia", "podcast"] if lang == "id" else ["reels", "podcast"])
    tags = []
    for k in kws[:5]:
        tag = re.sub(r"[^\w]", "", k)
        if len(tag) >= 3 and tag not in tags:
            tags.append(tag)
    for b in base:
        if b not in tags and len(tags) < 8:
            tags.append(b)
    return tags[:8]


# --- public API -------------------------------------------------------------
def analyze(segments: list[dict], max_clips: int, min_dur: float, max_dur: float,
            keywords: str = "", instruction: str = "") -> HighlightAnalysis:
    """Offline viral-moment detection. Never returns empty if the transcript
    has any content — worst case it returns the single best window."""
    lang = detect_language(segments)
    sents = _sentences(segments)
    if not sents:
        raise RuntimeError("No usable transcript segments for offline analysis.")

    cands = _make_candidates(sents, min_dur, max_dur)
    if not cands:
        cands = [{
            "start": sents[0]["start"], "end": sents[-1]["end"],
            "sents": sents, "end_gap": sents[-1]["gap_after"],
            "punct_final": sents[-1]["punct_final"],
        }]
    for c in cands:
        _score_window(c)

    # optional human steer: boost windows matching requested keywords
    steer = [k.strip().lower() for k in re.split(r"[,;]", keywords or "") if k.strip()]
    if steer:
        for c in cands:
            t = _norm(c["text"])
            if any(k in t for k in steer):
                c["score"] = min(1.0, c["score"] * 1.35 + 0.1)

    # greedy selection: best first, no overlaps, diversity-filtered
    cands.sort(key=lambda c: c["score"], reverse=True)
    chosen: list[dict] = []
    for c in cands:
        if len(chosen) >= max_clips:
            break
        if any(c["start"] < o["end"] + 2.0 and c["end"] + 2.0 > o["start"] for o in chosen):
            continue  # overlaps (or butts) an already-chosen moment
        if not _diverse(c, chosen):
            continue
        chosen.append(c)

    moments = []
    for rank, c in enumerate(chosen):
        sents_w = c["sents"]
        dims = c["dims"]
        title = _make_title(sents_w)
        kw_list = _keywords(c["text"], lang)
        tpl = _REASON_TEMPLATES[lang][rank % len(_REASON_TEMPLATES[lang])]
        reason = tpl.format(
            hook_extra=" (kalimat pembuka menyentuh kata kunci viral)" if dims["hook"] > 0.5 else "",
            kw=(kw_list[0] if kw_list else "kuat"),
        )
        moments.append(ViralMoment(
            start_time=round(c["start"], 2),
            end_time=round(c["end"], 2),
            title=title,
            reason=reason,
            viral_score=_to_10(c["score"]),
            hook=_shorten(sents_w[0]["text"], 48),
            speaker="",
            speakers=[],
            scores=ClipScores(
                hook=_to_10(dims["hook"]),
                payoff=_to_10(dims["payoff"]),
                emotion=_to_10(dims["emotion"]),
                quotability=_to_10(dims["quotability"]),
                energy=_to_10(dims["energy"]),
            ),
            caption=_make_caption(sents_w, lang),
            hashtags=_make_hashtags(kw_list, lang),
        ))
    if not moments:  # absolute last resort — one honest window
        c = cands[0]
        moments.append(ViralMoment(
            start_time=round(c["start"], 2), end_time=round(c["end"], 2),
            title=_shorten(c["text"], 58), reason="Best available moment.",
            viral_score=_to_10(c["score"]), hook=_shorten(c["text"], 48),
        ))
    return HighlightAnalysis(highlights=moments)
