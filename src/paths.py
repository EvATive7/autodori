from pathlib import Path


AGENT_DATA_DIR = Path(".autodori-agent-data")
DATA_PATH = AGENT_DATA_DIR / "data"
CACHE_PATH = AGENT_DATA_DIR / "cache"
DEBUG_PATH = AGENT_DATA_DIR / "debug"


def ensure_agent_data_directories() -> None:
    for directory in (DATA_PATH, CACHE_PATH, DEBUG_PATH):
        directory.mkdir(parents=True, exist_ok=True)
