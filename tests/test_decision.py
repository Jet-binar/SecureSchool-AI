import unittest

from secureschool.decision import decide


THRESHOLDS = {"match_threshold": 0.363, "review_threshold": 0.28}


class DecisionTests(unittest.TestCase):
    def test_matcher_failure_is_review(self):
        result = decide(
            face_count=1,
            matcher_ok=False,
            candidates=[{"research_id": "A-01", "score": 0.9}],
            zone_provided=True,
            zone_permitted=True,
            **THRESHOLDS,
        )
        self.assertEqual(result["decision"], "review_required")
        self.assertIsNone(result["research_id"])

    def test_missing_zone_does_not_allow(self):
        result = decide(
            face_count=1,
            matcher_ok=True,
            candidates=[{"research_id": "A-01", "score": 0.9}],
            zone_provided=False,
            zone_permitted=True,
            **THRESHOLDS,
        )
        self.assertEqual(result["decision"], "review_required")

    def test_no_face_does_not_guess(self):
        result = decide(
            face_count=0,
            matcher_ok=True,
            candidates=[],
            zone_provided=True,
            zone_permitted=False,
            **THRESHOLDS,
        )
        self.assertEqual(result["reason"], "no_face")

    def test_multiple_faces_are_not_guessed(self):
        result = decide(
            face_count=2,
            matcher_ok=True,
            candidates=[],
            zone_provided=True,
            zone_permitted=False,
            **THRESHOLDS,
        )
        self.assertEqual(result["reason"], "multiple_faces")

    def test_permitted_match_is_authorized(self):
        result = decide(
            face_count=1,
            matcher_ok=True,
            candidates=[{"research_id": "A-01", "score": 0.51}],
            zone_provided=True,
            zone_permitted=True,
            **THRESHOLDS,
        )
        self.assertEqual(result["decision"], "authorized")
        self.assertEqual(result["research_id"], "A-01")

    def test_match_outside_zone_is_unauthorized(self):
        result = decide(
            face_count=1,
            matcher_ok=True,
            candidates=[{"research_id": "A-01", "score": 0.51}],
            zone_provided=True,
            zone_permitted=False,
            **THRESHOLDS,
        )
        self.assertEqual(result["decision"], "unauthorized")
        self.assertEqual(result["reason"], "zone_denied")

    def test_unknown_face_is_unauthorized(self):
        result = decide(
            face_count=1,
            matcher_ok=True,
            candidates=[{"research_id": "A-01", "score": 0.1}],
            zone_provided=True,
            zone_permitted=True,
            **THRESHOLDS,
        )
        self.assertEqual(result["decision"], "unauthorized")
        self.assertEqual(result["reason"], "no_match")

    def test_weak_score_is_review(self):
        result = decide(
            face_count=1,
            matcher_ok=True,
            candidates=[{"research_id": "A-01", "score": 0.3}],
            zone_provided=True,
            zone_permitted=True,
            **THRESHOLDS,
        )
        self.assertEqual(result["reason"], "low_confidence")
        self.assertIsNone(result["research_id"])

    def test_two_strong_matches_are_not_auto_accepted(self):
        result = decide(
            face_count=1,
            matcher_ok=True,
            candidates=[
                {"research_id": "A-01", "score": 0.7},
                {"research_id": "B-02", "score": 0.69},
            ],
            zone_provided=True,
            zone_permitted=True,
            **THRESHOLDS,
        )
        self.assertEqual(result["reason"], "ambiguous_match")
        self.assertIsNone(result["research_id"])


if __name__ == "__main__":
    unittest.main()
