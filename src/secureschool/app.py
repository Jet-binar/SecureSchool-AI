"""Administrator dashboard for enrollment, one-shot checks, alerts, and audit."""

import secrets
import time
from functools import wraps

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from . import config, db, email_notifier, pipeline, recognition
from .camera import CameraError, capture_frame
from .decision import REASONS
from .pipeline import PipelineError

_login_failures = {}


def create_app():
    app = Flask(
        __name__,
        template_folder=str(config.TEMPLATE_DIR),
        static_folder=str(config.STATIC_DIR),
    )
    app.config["SECRET_KEY"] = config.env("FLASK_SECRET_KEY") or secrets.token_hex(32)
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_BYTES + 200_000

    @app.before_request
    def _prepare():
        db.init_db()
        _ensure_admin()

    @app.context_processor
    def _inject():
        return {
            "csrf_token": _csrf,
            "reasons": REASONS,
            "current_user": session.get("username"),
        }

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("username"):
                return redirect(url_for("login"))
            if session.get("role") != "admin":
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped

    @app.get("/")
    @login_required
    def dashboard():
        summary = db.counts()
        return render_template(
            "dashboard.html",
            summary=summary,
            events=db.recent_events(),
            models_ready=_models_ok(),
        )

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            _check_csrf()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            locked, wait = _locked(username)
            if locked:
                flash(f"Too many attempts. Try again in {wait} seconds.", "error")
                return render_template("login.html"), 429
            user = db.user_by_name(username)
            if not user or not check_password_hash(user["password_hash"], password):
                _record_failure(username)
                db.audit(username or "unknown", "login_failure", "rejected")
                flash("Those credentials were not accepted.", "error")
                return render_template("login.html"), 401
            _login_failures.pop(username, None)
            session.clear()
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["csrf"] = secrets.token_hex(16)
            db.audit(user["username"], "login_success", "")
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.post("/logout")
    @login_required
    def logout():
        _check_csrf()
        actor = session.get("username", "unknown")
        session.clear()
        db.audit(actor, "logout", "")
        return redirect(url_for("login"))

    @app.route("/enroll", methods=["GET", "POST"])
    @login_required
    def enroll():
        if request.method == "POST":
            _check_csrf()
            try:
                image = _image_from_request()
                result = pipeline.enroll(
                    image,
                    request.form.get("research_id", ""),
                    request.form.getlist("zone_ids"),
                    request.form.get("consent") == "yes",
                    session["username"],
                )
            except (PipelineError, recognition.RecognitionUnavailable, CameraError) as exc:
                flash(str(exc), "error")
            else:
                flash(
                    f"Stored sample {result['samples']} for {result['research_id']}. "
                    "The photograph was not kept.",
                    "ok",
                )
            return redirect(url_for("enroll"))
        return render_template(
            "enroll.html",
            people=db.list_persons(),
            zones=db.list_zones(),
            max_samples=config.MAX_ENROLLMENT_SAMPLES,
        )

    @app.post("/enroll/<int:person_id>/delete")
    @login_required
    def delete_enrollment(person_id):
        _check_csrf()
        try:
            research_id = pipeline.remove_person(person_id, session["username"])
        except PipelineError as exc:
            flash(str(exc), "error")
        else:
            flash(f"Deleted enrollment {research_id} and its templates.", "ok")
        return redirect(url_for("enroll"))

    @app.route("/test", methods=["GET", "POST"])
    @login_required
    def test_access():
        result = None
        if request.method == "POST":
            _check_csrf()
            try:
                zone_id = int(request.form.get("zone_id", "0"))
                image = _image_from_request()
                session["last_result"] = pipeline.access_check(
                    image, zone_id, session["username"]
                )
            except (PipelineError, recognition.RecognitionUnavailable, CameraError, ValueError) as exc:
                flash(str(exc), "error")
            return redirect(url_for("test_access"))
        result = session.pop("last_result", None)
        return render_template("test.html", zones=db.list_zones(), result=result)

    @app.get("/alerts")
    @login_required
    def alerts():
        return render_template(
            "alerts.html",
            open_alerts=db.open_alerts(),
            reviewed=db.reviewed_alerts(),
        )

    @app.post("/alerts/<int:event_id>/review")
    @login_required
    def review_alert(event_id):
        _check_csrf()
        note = request.form.get("note", "")
        if db.review_event(event_id, note):
            db.audit(session["username"], "alert_review", f"event={event_id}")
            flash("Alert marked reviewed. No automatic action was taken.", "ok")
        else:
            flash("That alert is no longer open.", "error")
        return redirect(url_for("alerts"))

    @app.route("/zones", methods=["GET", "POST"])
    @login_required
    def zones():
        if request.method == "POST":
            _check_csrf()
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip()
            if len(name) < 2 or len(name) > 60:
                flash("Zone name must be 2 to 60 characters.", "error")
            else:
                try:
                    db.add_zone(name, description)
                except Exception:
                    flash("That zone name already exists.", "error")
                else:
                    db.audit(session["username"], "zone_create", name)
                    flash(f"Added zone {name}.", "ok")
            return redirect(url_for("zones"))
        return render_template("zones.html", zones=db.list_zones())

    @app.get("/audit")
    @login_required
    def audit():
        return render_template("audit.html", rows=db.recent_audit())

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        if request.method == "POST":
            _check_csrf()
            enabled = "1" if request.form.get("email_enabled") == "yes" else "0"
            db.set_setting("email_enabled", enabled)
            db.audit(session["username"], "settings_change", f"email_enabled={enabled}")
            flash("Email setting saved. Messages stay text-only.", "ok")
            return redirect(url_for("settings"))
        return render_template(
            "settings.html",
            email_enabled=db.get_setting("email_enabled") == "1",
            smtp_ready=email_notifier.smtp_configured(),
            camera_backend=config.CAMERA_BACKEND,
        )

    return app


def _image_from_request():
    source = request.form.get("capture_source", "upload")
    if source == "server":
        import cv2

        ok, encoded = cv2.imencode(".jpg", capture_frame())
        if not ok:
            raise PipelineError("Could not read a frame from the computer camera.")
        return pipeline.decode_image(encoded.tobytes())
    upload = request.files.get("image")
    if upload is None:
        raise PipelineError("Choose a capture before submitting.")
    return pipeline.decode_image(upload.read(config.MAX_UPLOAD_BYTES + 1))


def _csrf():
    token = session.get("csrf")
    if not token:
        token = secrets.token_hex(16)
        session["csrf"] = token
    return token


def _check_csrf():
    sent = request.form.get("csrf_token", "")
    if not sent or sent != session.get("csrf"):
        from flask import abort

        abort(400)


def _locked(username):
    record = _login_failures.get(username)
    if not record:
        return False, 0
    remaining = int(record["until"] - time.time())
    if remaining > 0 and record["count"] >= config.LOGIN_LOCK_AFTER:
        return True, remaining
    if remaining <= 0:
        _login_failures.pop(username, None)
    return False, 0


def _record_failure(username):
    record = _login_failures.get(username, {"count": 0, "until": 0})
    if record["until"] and record["until"] < time.time():
        record = {"count": 0, "until": 0}
    record["count"] += 1
    if record["count"] >= config.LOGIN_LOCK_AFTER:
        record["until"] = time.time() + config.LOGIN_LOCK_SECONDS
    _login_failures[username] = record


def _ensure_admin():
    if db.user_by_name(config.env("ADMIN_USERNAME", "admin") or "admin"):
        return
    username = config.env("ADMIN_USERNAME", "admin") or "admin"
    password = config.env("ADMIN_PASSWORD")
    generated = False
    if not password:
        if config.ADMIN_PASSWORD_FILE.exists():
            password = config.ADMIN_PASSWORD_FILE.read_text(encoding="utf-8").strip()
        if not password:
            password = secrets.token_urlsafe(12)
            generated = True
    db.create_user(username, generate_password_hash(password), "admin")
    if generated:
        config.ADMIN_PASSWORD_FILE.write_text(password + "\n", encoding="utf-8")
        print(f"Initial admin password written to {config.ADMIN_PASSWORD_FILE}")


def _models_ok():
    try:
        return recognition.models_ready()
    except Exception:
        return False


def main():
    db.init_db()
    _ensure_admin()
    try:
        recognition.ensure_models()
    except recognition.RecognitionUnavailable as exc:
        print(exc)
    create_app().run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
