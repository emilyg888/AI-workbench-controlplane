from __future__ import annotations

from .models import BundleState

S = BundleState

ALLOWED: dict[BundleState, set[BundleState]] = {
    S.DRAFT:     {S.EVALUATED, S.ARCHIVED},
    S.EVALUATED: {S.CANDIDATE, S.ARCHIVED},
    S.CANDIDATE: {S.EVALUATED, S.APPROVED, S.ARCHIVED},
    S.APPROVED:  {S.DEPLOYED, S.ARCHIVED},
    S.DEPLOYED:  {S.APPROVED, S.ARCHIVED},
    S.ARCHIVED:  set(),
}


class InvalidTransitionError(ValueError):
    pass


def is_valid_transition(frm: BundleState, to: BundleState) -> bool:
    return to in ALLOWED.get(frm, set())


def assert_transition(frm: BundleState, to: BundleState) -> None:
    if not is_valid_transition(frm, to):
        raise InvalidTransitionError(
            f"Illegal state transition: {frm.value} -> {to.value}"
        )
