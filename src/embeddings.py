"""Local embeddings with lazy model loading.

Fallback: if sentence-transformers is unavailable or JOB_RADAR_NO_EMBED=1,
similarity() returns 0.5 for every job (neutral) and adds no crash risk.
"""
import logging
import os
from pathlib import Path

log = logging.getLogger("embeddings")

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class Similarity:
    def __init__(self, resume_path: str):
        self.enabled = os.environ.get("JOB_RADAR_NO_EMBED", "") != "1"
        self.model = None
        self.resume_vec = None
        if not self.enabled:
            log.warning("embeddings disabled via JOB_RADAR_NO_EMBED")
            return
        try:
            from sentence_transformers import SentenceTransformer  # lazy heavy import
            self.model = SentenceTransformer(MODEL_NAME)
            resume_text = Path(resume_path).read_text(encoding="utf-8")
            self.resume_vec = self.model.encode([resume_text], normalize_embeddings=True)[0]
        except Exception as exc:  # noqa: BLE001 - degrade, never crash the pipeline
            log.error("embeddings unavailable, falling back to neutral 0.5: %s", exc)
            self.enabled = False

    def cosine_batch(self, texts: list[str]) -> list[float]:
        if not self.enabled or self.model is None:
            return [0.5] * len(texts)
        vecs = self.model.encode(texts, normalize_embeddings=True, batch_size=32,
                                 show_progress_bar=False)
        return [float(v @ self.resume_vec) for v in vecs]
