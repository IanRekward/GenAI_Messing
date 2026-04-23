"""
Threshold evaluation: annotates every indicator and bucket with its stress band.
"""
from __future__ import annotations

_BAND_ORDER = {"green": 0, "yellow": 1, "orange": 2, "red": 3}


def _evaluate_band(raw: float | None, thr: dict) -> str:
    if raw is None:
        return "green"
    direction = thr.get("direction", "high")
    if direction == "high":
        if raw >= thr["red"]:
            return "red"
        if raw >= thr["orange"]:
            return "orange"
        if raw >= thr["yellow"]:
            return "yellow"
    else:  # low: smaller value = more stress
        if raw <= thr["red"]:
            return "red"
        if raw <= thr["orange"]:
            return "orange"
        if raw <= thr["yellow"]:
            return "yellow"
    return "green"


def _score_band(score: float) -> str:
    if score >= 70:
        return "red"
    if score >= 50:
        return "orange"
    if score >= 30:
        return "yellow"
    return "green"


def annotate_results(scoring: dict, thresholds: dict) -> dict:
    """
    Walk every indicator, assign its band from raw-value thresholds (falling back
    to score-based bands when no threshold exists), then roll up to bucket bands
    and recompute composite_band from actual trigger counts.
    """
    ind_thresholds = thresholds.get("indicators", {})
    red = orange = yellow = 0

    for bucket in scoring["buckets"].values():
        bucket_worst = "green"

        for ikey, ind in bucket["indicators"].items():
            thr = ind_thresholds.get(ikey)
            band = (
                _evaluate_band(ind["raw"], thr)
                if thr
                else _score_band(ind.get("score", 50.0))
            )
            ind["band"] = band

            if band == "red":
                red += 1
            elif band == "orange":
                orange += 1
            elif band == "yellow":
                yellow += 1

            if _BAND_ORDER.get(band, 0) > _BAND_ORDER.get(bucket_worst, 0):
                bucket_worst = band

        bucket["band"] = bucket_worst

    scoring["red_count"] = red
    scoring["orange_count"] = orange
    scoring["yellow_count"] = yellow

    composite = scoring["composite"]
    if red >= 3 or composite >= 70:
        scoring["composite_band"] = "red"
    elif red >= 1 or orange >= 3 or composite >= 50:
        scoring["composite_band"] = "orange"
    elif orange >= 1 or yellow >= 3 or composite >= 30:
        scoring["composite_band"] = "yellow"
    else:
        scoring["composite_band"] = "green"

    return scoring
