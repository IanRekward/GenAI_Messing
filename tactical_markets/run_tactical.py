import json
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.pushover import send as pushover_send
from src.sector_rotation import generate

BASE = Path(__file__).parent
load_dotenv(BASE / ".env")

UNIVERSE = BASE / "config" / "universe.yaml"
THRESHOLDS = BASE / "config" / "thresholds.yaml"
THESES_LOG = BASE / "data" / "theses.jsonl"


def main() -> None:
    THESES_LOG.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = generate(UNIVERSE, THRESHOLDS)
    except Exception as exc:
        print(f"ERROR: {exc}")
        with open(THESES_LOG, "a") as f:
            f.write(json.dumps({
                "signal": False,
                "error": str(exc),
                "as_of": datetime.now(timezone.utc).isoformat(),
            }) + "\n")
        return

    if result:
        print(result["thesis"])
        sent = pushover_send("Tactical Premarket", result["thesis"])
        print(f"Pushover: {'sent' if sent else 'FAILED (check .env)'}")
    else:
        print("No sector rotation signal today.")
        result = {"signal": False, "as_of": datetime.now(timezone.utc).isoformat()}

    with open(THESES_LOG, "a") as f:
        f.write(json.dumps(result) + "\n")


if __name__ == "__main__":
    main()
