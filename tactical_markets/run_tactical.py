from pathlib import Path
from src.sector_rotation import generate

BASE = Path(__file__).parent
UNIVERSE = BASE / "config" / "universe.yaml"
THRESHOLDS = BASE / "config" / "thresholds.yaml"


def main() -> None:
    result = generate(UNIVERSE, THRESHOLDS)
    if result:
        print(result["thesis"])
    else:
        print("No sector rotation signal today.")


if __name__ == "__main__":
    main()
