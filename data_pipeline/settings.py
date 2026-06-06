from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_LAKE_PATH = Path(os.getenv("DATA_LAKE_PATH", PROJECT_ROOT / "data_lake"))


def layer_path(layer: str, *parts: str) -> Path:
    path = DATA_LAKE_PATH / layer
    for part in parts:
        path = path / part
    path.mkdir(parents=True, exist_ok=True)
    return path


def file_path(layer: str, *parts: str) -> Path:
    path = DATA_LAKE_PATH / layer
    for part in parts[:-1]:
        path = path / part
    path.mkdir(parents=True, exist_ok=True)
    return path / parts[-1]

