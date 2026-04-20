from __future__ import annotations

import itertools

import pytest

from workbench.models import BundleState
from workbench.state_machine import (
    ALLOWED,
    InvalidTransitionError,
    assert_transition,
    is_valid_transition,
)

ALL_STATES = list(BundleState)


@pytest.mark.parametrize("frm,to", list(itertools.product(ALL_STATES, ALL_STATES)))
def test_transition_matrix(frm: BundleState, to: BundleState) -> None:
    """Every cell in the 6x6 transition matrix is checked."""
    expected = to in ALLOWED[frm]
    assert is_valid_transition(frm, to) is expected


def test_assert_transition_allows_valid() -> None:
    assert_transition(BundleState.DRAFT, BundleState.EVALUATED)
    assert_transition(BundleState.DRAFT, BundleState.ARCHIVED)
    assert_transition(BundleState.CANDIDATE, BundleState.APPROVED)


def test_assert_transition_rejects_invalid() -> None:
    with pytest.raises(InvalidTransitionError):
        assert_transition(BundleState.DRAFT, BundleState.APPROVED)
    with pytest.raises(InvalidTransitionError):
        assert_transition(BundleState.ARCHIVED, BundleState.DRAFT)


def test_principle_no_skip_evaluation() -> None:
    """Principle 2: no path from draft directly to approved or deployed."""
    assert not is_valid_transition(BundleState.DRAFT, BundleState.APPROVED)
    assert not is_valid_transition(BundleState.DRAFT, BundleState.DEPLOYED)
    assert not is_valid_transition(BundleState.DRAFT, BundleState.CANDIDATE)


def test_archived_is_terminal() -> None:
    for s in ALL_STATES:
        assert not is_valid_transition(BundleState.ARCHIVED, s)


def test_rejected_is_terminal() -> None:
    for s in ALL_STATES:
        assert not is_valid_transition(BundleState.REJECTED, s)


def test_can_reject_from_evaluated_and_candidate() -> None:
    assert is_valid_transition(BundleState.EVALUATED, BundleState.REJECTED)
    assert is_valid_transition(BundleState.CANDIDATE, BundleState.REJECTED)


def test_self_transitions_rejected() -> None:
    for s in ALL_STATES:
        assert not is_valid_transition(s, s)
