from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(adapter: str, name: str) -> bytes:
    """Recorded real responses (see scripts/record_fixture.py). Never hand-written."""
    matches = sorted((FIXTURES / adapter).glob(f"{name}.*"))
    if not matches:
        raise FileNotFoundError(f"no fixture {adapter}/{name}")
    return matches[0].read_bytes()
