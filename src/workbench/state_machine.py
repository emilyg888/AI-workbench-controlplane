from __future__ import annotations

from .models import BundleState

S = BundleState

# Every non-terminal state can transition to `rejected` via the promotion
# engine — see phase 4 spec §6.
_REJECTABLE = {S.EVALUATED, S.CANDIDATE}

ALLOWED: dict[BundleState, set[BundleState]] = {
    S.DRAFT:     {S.EVALUATED, S.ARCHIVED},
    S.EVALUATED: {S.CANDIDATE, S.ARCHIVED, S.REJECTED},
    S.CANDIDATE: {S.EVALUATED, S.APPROVED, S.ARCHIVED, S.REJECTED},
    S.APPROVED:  {S.DEPLOYED, S.ARCHIVED},
    S.DEPLOYED:  {S.APPROVED, S.ARCHIVED},
    S.ARCHIVED:  set(),
    S.REJECTED:  set(),
}


__all__ = ["ALLOWED", "InvalidTransitionError", "is_valid_transition",
           "assert_transition", "_REJECTABLE"]


class InvalidTransitionError(ValueError):
    pass


def is_valid_transition(frm: BundleState, to: BundleState) -> bool:
    return to in ALLOWED.get(frm, set())


def assert_transition(frm: BundleState, to: BundleState) -> None:
    if not is_valid_transition(frm, to):
        raise InvalidTransitionError(
            f"Illegal state transition: {frm.value} -> {to.value}"
        )
