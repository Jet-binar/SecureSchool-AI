"""One-shot camera capture.

The webcam path is for this PC. The Pi path is available when the prototype
later runs on a Raspberry Pi. Neither path keeps a camera open in the background.
"""

import time

import cv2

from . import config


class CameraError(Exception):
    pass


def capture_frame():
    if config.CAMERA_BACKEND == "pi":
        return _capture_pi()
    if config.CAMERA_BACKEND != "webcam":
        raise CameraError("CAMERA_BACKEND must be webcam or pi.")
    return _capture_webcam()


def _capture_webcam():
    capture = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not capture.isOpened():
        capture.release()
        capture = cv2.VideoCapture(0)
    if not capture.isOpened():
        raise CameraError("No webcam was found on this PC.")
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    frame = None
    ok = False
    try:
        for _ in range(8):
            ok, frame = capture.read()
    finally:
        capture.release()
    if not ok or frame is None:
        raise CameraError("The webcam did not return a frame.")
    return frame


def _capture_pi():
    try:
        from picamera2 import Picamera2
    except ImportError as exc:
        raise CameraError(
            "picamera2 is not installed. Use CAMERA_BACKEND=webcam on this PC."
        ) from exc
    camera = Picamera2()
    try:
        camera.configure(camera.create_still_configuration(main={"size": (640, 480)}))
        camera.start()
        time.sleep(0.4)
        frame = camera.capture_array()
    finally:
        try:
            camera.stop()
        except Exception:
            pass
        camera.close()
    if frame is None:
        raise CameraError("The Pi camera did not return a frame.")
    if frame.ndim == 3 and frame.shape[2] == 4:
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
