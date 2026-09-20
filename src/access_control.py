"""Access-decision service: match result + zone permission → allow/deny."""

SUCCESS_THRESHOLD_SECONDS = 2.0
TRUE_ACCEPT_TARGET = 0.90
FALSE_ACCEPT_LIMIT = 0.05
FALSE_REJECT_LIMIT = 0.10


def decide_access(match_result, zone_permission):
    """Return a reviewable access decision.

    The prototype never applies an automatic disciplinary action.
    An administrator must review unauthorized results.
    """
    if not match_result.get("matched"):
        return {"decision": "unauthorized", "reason": "no_authorized_match"}
    if not zone_permission.get("allowed"):
        return {"decision": "unauthorized", "reason": "zone_denied"}
    return {"decision": "authorized", "reason": "match_and_zone_ok"}
