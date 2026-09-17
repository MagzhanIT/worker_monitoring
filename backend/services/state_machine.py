from __future__ import annotations

from dataclasses import dataclass, field

from config import settings


@dataclass
class ActivityState:
    current_state: str = "UNKNOWN"
    candidate_state: str | None = None
    candidate_started_at: float | None = None
    state_started_at: float = 0
    confidence: float = 0
    reasons: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    evidence_quality: str = "LOW"
    idle_blocking_reasons: list[str] = field(default_factory=list)
    last_candidate_cancel_reason: str | None = None
    confirmation_seconds: float = 0.0


@dataclass
class Transition:
    previous: str
    current: str
    at: float
    reason: str | None = None


class TemporalStateMachine:
    def __init__(self, confirm_seconds: float | None = None) -> None:
        self.confirm_seconds = confirm_seconds if confirm_seconds is not None else settings.state_switch_confirm_seconds
        self.states: dict[int, ActivityState] = {}

    @staticmethod
    def _transition(
        state: ActivityState,
        proposed: str,
        now: float,
        reason: str | None,
    ) -> Transition:
        previous = state.current_state
        state.current_state = proposed
        state.state_started_at = now
        state.candidate_state = None
        state.candidate_started_at = None
        return Transition(previous, proposed, now, reason)

    def update(
        self,
        track_id: int,
        proposed: str,
        now: float,
        confidence: float = 0,
        reasons=None,
        limitations=None,
        *,
        evidence_quality: str = "LOW",
        idle_blocking_reasons=None,
        exit_reason: str | None = None,
    ) -> Transition | None:
        state = self.states.setdefault(track_id, ActivityState(state_started_at=now))
        state.confidence = confidence
        state.reasons = list(reasons or [])
        state.limitations = list(limitations or [])
        state.evidence_quality = evidence_quality
        state.idle_blocking_reasons = list(idle_blocking_reasons or [])

        if proposed == "IDLE_CANDIDATE":
            if state.current_state == "IDLE":
                state.candidate_state = None
                state.candidate_started_at = None
                return None
            if state.candidate_state != proposed:
                state.candidate_state = proposed
                state.candidate_started_at = now
                state.confirmation_seconds = settings.idle_confirm_seconds
                return None
            elapsed = now - (
                state.candidate_started_at
                if state.candidate_started_at is not None
                else now
            )
            if elapsed < settings.idle_confirm_seconds:
                return None
            return self._transition(
                state,
                "IDLE",
                now,
                "idle candidate satisfied confirmation duration",
            )

        if state.candidate_state == "IDLE_CANDIDATE":
            state.last_candidate_cancel_reason = exit_reason or proposed.lower()
            state.candidate_state = None
            state.candidate_started_at = None

        if proposed == state.current_state:
            state.candidate_state = None
            state.candidate_started_at = None
            return None
        if state.current_state == "IDLE" and proposed in {
            "SERVING_CUSTOMER",
            "FETCHING_MEDICINE",
            "SHELF_WORK",
            "CASHIER_WORK",
            "COMPUTER_POS_WORK",
            "OTHER_WORK",
            "ON_PHONE",
        }:
            return self._transition(
                state,
                proposed,
                now,
                exit_reason or "strong activity evidence",
            )
        if state.candidate_state != proposed:
            state.candidate_state = proposed
            state.candidate_started_at = now
            return None
        required = (
            settings.idle_exit_confirm_seconds
            if state.current_state == "IDLE"
            else self.confirm_seconds
        )
        if state.current_state == "IDLE" and evidence_quality == "LOW":
            required = max(required, settings.idle_hold_seconds)
        if state.candidate_started_at is None or now - state.candidate_started_at < required:
            return None
        return self._transition(state, proposed, now, exit_reason)

    def diagnostics(self, track_id: int, now: float) -> dict:
        state = self.states.get(track_id)
        if state is None:
            return {}
        candidate_duration = (
            max(0.0, now - state.candidate_started_at)
            if state.candidate_started_at is not None
            else 0.0
        )
        return {
            "final_activity": state.current_state,
            "candidate_activity": state.candidate_state,
            "candidate_duration_seconds": round(candidate_duration, 3),
            "idle_candidate_seconds": round(
                candidate_duration
                if state.candidate_state == "IDLE_CANDIDATE"
                else 0.0,
                3,
            ),
            "idle_confirmation_seconds": settings.idle_confirm_seconds,
            "confirmed_idle_seconds": round(
                max(0.0, now - state.state_started_at)
                if state.current_state == "IDLE"
                else 0.0,
                3,
            ),
            "evidence_quality": state.evidence_quality,
            "idle_blocking_reasons": list(state.idle_blocking_reasons),
            "last_idle_candidate_cancel_reason": state.last_candidate_cancel_reason,
        }

    def rebind(self, previous_track_id: int, new_track_id: int) -> bool:
        state = self.states.pop(previous_track_id, None)
        if state is None or new_track_id in self.states:
            return False
        self.states[new_track_id] = state
        return True

    def clear(self, track_id: int) -> ActivityState | None:
        return self.states.pop(track_id, None)
