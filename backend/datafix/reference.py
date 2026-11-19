"""India Post PIN reference (data/reference/pincodes.csv)."""
import csv
import os
from functools import lru_cache
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "reference"


class PinReference:
    def __init__(self, path: Path):
        self.offices: dict[str, list[dict]] = {}
        with path.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                self.offices.setdefault(r["pin"], []).append(r)
        self.pins = frozenset(self.offices)

    def __contains__(self, pin: str) -> bool:
        return pin in self.pins

    def lookup(self, pin: str) -> list[dict]:
        return self.offices.get(pin, [])


@lru_cache(maxsize=1)
def pin_reference() -> PinReference | None:
    path = Path(os.getenv("DATAFIX_REFERENCE_DIR", DEFAULT_DIR)) / "pincodes.csv"
    return PinReference(path) if path.exists() else None
