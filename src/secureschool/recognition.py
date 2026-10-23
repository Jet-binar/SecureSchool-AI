"""Face detection and embedding comparison using OpenCV YuNet and SFace."""

import urllib.request

import cv2
import numpy as np

from . import config
from .crypto_util import decrypt_bytes, encrypt_bytes


class RecognitionUnavailable(Exception):
    pass


_detector = None
_recognizer = None


def ensure_models():
    config.MODEL_DIR.mkdir(parents=True, exist_ok=True)
    _download(config.YUNET_URL, config.YUNET_PATH)
    _download(config.SFACE_URL, config.SFACE_PATH)


def models_ready():
    return config.YUNET_PATH.exists() and config.SFACE_PATH.exists()


def _download(url, path):
    if path.exists() and path.stat().st_size > 0:
        return
    try:
        urllib.request.urlretrieve(url, path)
    except Exception:
        try:
            import ssl

            opener = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=ssl._create_unverified_context())
            )
            with opener.open(url, timeout=60) as response, path.open("wb") as handle:
                handle.write(response.read())
        except Exception as exc:
            if path.exists() and path.stat().st_size == 0:
                path.unlink()
            raise RecognitionUnavailable(
                f"Could not download {path.name}. Check the network and try again."
            ) from exc


def _load():
    global _detector, _recognizer
    if _detector is not None and _recognizer is not None:
        return
    if not models_ready():
        ensure_models()
    _detector = cv2.FaceDetectorYN.create(str(config.YUNET_PATH), "", (320, 320), 0.8, 0.3, 5000)
    _recognizer = cv2.FaceRecognizerSF.create(str(config.SFACE_PATH), "")


def detect_faces(image):
    """Return YuNet face rows. Empty list when no face is present."""
    try:
        _load()
    except Exception as exc:
        raise RecognitionUnavailable(str(exc)) from exc
    height, width = image.shape[:2]
    _detector.setInputSize((width, height))
    try:
        _, faces = _detector.detect(image)
    except Exception as exc:
        raise RecognitionUnavailable("Face detection failed.") from exc
    if faces is None:
        return []
    return [row for row in faces]


def embed(image, face_row):
    try:
        _load()
        aligned = _recognizer.alignCrop(image, face_row)
        feature = _recognizer.feature(aligned)
    except Exception as exc:
        raise RecognitionUnavailable("Could not create a face embedding.") from exc
    vector = np.asarray(feature, dtype=np.float32).reshape(-1)
    if vector.size == 0:
        raise RecognitionUnavailable("The embedding was empty.")
    return vector


def pack_embedding(vector):
    return encrypt_bytes(np.asarray(vector, dtype=np.float32).tobytes())


def unpack_embedding(blob):
    raw = decrypt_bytes(blob)
    return np.frombuffer(raw, dtype=np.float32).copy()


def cosine_score(left, right):
    try:
        _load()
        left_row = np.asarray(left, dtype=np.float32).reshape(1, -1)
        right_row = np.asarray(right, dtype=np.float32).reshape(1, -1)
        return float(
            _recognizer.match(left_row, right_row, cv2.FaceRecognizerSF_FR_COSINE)
        )
    except Exception as exc:
        raise RecognitionUnavailable("Face comparison failed.") from exc
