"""Phase 2 MACRO sidecar consumer.

Reads `../market_dashboard/data/latest.json` (MACRO publishes daily ~07:30 ET).
Two-tier failure handling per architecture decision D6:
- Stale (run_timestamp > 4h old, content valid): degrade to neutral; trade full size.
- Broken (schema mismatch, weights_hash unknown, errors[] non-empty, etc.): block new entries.

Provenance gate (AR12): only weights_hash values in data/macro_weights_allowlist.json
are accepted. When MACRO ships a recalibration the new hash will fail until manually approved.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

MACRO_SIDECAR_PATH = Path(__file__).resolve().parent.parent.parent / "market_dashboard" / "data" / "latest.json"
ALLOWLIST_PATH = Path(__file__).resolve().parent.parent / "data" / "macro_weights_allowlist.json"
STALENESS_HOURS = 4
EXPECTED_SCHEMA_VERSION = 1


def _load_allowlist() -> tuple[bool, str, list[str] | None]:
    """Load the weights_hash allow-list. Returns (ok, reason, hashes)."""
    if not ALLOWLIST_PATH.exists():
        return False, "macro_weights_allowlist_missing", None
    try:
        with open(ALLOWLIST_PATH) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return False, f"macro_weights_allowlist_malformed: {e}", None
    hashes = data.get("allowed_hashes")
    if not isinstance(hashes, list):
        return False, "macro_weights_allowlist_missing_allowed_hashes", None
    return True, "ok", hashes


def validate() -> tuple[bool, str, dict | None]:
    """Story 1b.1 + 1b.2: Read + validate MACRO sidecar.

    Returns:
        (ok, reason, regime_data)

        - (True, "ok", regime_data) — file present, content valid, fresh, weights_hash known.
        - (True, "macro_stale_Xh_treating_as_neutral", regime_data_with_neutralized_flag) —
          file present, content valid, but >4h old. Callers should treat as neutral regime.
        - (False, "<reason>", None) — file missing, malformed, schema bumped, errors[] non-empty,
          composite out of range, weights_hash unknown, or allow-list missing/broken.

    The regime_data dict carries (at minimum): composite_band, regime, run_timestamp,
    weights_hash. When neutralized=True, callers should ignore band/regime semantics.
    """
    if not MACRO_SIDECAR_PATH.exists():
        return False, f"macro_file_missing: {MACRO_SIDECAR_PATH}", None

    try:
        with open(MACRO_SIDECAR_PATH) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return False, f"macro_file_malformed: {e}", None
    except OSError as e:
        return False, f"macro_file_read_error: {e}", None

    schema_version = data.get("schema_version")
    if schema_version != EXPECTED_SCHEMA_VERSION:
        return False, f"macro_schema_version_unexpected: {schema_version}", None

    errors = data.get("errors") or []
    # MACRO writes warnings as "STALE: ..." in errors[] for individual stale indicators.
    # Phase 2 architecture D6 says: "errors[] non-empty → block new entries."
    # But MACRO's own integration brief notes stale individual indicators are benign
    # (e.g., stale cpi_yoy is fine). For Phase 2 first ship we follow the strict spec
    # and block; Phase 2.1 can refine if STALE: entries prove tolerable.
    if errors:
        return False, f"macro_errors: {errors}", None

    composite = data.get("composite")
    if composite is None or not (0 <= composite <= 100):
        return False, f"macro_composite_out_of_range: {composite}", None

    if "composite_band" not in data or "regime" not in data:
        return False, "macro_required_fields_missing", None

    weights_hash = data.get("weights_hash")
    if not weights_hash:
        return False, "macro_weights_hash_missing", None

    allowlist_ok, allowlist_reason, allowed_hashes = _load_allowlist()
    if not allowlist_ok:
        return False, allowlist_reason, None
    if weights_hash not in allowed_hashes:
        return False, f"macro_weights_hash_unknown: {weights_hash}", None

    run_timestamp_str = data.get("run_timestamp")
    if not run_timestamp_str:
        return False, "macro_run_timestamp_missing", None
    try:
        run_ts = datetime.fromisoformat(run_timestamp_str)
        if run_ts.tzinfo is None:
            run_ts = run_ts.replace(tzinfo=timezone.utc)
    except ValueError as e:
        return False, f"macro_run_timestamp_malformed: {e}", None

    age = datetime.now(timezone.utc) - run_ts
    age_hours = age.total_seconds() / 3600

    regime_data = {
        "run_timestamp": run_timestamp_str,
        "composite_band": data["composite_band"],
        "regime": data["regime"],
        "weights_hash": weights_hash,
        "composite": composite,
        "neutralized": False,
    }

    if age_hours > STALENESS_HOURS:
        regime_data["neutralized"] = True
        return (
            True,
            f"macro_stale_{age_hours:.1f}h_treating_as_neutral",
            regime_data,
        )

    return True, "ok", regime_data


def size_multiplier(regime_data: dict) -> float:
    """Story 1b.3: Map regime data to a sizing multiplier per the policy table.

    Per architecture decision D5:
    - composite_band == "red"  →  0.0  (block new entries)
    - composite_band == "orange" AND regime == "high"  →  0.5
    - otherwise (incl. neutralized) → 1.0
    """
    if regime_data.get("neutralized"):
        return 1.0
    if regime_data.get("composite_band") == "red":
        return 0.0
    if regime_data.get("composite_band") == "orange" and regime_data.get("regime") == "high":
        return 0.5
    return 1.0
