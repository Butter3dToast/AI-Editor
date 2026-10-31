"""Your taste (Phase 3A-2): a score per game, learned from the clips you rated.

Spec section 7.10: "periodically fit a small model per game on accepted versus
rejected clips". A logistic regression, fitted here with numpy (no
scikit-learn to install), on a handful of things about each clip:

- the usual score (it already knows kills, laughter, your marks...),
- a kill and a multikill from League's game info, a Shorts mark (Numpad -),
- how long the moment is, and how much talking there is per second.

Tried on the creator's 424 League ratings on 24 Oct, each stream predicted
from the others: the usual score put a liked clip above a disliked one 70% of
the time, this 74%. What it adds is "lots of talking without action is less
likely to be liked" (chill 12% liked, banter 26%, a multikill 96%). Every
other measurement and the local AI's tags added nothing on top.

The safety net: each time a game's model is learned, the same test runs, and
the model is only used where it beats the usual score. It's learned again
after every RELEARN_EVERY new ratings, so it can switch itself off again.

It changes the order, never the scale: within a stream, the clip it likes
best gets the best usual score there, the next one the next best, and so on.
So the quality bar lets through as many clips as before, picked by your taste.
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

import numpy as np

from ..config import Settings

MIN_RATINGS = 30      # per game, before there's anything to learn from
MIN_STREAMS = 3       # streams with a 👍 and a 👎 each, to test it fairly
RELEARN_EVERY = 20    # new ratings
STRENGTH = 50.0       # how firmly it's held back from trusting few ratings (L2)
FEATURES = ("usual score", "kill", "multikill", "Shorts mark", "length", "talking")
# The model's layout: 2 holds a second model with the AI's rating (3A-3b).
VERSION = 2


def ai_ratings(conn: sqlite3.Connection, clips: Sequence[sqlite3.Row]) -> dict[str, float]:
    """The local AI's rating of each clip, where it was made with the creator's own
    verdicts as examples (3A-3b). Those made without them added nothing: tried on
    25 Oct, your taste with them 66.5%, without 66.7%; with examples, 69.6%."""
    from ..analysis.ai_rating import WITH_EXAMPLES, notes_for

    found: dict[str, float] = {}
    for rid in sorted({c["recording_id"] for c in clips}):
        mine = [c for c in clips if c["recording_id"] == rid]
        found.update({clip_id: n.rating for clip_id, n in notes_for(conn, rid, mine).items()
                      if n.prompt_version == WITH_EXAMPLES})
    return found


def features(clip: sqlite3.Row, ai: dict[str, float] | None = None) -> list[float]:
    """``ai``: with the AI's rating too (ai_ratings), for the model that uses it."""
    summary = json.loads(clip["signals_json"] or "{}")
    core = summary.get("core") or [clip["start_sec"], clip["end_sec"]]
    words = len((clip["transcript"] or "").split())
    return [float(clip["score"]),
            1.0 if summary.get("lol_kill") else 0.0,
            1.0 if summary.get("lol_multikill") else 0.0,
            1.0 if summary.get("marker_short") else 0.0,
            math.log(max(0.0, float(core[1]) - float(core[0])) + 1.0),
            words / max(1.0, clip["end_sec"] - clip["start_sec"])] + (
        [float(ai[clip["clip_id"]])] if ai is not None else [])


def clip_game(clip: sqlite3.Row, recording_game: str | None) -> str:
    return json.loads(clip["signals_json"] or "{}").get("game") or recording_game or "Other"


def _fit(x: np.ndarray, y: np.ndarray) -> dict:
    mu, sd = x.mean(0), x.std(0) + 1e-9
    z = np.hstack([(x - mu) / sd, np.ones((len(x), 1))])
    w = np.zeros(z.shape[1])
    hold = STRENGTH * np.diag(np.r_[np.ones(len(w) - 1), 0.0])   # never the constant
    for _ in range(100):   # Newton's method: a few steps are enough
        p = 1 / (1 + np.exp(-z @ w))
        step = np.linalg.solve((z * (p * (1 - p))[:, None]).T @ z + hold, z.T @ (p - y) + hold @ w)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return {"mu": mu.tolist(), "sd": sd.tolist(), "w": w.tolist()}


def _predict(model: dict, x: np.ndarray) -> np.ndarray:
    z = (x - np.array(model["mu"])) / np.array(model["sd"])
    w = np.array(model["w"])
    return 1 / (1 + np.exp(-(z @ w[:-1] + w[-1])))


def _above(liked: list[float], disliked: list[float]) -> float:
    """How often a liked clip is above a disliked one (ties count half)."""
    return sum(1.0 if a > b else 0.5 if a == b else 0.0
               for a in liked for b in disliked) / (len(liked) * len(disliked))


def _rated(conn: sqlite3.Connection, game: str) -> list[sqlite3.Row]:
    rows = conn.execute("SELECT clips.*, recordings.game AS recording_game FROM clips "
                        "JOIN recordings ON recordings.id = clips.recording_id "
                        "WHERE user_rating IS NOT NULL AND user_rating != 0").fetchall()
    return [r for r in rows if clip_game(r, r["recording_game"]) == game]


def check(rated: Sequence[sqlite3.Row],
          ai: dict[str, float] | None = None) -> tuple[float, float] | None:
    """(taste, usual): each stream ranked by a model learned from the others,
    as a new stream would be. None with too few streams to tell. ``ai``: the
    model with the AI's rating in it (every clip in ``rated`` must have one)."""
    streams = sorted({r["recording_id"] for r in rated})
    taste = usual = pairs = 0.0
    tested = 0
    for held in streams:
        test = [r for r in rated if r["recording_id"] == held]
        train = [r for r in rated if r["recording_id"] != held]
        liked = [r for r in test if r["user_rating"] > 0]
        disliked = [r for r in test if r["user_rating"] < 0]
        if not liked or not disliked or len({r["user_rating"] > 0 for r in train}) < 2:
            continue
        model = _fit(np.array([features(r, ai) for r in train]),
                     np.array([1.0 if r["user_rating"] > 0 else 0.0 for r in train]))
        mine = dict(zip([r["clip_id"] for r in test],
                        _predict(model, np.array([features(r, ai) for r in test]))))
        n = len(liked) * len(disliked)
        taste += n * _above([mine[r["clip_id"]] for r in liked],
                            [mine[r["clip_id"]] for r in disliked])
        usual += n * _above([r["score"] for r in liked], [r["score"] for r in disliked])
        pairs += n
        tested += 1
    return (taste / pairs, usual / pairs) if tested >= MIN_STREAMS else None


@dataclass
class Taste:
    game: str
    ratings: int
    model: dict | None          # None: too few ratings to learn from
    taste: float | None = None  # how often it puts a liked clip above a disliked one
    usual: float | None = None  # the same for the usual score
    learned_at: str = ""
    # With the AI's rating too (3A-3b): learned from the clips that have one, and
    # tested against the same model without it, on those same clips.
    ai_model: dict | None = None
    with_ai: float | None = None
    without_ai: float | None = None
    ai_clips: int = 0

    @property
    def better(self) -> bool:
        return self.model is not None and self.taste is not None and self.taste > self.usual

    @property
    def ai_helps(self) -> bool:
        return (self.ai_model is not None and self.with_ai is not None
                and self.with_ai > self.without_ai)

    def kept(self) -> dict | None:
        if self.model is None:
            return None
        return {"version": VERSION, "base": self.model, "ai": self.ai_model,
                "with_ai": self.with_ai, "without_ai": self.without_ai, "ai_clips": self.ai_clips}


def learn(conn: sqlite3.Connection, game: str) -> Taste:
    """Learn a game's taste from all its ratings, test it, and keep it."""
    rated = _rated(conn, game)
    found = Taste(game, len(rated), None,
                  learned_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    if len(rated) >= MIN_RATINGS and len({r["user_rating"] > 0 for r in rated}) == 2:
        found.model = _fit(np.array([features(r) for r in rated]),
                           np.array([1.0 if r["user_rating"] > 0 else 0.0 for r in rated]))
        tested = check(rated)
        if tested:
            found.taste, found.usual = tested
        ai = ai_ratings(conn, rated)
        rated_ai = [r for r in rated if r["clip_id"] in ai]
        found.ai_clips = len(rated_ai)
        if len(rated_ai) >= MIN_RATINGS and len({r["user_rating"] > 0 for r in rated_ai}) == 2:
            with_ai, without = check(rated_ai, ai), check(rated_ai)
            if with_ai and without:
                found.with_ai, found.without_ai = with_ai[0], without[0]
                found.ai_model = _fit(np.array([features(r, ai) for r in rated_ai]),
                                      np.array([1.0 if r["user_rating"] > 0 else 0.0
                                                for r in rated_ai]))
    kept = found.kept()
    conn.execute("INSERT OR REPLACE INTO taste_models (game, model_json, ratings, taste_check, "
                 "usual_check, learned_at) VALUES (?, ?, ?, ?, ?, ?)",
                 (game, json.dumps(kept) if kept else None, found.ratings,
                  found.taste, found.usual, found.learned_at))
    conn.commit()
    return found


def _games(conn: sqlite3.Connection) -> dict[str, int]:
    """Ratings per game."""
    counts: dict[str, int] = {}
    for r in conn.execute("SELECT clips.signals_json, recordings.game FROM clips "
                          "JOIN recordings ON recordings.id = clips.recording_id "
                          "WHERE user_rating IS NOT NULL AND user_rating != 0"):
        game = clip_game(r, r["game"])
        counts[game] = counts.get(game, 0) + 1
    return counts


def tastes(conn: sqlite3.Connection) -> dict[str, Taste]:
    """Every rated game's taste, learned again where RELEARN_EVERY ratings came in since."""
    kept = {r["game"]: r for r in conn.execute("SELECT * FROM taste_models")}
    found = {}
    for game, count in sorted(_games(conn).items()):
        row = kept.get(game)
        model = json.loads(row["model_json"]) if row and row["model_json"] else None
        if row is None or abs(count - row["ratings"]) >= RELEARN_EVERY or \
                (model is None and count >= MIN_RATINGS) or \
                (model is not None and model.get("version") != VERSION):
            found[game] = learn(conn, game)
        else:
            found[game] = Taste(game, row["ratings"], model["base"] if model else None,
                                row["taste_check"], row["usual_check"], row["learned_at"],
                                (model or {}).get("ai"), (model or {}).get("with_ai"),
                                (model or {}).get("without_ai"), (model or {}).get("ai_clips", 0))
    return found


def in_use(conn: sqlite3.Connection, settings: Settings) -> dict[str, Taste]:
    """{game: its taste} for the games where your taste is used to pick clips."""
    if not settings.learning.taste:
        return {}
    return {g: t for g, t in tastes(conn).items() if t.better}


def likes(conn: sqlite3.Connection, settings: Settings, clips: Sequence[sqlite3.Row],
          recording_game: str | None, models: dict[str, Taste] | None = None) -> dict[str, float]:
    """How likely you are to like each clip (0-1), where your taste is in use:
    with the AI's rating where the AI rated it with your examples and that helps."""
    models = in_use(conn, settings) if models is None else models
    found = {}
    for game, t in models.items():
        mine = [c for c in clips if clip_game(c, recording_game) == game]
        if not mine:
            continue
        ai = ai_ratings(conn, mine) if t.ai_helps else {}
        rated = [c for c in mine if c["clip_id"] in ai]
        plain = [c for c in mine if c["clip_id"] not in ai]
        if rated:
            found.update(zip([c["clip_id"] for c in rated], _predict(
                t.ai_model, np.array([features(c, ai) for c in rated])).tolist()))
        if plain:
            found.update(zip([c["clip_id"] for c in plain], _predict(
                t.model, np.array([features(c) for c in plain])).tolist()))
    return found


def reordered(scores: dict[str, float], liking: dict[str, float]) -> dict[str, float]:
    """The same scores, handed out in the order of your taste: the clip you'd
    most like gets the best score there is, and so on. Clips your taste doesn't
    cover keep their own."""
    mine = [c for c in scores if c in liking]
    by_taste = sorted(mine, key=lambda c: (-liking[c], -scores[c], c))
    values = sorted((scores[c] for c in mine), reverse=True)
    # Many clips share the top score (1.00): a millionth apart, your taste
    # settles the ties too, without moving anything past the quality bar.
    return {**scores, **{c: v - n * 1e-6 for n, (c, v) in enumerate(zip(by_taste, values))}}


def ranked(conn: sqlite3.Connection, settings: Settings | None, recording_id: int,
           ) -> tuple[list[sqlite3.Row], dict[str, float]]:
    """A recording's clips best first, as the Clips tab lists them and highlights
    pick them, and how likely you are to like each (where your taste is in use)."""
    rows = conn.execute("SELECT * FROM clips WHERE recording_id = ? ORDER BY score DESC, "
                        "start_sec", (recording_id,)).fetchall()
    if settings is None:
        return rows, {}
    game = conn.execute("SELECT game FROM recordings WHERE id = ?", (recording_id,)).fetchone()
    liking = likes(conn, settings, rows, game[0] if game else None)
    if not liking:
        return rows, {}
    order = reordered({r["clip_id"]: r["score"] for r in rows}, liking)
    return sorted(rows, key=lambda r: (-order[r["clip_id"]], r["start_sec"])), liking


def status_text(conn: sqlite3.Connection, settings: Settings) -> str:
    """For Settings: per game, how your taste does against the usual score."""
    lines = []
    for game, t in tastes(conn).items():
        if t.model is None:
            lines.append(f"- **{game}**: {t.ratings} rating{'s' if t.ratings != 1 else ''}; "
                         f"it starts learning at {MIN_RATINGS} (with some 👍 and some 👎).")
        elif t.taste is None:
            lines.append(f"- **{game}**: learned from {t.ratings} ratings, but they're from "
                         f"too few streams to test fairly ({MIN_STREAMS} with a 👍 and a 👎 "
                         "each). Until then, the usual score picks.")
        else:
            used = ("**in use**" if settings.learning.taste else "switched off below") \
                if t.better else "not used: the usual score does as well or better"
            line = (f"- **{game}**: your taste puts a clip you liked above one you didn't "
                    f"**{t.taste:.0%}** of the time, the usual score {t.usual:.0%} "
                    f"(from {t.ratings} ratings), {used}.")
            if t.with_ai is not None:
                line += (f" With the local AI's rating (made with your examples, on "
                         f"{t.ai_clips} of them): {t.with_ai:.0%} against {t.without_ai:.0%} "
                         "without, so " + ("it's used where the AI has rated a clip that way."
                                           if t.ai_helps else "it's left out."))
            elif t.ai_clips:
                line += (f" The local AI has rated {t.ai_clips} of them with your examples; "
                         f"at {MIN_RATINGS} its rating is tried in your taste too.")
            lines.append(line)
    if not lines:
        return "Nothing learned yet: rate some clips 👍, 🔖 or 👎 in the Clips tab."
    return "\n".join(lines) + (f"\n\nIt learns again after every {RELEARN_EVERY} new ratings, "
                               "and is only used where it beats the usual score.")
