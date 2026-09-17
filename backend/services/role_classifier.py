from __future__ import annotations

from collections import deque

from config import settings


class TemporalRoleClassifier:
    """Stable Codea-style role memory with conservative one-way promotion.

    Once a track is a confirmed worker, missed coat detections do not demote it.
    A customer can become a worker only after repeated worker evidence. All
    memory remains camera-local and is cleared when the tracker expires.
    """

    def __init__(
        self,
        window: int | None = None,
        minimum_votes: int | None = None,
        worker_promotion_hits: int | None = None,
    ) -> None:
        self.window = window or settings.role_confirmation_window
        self.minimum_votes = minimum_votes or settings.role_customer_minimum_votes
        self.worker_promotion_hits = (
            worker_promotion_hits or settings.role_worker_promotion_hits
        )
        self.history: dict[int, deque[str]] = {}
        self.roles: dict[int, str] = {}

    def update(
        self,
        track_id: int,
        *,
        lab_coat_overlap: bool = False,
        employee_zone: bool = False,
        behind_counter: bool = False,
        worker_activity_zone: bool = False,
        customer_zone: bool = False,
        prior_role: str = "UNKNOWN",
    ) -> str:
        worker_score = sum(
            (
                lab_coat_overlap,
                employee_zone,
                behind_counter,
                worker_activity_zone,
                prior_role == "WORKER",
            )
        )
        customer_score = sum((customer_zone, prior_role == "CUSTOMER"))
        vote = "WORKER" if lab_coat_overlap or worker_score >= 2 else "CUSTOMER" if customer_score >= 1 and worker_score == 0 else "UNKNOWN"
        values = self.history.setdefault(track_id, deque(maxlen=self.window))
        values.append(vote)
        locked = self.roles.get(track_id)
        worker_votes = sum(value == "WORKER" for value in values)
        customer_votes = sum(value == "CUSTOMER" for value in values)
        if locked == "WORKER":
            return locked
        if worker_votes >= self.worker_promotion_hits:
            self.roles[track_id] = "WORKER"
        elif locked == "CUSTOMER":
            return locked
        elif customer_votes >= self.minimum_votes:
            self.roles[track_id] = "CUSTOMER"
        return self.roles.get(track_id, "UNKNOWN")

    def clear(self, track_id: int) -> None:
        self.history.pop(track_id, None)
        self.roles.pop(track_id, None)
