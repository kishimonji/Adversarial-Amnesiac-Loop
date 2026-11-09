"""
Adversarial Amnesiac Loop (AAL) - Core Controller
Version: 1.1
Description: Manages the adversarial friction loop, dynamic point budget, 
vectorized similarity penalties, and amnesia state resets between a Generator and Saboteur AI.
Includes thread-safe matrix buffering and Reflexion-style audit archiving.
"""

import logging
import threading
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger("AALController")  # host app configures logging

class Status(str, Enum):
    CONTINUE = "CONTINUE"
    RESET_TRIGGERED = "RESET_TRIGGERED"

@dataclass(frozen=True)
class TurnResult:
    status: Status
    points_remaining: int
    max_similarity: float
    penalty_applied: int
    mask_hit: bool                       # this turn re-entered a blacklisted zone
    reset_triggered: bool
    message: str
    archived_texts: Tuple[str, ...] = () # failed trajectory, for audit / text-level lessons

class _UnitStore:
    """Growable matrix of unit-norm vectors; avoids re-stacking on every query."""
    def __init__(self) -> None:
        self._m: Optional[np.ndarray] = None
        self._n = 0

    def __len__(self) -> int:
        return self._n

    def view(self) -> np.ndarray:
        return self._m[: self._n] if self._m is not None else np.empty((0, 0))

    def add(self, v: np.ndarray) -> None:
        if self._m is None:
            self._m = np.empty((16, v.shape[0]))
        elif self._n == self._m.shape[0]:
            self._m = np.concatenate([self._m, np.empty_like(self._m)])
        self._m[self._n] = v
        self._n += 1

    def max_sim(self, q: np.ndarray) -> float:
        return float((self._m[: self._n] @ q).max()) if self._n else 0.0

    def clear(self) -> None:
        self._n = 0

class AALController:
    AXIOM = (
        "SYSTEM_AXIOM: Prior trajectories failed and have been discarded. "
        "Review the archived texts to understand what not to do. "
        "Take a materially different approach."
    )

    def __init__(
        self,
        max_points: int = 10,
        similarity_threshold: float = 0.85,
        base_cost: int = 0,        # Set to 0 so novel/productive turns don't drain the budget
        loop_cost: int = 2,
        mask_cost: int = 3,
        mask_window: int = 3,      # Archive centroid of only the last k turns
    ) -> None:
        self.max_points = max_points
        self.points = max_points
        self.similarity_threshold = similarity_threshold
        self.base_cost = base_cost
        self.loop_cost = loop_cost
        self.mask_cost = mask_cost
        self.mask_window = mask_window

        self._hist = _UnitStore()
        self._mask = _UnitStore()
        self._texts: List[str] = []
        self._dim: Optional[int] = None
        self._lock = threading.Lock()

    def _prepare(self, emb: Sequence[float]) -> np.ndarray:
        v = np.asarray(emb, dtype=float)
        if v.ndim != 1 or not np.all(np.isfinite(v)):
            raise ValueError("embedding must be a finite 1-D vector")
        if self._dim is None:
            self._dim = v.shape[0]
        elif v.shape[0] != self._dim:
            raise ValueError(f"embedding dim {v.shape[0]} != expected {self._dim}")
        n = np.linalg.norm(v)
        if n == 0:
            raise ValueError("zero-norm embedding")
        return v / n

    def evaluate_turn(self, generator_output: str, output_embedding: Sequence[float]) -> TurnResult:
        with self._lock:
            q = self._prepare(output_embedding)
            neg_sim = self._mask.max_sim(q)
            hist_sim = self._hist.max_sim(q)
            mask_hit = neg_sim >= self.similarity_threshold
            loop_hit = hist_sim >= self.similarity_threshold

            if mask_hit:
                penalty = self.mask_cost
                logger.warning("Re-entered blacklisted zone (sim=%.3f, -%d)", neg_sim, penalty)
            elif loop_hit:
                penalty = self.loop_cost
                logger.info("Semantic loop (sim=%.3f, -%d)", hist_sim, penalty)
            else:
                penalty = self.base_cost

            self.points -= penalty
            self._texts.append(generator_output)
            self._hist.add(q)
            max_sim = max(neg_sim, hist_sim)

            if self.points <= 0:
                return self._reset_locked(penalty, max_sim, mask_hit)

            return TurnResult(Status.CONTINUE, self.points, max_sim, penalty, mask_hit, False, "Proceed.")

    def _reset_locked(self, penalty: int, max_sim: float, mask_hit: bool) -> TurnResult:
        logger.warning("Point budget exhausted; executing amnesia wipe...")
        
        # Save the texts before wiping them so the LLM can learn from the failure
        archived_failure_texts = tuple(self._texts)
        
        # Archive the centroid of ONLY the most recent failure loops, not the whole episode
        if len(self._hist) > 0:
            window_size = min(len(self._hist), self.mask_window)
            recent_embs = self._hist.view()[-window_size:]
            toxic_centroid = np.mean(recent_embs, axis=0)
            norm = np.linalg.norm(toxic_centroid)
            if norm > 0:
                self._mask.add(toxic_centroid / norm)

        # Hard Wipe
        self._texts.clear()
        self._hist.clear()
        self.points = self.max_points

        return TurnResult(
            status=Status.RESET_TRIGGERED,
            points_remaining=self.points,
            max_similarity=max_sim,
            penalty_applied=penalty,
            mask_hit=mask_hit,
            reset_triggered=True,
            message=self.AXIOM,
            archived_texts=archived_failure_texts
        )
