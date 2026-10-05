"""Combine a match result and a zone permission into one access decision.

The matcher must never fail open. A missing face, an unavailable matcher,
or an unclear score becomes review required.
"""


def decide(
    *,
    face_count,
    matcher_ok,
    candidates,
    zone_provided,
    zone_permitted,
    match_threshold,
    review_threshold,
):
    """Return decision, reason, research_id, and confidence.

    candidates is a list of {"research_id", "score"} sorted best-first.
    """
    if not matcher_ok:
        return _result("review_required", "recognition_unavailable", None, None)
    if not zone_provided:
        return _result("review_required", "zone_missing", None, None)
    if face_count <= 0:
        return _result("review_required", "no_face", None, None)
    if face_count > 1:
        return _result("review_required", "multiple_faces", None, None)
    if not candidates:
        return _result("unauthorized", "no_match", None, None)

    best = candidates[0]
    confidence = round(float(best["score"]), 4)
    above = [item for item in candidates if item["score"] >= match_threshold]
    identities = []
    for item in above:
        if item["research_id"] not in identities:
            identities.append(item["research_id"])

    if len(identities) > 1:
        return _result("review_required", "ambiguous_match", None, confidence)
    if len(identities) == 1:
        research_id = identities[0]
        if not zone_permitted:
            return _result("unauthorized", "zone_denied", research_id, confidence)
        return _result("authorized", "match_and_permitted", research_id, confidence)
    if confidence >= review_threshold:
        return _result("review_required", "low_confidence", None, confidence)
    return _result("unauthorized", "no_match", None, confidence)


REASONS = {
    "recognition_unavailable": "The recognition service was unavailable, so the result is review required.",
    "zone_missing": "The selected zone does not exist.",
    "no_face": "No face was found. No identity was guessed.",
    "multiple_faces": "More than one face was in the frame, so no identity was guessed.",
    "ambiguous_match": "The face was close to more than one enrolled record.",
    "zone_denied": "The person is enrolled but is not permitted in this zone.",
    "match_and_permitted": "The face matched an enrolled adult who is permitted in this zone.",
    "low_confidence": "The similarity was too weak for an automatic match.",
    "no_match": "A face was found, and it did not match an enrolled record.",
}


def _result(decision, reason, research_id, confidence):
    return {
        "decision": decision,
        "reason": reason,
        "research_id": research_id,
        "confidence": confidence,
    }
