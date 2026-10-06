"""A policy-decision record only; this module does not evaluate policy."""

from __future__ import annotations

from enum import StrEnum

from .common import DomainId, DomainModel, NonBlankText


class PolicyVerdict(StrEnum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


class PolicyDecision(DomainModel):
    """Describes a verdict and its provenance; constructing it grants nothing."""

    action_id: DomainId
    verdict: PolicyVerdict
    reason_code: NonBlankText
    human_reason: NonBlankText
    policy_source: NonBlankText
