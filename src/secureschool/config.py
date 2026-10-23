"""Paths and thresholds for the local prototype."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.getenv("SECURESCHOOL_DATA", str(ROOT / "data")))
MODEL_DIR = ROOT / "models"
TEMPLATE_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"

DB_PATH = DATA_DIR / "secureschool.db"
FERNET_PATH = DATA_DIR / "fernet.key"
ADMIN_PASSWORD_FILE = DATA_DIR / "initial_admin_password.txt"

YUNET_PATH = MODEL_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_PATH = MODEL_DIR / "face_recognition_sface_2021dec.onnx"

YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
SFACE_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_recognition_sface/face_recognition_sface_2021dec.onnx"
)

# OpenCV SFace sample thresholds. Higher cosine similarity is a closer match.
MATCH_THRESHOLD = 0.363
REVIEW_THRESHOLD = 0.28
CAPTURE_COOLDOWN_SECONDS = 2
EMAIL_COOLDOWN_SECONDS = 60
MAX_ENROLLMENT_SAMPLES = 5
MAX_UPLOAD_BYTES = 5_000_000
LOGIN_LOCK_AFTER = 5
LOGIN_LOCK_SECONDS = 300

CAMERA_BACKEND = os.getenv("CAMERA_BACKEND", "webcam").strip().lower() or "webcam"


def env(name, default=""):
    return os.getenv(name, default).strip()
