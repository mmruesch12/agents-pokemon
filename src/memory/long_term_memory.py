"""Long-term memory: vector summaries + structured facts + landmarks."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.memory.landmarks import merge_landmark, retrieve_landmarks_from_state

logger = logging.getLogger(__name__)


class LongTermMemory:
    """In-memory vector store with optional FAISS persistence."""

    def __init__(self, data_dir: str | Path = "data/memory"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._summaries: list[dict[str, Any]] = []
        self._facts: list[str] = []
        self._landmarks: list[dict[str, Any]] = []
        self._index = None
        self._load()

    def _load_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            logger.warning("Corrupt memory file %s — resetting", path)
            return default

    def _load(self) -> None:
        self._facts = self._load_json(self.data_dir / "facts.json", [])
        self._summaries = self._load_json(self.data_dir / "summaries.json", [])
        self._landmarks = self._load_json(self.data_dir / "landmarks.json", [])

    def _save(self) -> None:
        (self.data_dir / "facts.json").write_text(json.dumps(self._facts, indent=2))
        (self.data_dir / "summaries.json").write_text(json.dumps(self._summaries, indent=2))
        (self.data_dir / "landmarks.json").write_text(json.dumps(self._landmarks, indent=2))

    def add_summary(self, text: str, *, metadata: dict[str, Any] | None = None) -> str:
        entry = {"text": text, "metadata": metadata or {}}
        self._summaries.append(entry)
        self._save()
        return text

    def add_fact(self, fact: str) -> None:
        if fact not in self._facts:
            self._facts.append(fact)
            self._save()

    def add_landmark(self, landmark: dict[str, Any]) -> dict[str, Any]:
        if not landmark.get("id"):
            landmark = {
                **landmark,
                "id": f"landmark:{landmark.get('name', 'unknown')}:{landmark.get('map_key', '')}",
            }
        self._landmarks = merge_landmark(self._landmarks, landmark)
        self._save()
        return landmark

    def get_landmarks(self) -> list[dict[str, Any]]:
        return list(self._landmarks)

    def retrieve_landmarks(self, query: str, *, k: int = 3) -> list[dict[str, Any]]:
        return retrieve_landmarks_from_state(self._landmarks, query, k=k)

    def retrieve(self, query: str, *, k: int = 3, allow_fallback: bool = True) -> list[str]:
        query_lower = query.lower()
        scored = []
        for entry in self._summaries:
            text = entry["text"]
            score = sum(1 for word in query_lower.split() if word in text.lower())
            if score > 0:
                scored.append((score, text))
        scored.sort(key=lambda x: -x[0])
        results = [t for _, t in scored[:k]]
        if not results and allow_fallback:
            results = [s["text"] for s in self._summaries[-k:]]
        return results

    def summarize_history(self, history: list[str], *, max_items: int = 5) -> str:
        recent = history[-max_items:]
        summary = "; ".join(recent) if recent else "No recent history"
        self.add_summary(summary, metadata={"type": "history_summary"})
        return summary

    def format_stuck_fact(self, map_key: str, pattern: str, stuck_count: int) -> str:
        return f"stuck@{map_key}:{pattern}:{stuck_count}"

    def recent_nav_pattern(self, history: list[str], *, max_items: int = 5) -> str:
        dirs: list[str] = []
        for entry in history[-max_items:]:
            if entry.startswith("navigate:"):
                dirs.append(entry.split(":")[1].split("@")[0])
        return "-".join(dirs) if dirs else "none"

    def capture_stuck_episode(self, state: dict[str, Any], gs: Any) -> str:
        """Summarize recent history and record a structured stuck fact."""
        history = list(state.get("short_term_history", []))
        map_key = getattr(gs, "map_key", "") or ""
        summary = self.summarize_history(history)
        if self._summaries:
            self._summaries[-1]["text"] = f"{map_key}: {summary}"
            self._summaries[-1]["metadata"] = {"type": "stuck_episode", "map_key": map_key}
            self._save()
        pattern = self.recent_nav_pattern(history)
        stuck_count = int(state.get("stuck_count", 0))
        fact = self.format_stuck_fact(map_key, pattern, stuck_count)
        self.add_fact(fact)
        facts = list(state.get("long_term_facts", []))
        if fact not in facts:
            facts.append(fact)
        state["long_term_facts"] = facts
        return fact

    def get_facts(self) -> list[str]:
        return list(self._facts)

    def hydrate_state(self, state: dict[str, Any]) -> dict[str, Any]:
        state["long_term_facts"] = self.get_facts()
        merged = list(state.get("known_landmarks", []))
        for landmark in self.get_landmarks():
            merged = merge_landmark(merged, landmark)
        state["known_landmarks"] = merged
        return state

    def sync_landmarks_from_state(self, state: dict[str, Any]) -> None:
        for landmark in state.get("known_landmarks", []):
            self.add_landmark(landmark)

    def build_faiss_index(self) -> bool:
        try:
            import faiss
            import numpy as np
            if not self._summaries:
                return False
            dim = 64
            vectors = np.random.randn(len(self._summaries), dim).astype("float32")
            faiss.normalize_L2(vectors)
            self._index = faiss.IndexFlatIP(dim)
            self._index.add(vectors)
            logger.info("Built FAISS index with %d entries", len(self._summaries))
            return True
        except ImportError:
            return False
