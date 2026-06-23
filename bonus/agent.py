"""Minimal hybrid-memory POC for the Day 19 bonus challenge.

It keeps episodic memories in a Qdrant vector collection and obtains stable
profile/recent-activity features from the lab's Feast repository when that
repository has been materialized.  The small fallback profile keeps this demo
standalone while making the expected serving contract explicit.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)
from rank_bm25 import BM25Okapi

ROOT = Path(__file__).resolve().parent.parent
COLLECTION = "bonus_memories"
PROFILE_FEATURES = [
    "user_profile_features:reading_speed_wpm",
    "user_profile_features:preferred_language",
    "user_profile_features:topic_affinity",
    "query_velocity_features:queries_last_hour",
    "query_velocity_features:distinct_topics_24h",
]


class HybridMemoryAgent:
    """A clear POC: RRF combines lexical and semantic episodic recall."""

    def __init__(self) -> None:
        self.embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        self.client = QdrantClient(":memory:")
        self.client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
        self.memories: dict[str, list[dict[str, str]]] = defaultdict(list)
        self._next_id = 0

    @staticmethod
    def _chunks(text: str, size: int = 500) -> list[str]:
        """Prefer sentence boundaries, with a bounded fallback for long notes."""
        sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
        chunks, current = [], ""
        for sentence in sentences:
            candidate = f"{current}. {sentence}".strip(". ")
            if current and len(candidate) > size:
                chunks.append(current)
                current = sentence
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks or [text.strip()]

    def remember(self, text: str, user_id: str = "u_001") -> None:
        """Chunk, embed, and upsert an episodic memory scoped to one user."""
        chunks = self._chunks(text)
        vectors = list(self.embedder.embed(chunks))
        points = []
        for chunk, vector in zip(chunks, vectors):
            memory = {"id": str(self._next_id), "text": chunk}
            self.memories[user_id].append(memory)
            points.append(PointStruct(
                id=self._next_id,
                vector=vector.tolist(),
                payload={"user_id": user_id, "text": chunk},
            ))
            self._next_id += 1
        self.client.upsert(collection_name=COLLECTION, points=points)

    def _profile(self, user_id: str) -> dict[str, object]:
        fallback: dict[str, object] = {
            "reading_speed_wpm": 187, "preferred_language": "vi",
            "topic_affinity": "cloud", "queries_last_hour": 11,
            "distinct_topics_24h": 4,
        }
        try:
            from feast import FeatureStore

            fs = FeatureStore(repo_path=str(ROOT / "app" / "feast_repo"))
            values = fs.get_online_features(
                features=PROFILE_FEATURES, entity_rows=[{"user_id": user_id}]
            ).to_dict()
            for name, value in values.items():
                if name != "user_id" and value and value[0] is not None:
                    fallback[name] = value[0]
        except Exception:
            # A POC should still demonstrate the memory path before NB4 is run.
            pass
        return fallback

    def _keyword_ids(self, query: str, user_id: str) -> list[str]:
        memories = self.memories[user_id]
        if not memories:
            return []
        bm25 = BM25Okapi([m["text"].lower().split() for m in memories])
        scores = bm25.get_scores(query.lower().split())
        return [memories[i]["id"] for i in sorted(range(len(scores)), key=lambda i: -scores[i])]

    def recall(self, query: str, user_id: str = "u_001") -> str:
        """RRF-retrieve top memories, fetch features, then assemble LLM context."""
        profile = self._profile(user_id)
        query_vector = next(self.embedder.embed([query])).tolist()
        semantic = self.client.query_points(
            collection_name=COLLECTION,
            query=query_vector,
            query_filter=Filter(must=[FieldCondition(
                key="user_id", match=MatchValue(value=user_id)
            )]),
            limit=10,
        ).points
        semantic_ids = [str(point.id) for point in semantic]
        rrf: dict[str, float] = defaultdict(float)
        for ranked in (self._keyword_ids(query, user_id), semantic_ids):
            for rank, memory_id in enumerate(ranked, start=1):
                rrf[memory_id] += 1 / (60 + rank)
        by_id = {m["id"]: m["text"] for m in self.memories[user_id]}
        top = [by_id[memory_id] for memory_id, _ in sorted(
            rrf.items(), key=lambda item: -item[1]
        )[:3]]
        memories = "\n".join(f"- {text}" for text in top) or "- Chưa có episodic memory phù hợp."
        return (
            f"Query: {query}\n"
            f"User profile: prefers {profile['preferred_language']}, likes {profile['topic_affinity']}, "
            f"reads at {profile['reading_speed_wpm']} wpm.\n"
            f"Recent activity: {profile['queries_last_hour']} queries in the last hour; "
            f"{profile['distinct_topics_24h']} topics in 24h.\n"
            f"Top episodic memories (hybrid RRF, user-isolated):\n{memories}"
        )

