import json
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

BACKEND_DIR = Path(__file__).parent.parent


@pytest.fixture
def scheduler_config() -> dict:
    """The branched example agent — the main fixture for path/tool-calling tests."""
    return json.loads((BACKEND_DIR / "example_flow2.json").read_text())


@pytest.fixture
def linear_config() -> dict:
    return json.loads((BACKEND_DIR / "example_flow.json").read_text())
