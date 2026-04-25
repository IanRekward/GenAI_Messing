"""
Config validation — raises ConfigError at startup on any schema drift.

Validates:
- Bucket weights sum to 1.0
- Indicator weights per bucket sum to 1.0
- Every indicator key in weights.yaml has a handler in scoring.py
- Every key in thresholds.yaml references an indicator that exists in weights.yaml
- No indicator key appears in more than one bucket

Call validate_config() from run_dashboard.py before any data fetching.
"""
from __future__ import annotations


class ConfigError(Exception):
    """Raised when weights.yaml, thresholds.yaml, or scoring.py have drifted."""


# Canonical set of indicator keys that _fetch_indicator() handles.
# Update this when adding a new indicator to scoring.py.
KNOWN_INDICATOR_KEYS: frozenset[str] = frozenset({
    "vix", "sp500_1m_vol", "vix_term_structure",
    "hy_oas", "ig_oas",
    "yield_curve", "ten_year", "move_index",
    "nfci", "stlfsi",
    "breakeven_5y", "cpi_yoy",
    "sofr_spread",
    "wti_crude", "oil_vol",
    "jobless_claims", "unemployment",
    "usd_index", "euro_hy_oas", "em_corp_oas", "eem_vol",
    "cnn_fear_greed",
    "treasury_auction_stress",
    "sector_breadth", "spx_200dma_distance",
    # manual-only indicators (no fetch handler needed)
    "repo_stress", "iran_trigger",
})

_WEIGHT_TOLERANCE = 1e-4
_MIN_BUCKETS = 11  # expected bucket count; raises if a bucket is silently removed

_VALID_SOURCE_TYPES = frozenset({"yfinance", "fred", "computed", "manual"})
_VALID_TRANSFORMS = frozenset({"realized_vol_series", "yoy_series"})


def validate_config(weights: dict, thresholds: dict,
                    computed_handlers: "frozenset[str] | None" = None) -> None:
    """
    Validate that weights.yaml and thresholds.yaml are internally consistent
    and that every indicator key has a known handler.

    Raises ConfigError with a specific message naming the offending field.
    """
    _validate_bucket_count(weights)
    _validate_bucket_weights(weights)
    _validate_indicator_keys(weights)
    _validate_no_duplicate_keys(weights)
    _validate_threshold_keys(weights, thresholds)
    _validate_sources(weights, computed_handlers or frozenset())


def _validate_bucket_count(weights: dict) -> None:
    n = len(weights.get("buckets", {}))
    if n < _MIN_BUCKETS:
        raise ConfigError(
            f"config/weights.yaml has {n} bucket(s) but expected at least "
            f"{_MIN_BUCKETS}. A bucket may have been accidentally removed. "
            f"If you intentionally reduced the bucket count, update "
            f"_MIN_BUCKETS in src/config.py."
        )


def _validate_bucket_weights(weights: dict) -> None:
    buckets = weights.get("buckets", {})
    if not buckets:
        raise ConfigError("weights.yaml has no 'buckets' key")

    bucket_sum = sum(float(b["weight"]) for b in buckets.values())
    if abs(bucket_sum - 1.0) > _WEIGHT_TOLERANCE:
        raise ConfigError(
            f"Bucket weights sum to {bucket_sum:.6f}, expected 1.0 ± {_WEIGHT_TOLERANCE}. "
            f"Adjust bucket weights in config/weights.yaml."
        )

    for bkey, bcfg in buckets.items():
        ind_weights = bcfg.get("indicators", {})
        if not ind_weights:
            raise ConfigError(f"Bucket '{bkey}' has no indicators")
        ind_sum = sum(float(i["weight"]) for i in ind_weights.values())
        if abs(ind_sum - 1.0) > _WEIGHT_TOLERANCE:
            raise ConfigError(
                f"Indicator weights in bucket '{bkey}' sum to {ind_sum:.6f}, "
                f"expected 1.0 ± {_WEIGHT_TOLERANCE}."
            )


def _validate_indicator_keys(weights: dict) -> None:
    for bkey, bcfg in weights["buckets"].items():
        for ikey in bcfg.get("indicators", {}):
            if ikey not in KNOWN_INDICATOR_KEYS:
                raise ConfigError(
                    f"Indicator '{ikey}' in bucket '{bkey}' has no fetch handler "
                    f"in src/scoring.py. Add it to _fetch_indicator() and to "
                    f"KNOWN_INDICATOR_KEYS in src/config.py."
                )


def _validate_no_duplicate_keys(weights: dict) -> None:
    seen: dict[str, str] = {}
    for bkey, bcfg in weights["buckets"].items():
        for ikey in bcfg.get("indicators", {}):
            if ikey in seen:
                raise ConfigError(
                    f"Indicator key '{ikey}' appears in both bucket "
                    f"'{seen[ikey]}' and '{bkey}'. Keys must be unique."
                )
            seen[ikey] = bkey


def _validate_sources(weights: dict, computed_handlers: frozenset) -> None:
    for bkey, bcfg in weights["buckets"].items():
        for ikey, icfg in bcfg.get("indicators", {}).items():
            src = icfg.get("source")
            if src is None:
                raise ConfigError(
                    f"Indicator '{ikey}' in bucket '{bkey}' is missing a 'source:' field. "
                    f"Add source.type (yfinance/fred/computed/manual) to config/weights.yaml."
                )
            stype = src.get("type")
            if stype not in _VALID_SOURCE_TYPES:
                raise ConfigError(
                    f"Indicator '{ikey}' has unknown source type '{stype}'. "
                    f"Must be one of: {sorted(_VALID_SOURCE_TYPES)}."
                )
            if stype == "yfinance" and not src.get("ticker"):
                raise ConfigError(
                    f"Indicator '{ikey}' source type 'yfinance' requires a 'ticker' field."
                )
            if stype == "fred" and not src.get("series_id"):
                raise ConfigError(
                    f"Indicator '{ikey}' source type 'fred' requires a 'series_id' field."
                )
            if stype == "computed":
                handler = src.get("handler")
                if not handler:
                    raise ConfigError(
                        f"Indicator '{ikey}' source type 'computed' requires a 'handler' field."
                    )
                if computed_handlers and handler not in computed_handlers:
                    raise ConfigError(
                        f"Indicator '{ikey}' references computed handler '{handler}' "
                        f"which is not registered in scoring.COMPUTED_HANDLERS."
                    )
            transform = src.get("transform")
            if transform and transform not in _VALID_TRANSFORMS:
                raise ConfigError(
                    f"Indicator '{ikey}' has unknown transform '{transform}'. "
                    f"Must be one of: {sorted(_VALID_TRANSFORMS)}."
                )


def _validate_threshold_keys(weights: dict, thresholds: dict) -> None:
    all_indicator_keys: set[str] = {
        ikey
        for bcfg in weights["buckets"].values()
        for ikey in bcfg.get("indicators", {})
    }
    for tkey in thresholds.get("indicators", {}):
        if tkey not in all_indicator_keys:
            raise ConfigError(
                f"Threshold entry '{tkey}' in config/thresholds.yaml does not "
                f"match any indicator in config/weights.yaml. "
                f"Possible typo — check the key name."
            )
