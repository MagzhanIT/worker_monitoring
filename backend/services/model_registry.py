from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from config import settings


@dataclass
class ModelMetadata:
    filename: str
    path: str
    sha256: str | None
    class_names: list[str]
    input_size: int | None
    confidence_threshold: float
    dataset_name: str | None = None
    dataset_version: str | None = None
    training_date: str | None = None
    ultralytics_version: str | None = None
    pytorch_version: str | None = None
    device: str = "unavailable"
    license: str | None = None
    known_limitations: list[str] | None = None
    loaded: bool = False
    error: str | None = None


class ModelRegistry:
    def __init__(self) -> None:
        self.models: dict[str, object] = {}
        self.metadata: dict[str, ModelMetadata] = {}
        self._load_lock = threading.RLock()
        self._inference_locks: dict[str, threading.Lock] = {}

    @staticmethod
    def hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def load(self, name: str, configured_path: str, threshold: float, input_size: int | None = None):
        with self._load_lock:
            if name in self.models:
                return self.models[name]
            path = settings.backend_path(configured_path)
            metadata = ModelMetadata(path.name, str(path), None, [], input_size, threshold, known_limitations=["Accuracy is not measured for this pharmacy."])
            if not path.is_file():
                metadata.error = "Model file is missing; runtime download is disabled"
                self.metadata[name] = metadata
                return None
            try:
                from ultralytics import YOLO
                import torch
                import ultralytics
                model = YOLO(str(path))
                names = model.names
                metadata.class_names = list(names.values()) if isinstance(names, dict) else list(names)
                metadata.sha256 = self.hash_file(path)
                metadata.ultralytics_version = getattr(ultralytics, "__version__", None)
                metadata.pytorch_version = getattr(torch, "__version__", None)
                metadata.device = "cuda" if torch.cuda.is_available() else "cpu"
                sidecar = path.with_suffix(path.suffix + ".metadata.json")
                if sidecar.is_file():
                    data = json.loads(sidecar.read_text())
                    for key in ("dataset_name", "dataset_version", "training_date", "license", "known_limitations"):
                        if key in data:
                            setattr(metadata, key, data[key])
                metadata.loaded = True
                self.models[name] = model
                self._inference_locks.setdefault(name, threading.Lock())
            except Exception as exc:
                metadata.error = f"{type(exc).__name__}: {exc}"[:300]
            self.metadata[name] = metadata
            return self.models.get(name)

    def predict(self, name: str, model, *args, **kwargs):
        """Serialize a shared model while allowing different models in parallel."""
        lock = self._inference_locks.setdefault(name, threading.Lock())
        with lock:
            return model.predict(*args, **kwargs)

    def status(self) -> dict[str, dict]:
        return {name: asdict(value) for name, value in self.metadata.items()}


model_registry = ModelRegistry()
