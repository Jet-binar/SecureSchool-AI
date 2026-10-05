import os
import tempfile
import unittest
from pathlib import Path

os.environ["SECURESCHOOL_DATA"] = tempfile.mkdtemp(prefix="secureschool-test-")
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "test-pass-123"
os.environ["FLASK_SECRET_KEY"] = "test-secret"

from secureschool.app import create_app
from secureschool.email_notifier import build_message


class EmailShapeTests(unittest.TestCase):
    def test_alert_is_text_only(self):
        message = build_message("Laboratory", "unauthorized", "no_match", None, "2026-09-30T00:00:00+00:00", 120)
        self.assertFalse(message.is_multipart())
        content = message.get_content()
        self.assertIn("does not include a facial image", content)
        self.assertNotIn("attachment", content.lower())


class DashboardFlowTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        self.client.get("/login")
        self.csrf = self._csrf()

    def _csrf(self):
        with self.client.session_transaction() as sess:
            return sess["csrf"]

    def test_login_capture_review_and_audit(self):
        denied = self.client.get("/")
        self.assertEqual(denied.status_code, 302)

        bad = self.client.post(
            "/login",
            data={"username": "admin", "password": "wrong", "csrf_token": self.csrf},
        )
        self.assertEqual(bad.status_code, 401)

        ok = self.client.post(
            "/login",
            data={"username": "admin", "password": "test-pass-123", "csrf_token": self.csrf},
            follow_redirects=True,
        )
        self.assertIn(b"Dashboard", ok.data)
        self.csrf = self._csrf()

        blank = _jpeg()
        checked = self.client.post(
            "/test",
            data={
                "csrf_token": self.csrf,
                "zone_id": "1",
                "image": (blank, "blank.jpg"),
            },
            follow_redirects=True,
        )
        self.assertEqual(checked.status_code, 200)
        self.assertTrue(
            b"review required" in checked.data or b"Review required" in checked.data
            or b"unauthorized" in checked.data
        )

        alerts = self.client.get("/alerts")
        self.assertIn(b"Mark reviewed", alerts.data)
        reviewed = self.client.post(
            "/alerts/1/review",
            data={"csrf_token": self._csrf(), "note": "Checked in person"},
            follow_redirects=True,
        )
        self.assertIn(b"Already reviewed", reviewed.data)

        audit = self.client.get("/audit")
        self.assertIn(b"access_decision", audit.data)
        self.assertIn(b"alert_review", audit.data)
        self.assertNotIn(b"embedding", audit.data.lower())

        no_consent = self.client.post(
            "/enroll",
            data={
                "csrf_token": self._csrf(),
                "research_id": "A-100",
                "zone_ids": "1",
                "image": (_jpeg(), "blank.jpg"),
            },
            follow_redirects=True,
        )
        self.assertIn(b"consent", no_consent.data.lower())

        data_dir = Path(os.environ["SECURESCHOOL_DATA"])
        photos = list(data_dir.glob("*.jpg")) + list(data_dir.glob("*.png"))
        self.assertEqual(photos, [])


def _jpeg():
    import io

    import cv2
    import numpy as np

    image = np.full((80, 80, 3), 255, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    if not ok:
        raise RuntimeError("Could not encode a test image.")
    return io.BytesIO(encoded.tobytes())


if __name__ == "__main__":
    unittest.main()
