"""Text-only alert email. This module has no image attachment path."""

import smtplib
from email.message import EmailMessage

from . import config


def smtp_configured():
    return all(
        [
            config.env("SMTP_HOST"),
            config.env("SMTP_USERNAME"),
            config.env("SMTP_PASSWORD"),
            config.env("SMTP_RECIPIENT"),
        ]
    )


def build_message(zone_name, decision, reason, research_id, when, elapsed_ms):
    identity = research_id or "not matched"
    body = (
        "SecureSchool AI access alert\n\n"
        f"Decision: {decision}\n"
        f"Reason: {reason}\n"
        f"Zone: {zone_name}\n"
        f"Research ID: {identity}\n"
        f"Time (UTC): {when}\n"
        f"Response time: {elapsed_ms} ms\n\n"
        "Review this alert in the administrator dashboard before taking any action.\n"
        "This message does not include a facial image.\n"
        "The prototype does not apply an automatic penalty.\n"
    )
    message = EmailMessage()
    message["Subject"] = f"SecureSchool AI alert: {decision} at {zone_name}"
    message["From"] = config.env("SMTP_USERNAME")
    message["To"] = config.env("SMTP_RECIPIENT")
    message.set_content(body)
    return message


def send_text_alert(zone_name, decision, reason, research_id, when, elapsed_ms):
    if not smtp_configured():
        raise RuntimeError("SMTP settings are incomplete in .env.")
    message = build_message(zone_name, decision, reason, research_id, when, elapsed_ms)
    host = config.env("SMTP_HOST", "smtp.gmail.com")
    port = int(config.env("SMTP_PORT", "587") or "587")
    with smtplib.SMTP(host, port, timeout=20) as server:
        server.starttls()
        server.login(config.env("SMTP_USERNAME"), config.env("SMTP_PASSWORD"))
        server.send_message(message)
