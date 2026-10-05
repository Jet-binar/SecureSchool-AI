"""Enrollment and one-shot access checks.

Images are decoded in memory and are not written to disk.
"""

import re
import time
from datetime import datetime, timezone

import cv2
import numpy as np

from . import config, db, email_notifier, recognition
from .decision import decide

RESEARCH_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,31}$")


class PipelineError(Exception):
    pass


def decode_image(raw_bytes):
    if not raw_bytes:
        raise PipelineError("No image was submitted.")
    if len(raw_bytes) > config.MAX_UPLOAD_BYTES:
        raise PipelineError("Image is larger than 5 MB.")
    image = cv2.imdecode(np.frombuffer(raw_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise PipelineError("That file is not a readable image.")
    return image


def enroll(image, research_id, zone_ids, consent, actor):
    if not consent:
        raise PipelineError("Enrollment requires a recorded consent confirmation.")
    research_id = (research_id or "").strip()
    if not RESEARCH_ID.match(research_id):
        raise PipelineError(
            "Use a research ID of 3 to 32 letters, numbers, hyphens, or underscores."
        )
    zone_ids = sorted({int(zone_id) for zone_id in zone_ids})
    if not zone_ids:
        raise PipelineError("Select at least one zone.")
    known_zones = {zone["id"] for zone in db.list_zones()}
    if any(zone_id not in known_zones for zone_id in zone_ids):
        raise PipelineError("One of the selected zones does not exist.")

    faces = _faces(image)
    if len(faces) == 0:
        raise PipelineError("No face was found. Take the sample again.")
    if len(faces) > 1:
        raise PipelineError("The sample must contain one face.")

    vector = recognition.embed(image, _largest_face(faces))
    person = db.person_by_research_id(research_id)
    created = person is None
    if created:
        person_id = db.create_person(research_id)
    else:
        person_id = person["id"]
        if db.enrollment_count(person_id) >= config.MAX_ENROLLMENT_SAMPLES:
            raise PipelineError(
                f"This research ID already has {config.MAX_ENROLLMENT_SAMPLES} samples."
            )
    db.add_embedding(person_id, recognition.pack_embedding(vector))
    db.set_person_zones(person_id, zone_ids)
    samples = db.enrollment_count(person_id)
    db.audit(
        actor,
        "enroll",
        f"research_id={research_id}; samples={samples}; zones={','.join(map(str, zone_ids))}",
    )
    return {"research_id": research_id, "samples": samples, "created": created}


def remove_person(person_id, actor):
    research_id = db.delete_person(person_id)
    if not research_id:
        raise PipelineError("That enrollment record was not found.")
    db.audit(actor, "delete_enrollment", f"research_id={research_id}")
    return research_id


def access_check(image, zone_id, actor):
    started = time.perf_counter()
    _throttle()
    zone = db.zone_by_id(zone_id)
    zone_name = zone["name"] if zone else "Unknown zone"
    matcher_ok = True
    face_count = 0
    candidates = []
    zone_permitted = False

    if zone is None:
        outcome = decide(
            face_count=0,
            matcher_ok=True,
            candidates=[],
            zone_provided=False,
            zone_permitted=False,
            match_threshold=config.MATCH_THRESHOLD,
            review_threshold=config.REVIEW_THRESHOLD,
        )
    else:
        try:
            faces = _faces(image)
            face_count = len(faces)
            if face_count == 1:
                probe = recognition.embed(image, faces[0])
                candidates = _candidates(probe)
                above = []
                for item in candidates:
                    if item["score"] >= config.MATCH_THRESHOLD and item["research_id"] not in above:
                        above.append(item["research_id"])
                if len(above) == 1:
                    person = db.person_by_research_id(above[0])
                    allowed = db.person_zone_ids(person["id"]) if person else set()
                    zone_permitted = zone["id"] in allowed
        except recognition.RecognitionUnavailable:
            matcher_ok = False
        outcome = decide(
            face_count=face_count,
            matcher_ok=matcher_ok,
            candidates=candidates,
            zone_provided=True,
            zone_permitted=zone_permitted,
            match_threshold=config.MATCH_THRESHOLD,
            review_threshold=config.REVIEW_THRESHOLD,
        )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    event_id = db.add_event(
        zone_name,
        outcome["decision"],
        outcome["reason"],
        outcome["research_id"],
        outcome["confidence"],
        elapsed_ms,
    )
    db.set_setting("last_capture_at", db.now_iso())
    db.audit(
        actor,
        "access_decision",
        (
            f"event={event_id}; zone={zone_name}; decision={outcome['decision']}; "
            f"reason={outcome['reason']}; research_id={outcome['research_id'] or 'none'}"
        ),
    )
    email_status = _maybe_email(outcome, zone_name, elapsed_ms, actor)
    return {
        **outcome,
        "event_id": event_id,
        "zone_name": zone_name,
        "elapsed_ms": elapsed_ms,
        "email_status": email_status,
    }


def _faces(image):
    try:
        faces = recognition.detect_faces(image)
    except recognition.RecognitionUnavailable:
        raise
    return faces


def _largest_face(faces):
    return max(faces, key=lambda row: float(row[2]) * float(row[3]))


def _candidates(probe):
    best = {}
    for row in db.all_embeddings():
        stored = recognition.unpack_embedding(row["embedding"])
        score = recognition.cosine_score(probe, stored)
        current = best.get(row["research_id"])
        if current is None or score > current:
            best[row["research_id"]] = score
    candidates = [
        {"research_id": research_id, "score": score} for research_id, score in best.items()
    ]
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates


def _throttle():
    previous = db.get_setting("last_capture_at")
    if not previous:
        return
    then = datetime.fromisoformat(previous)
    elapsed = (datetime.now(timezone.utc) - then).total_seconds()
    if elapsed < config.CAPTURE_COOLDOWN_SECONDS:
        raise PipelineError("Wait a moment before starting another capture.")


def _maybe_email(outcome, zone_name, elapsed_ms, actor):
    if outcome["decision"] != "unauthorized":
        return "not_sent"
    if db.get_setting("email_enabled") != "1":
        return "disabled"
    previous = db.get_setting("last_email_at")
    if previous:
        then = datetime.fromisoformat(previous)
        if (datetime.now(timezone.utc) - then).total_seconds() < config.EMAIL_COOLDOWN_SECONDS:
            db.audit(actor, "email_skipped", "cooldown")
            return "cooldown"
    if not email_notifier.smtp_configured():
        db.audit(actor, "email_skipped", "smtp_not_configured")
        return "not_configured"
    try:
        email_notifier.send_text_alert(
            zone_name,
            outcome["decision"],
            outcome["reason"],
            outcome["research_id"],
            db.now_iso(),
            elapsed_ms,
        )
    except Exception as exc:
        db.audit(actor, "email_failed", exc.__class__.__name__)
        return "failed"
    db.set_setting("last_email_at", db.now_iso())
    db.audit(actor, "email_sent", f"zone={zone_name}")
    return "sent"
