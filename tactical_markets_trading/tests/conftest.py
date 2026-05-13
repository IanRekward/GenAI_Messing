"""pytest configuration: put src/ on the path so tests can import bot modules without installing as a package."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
