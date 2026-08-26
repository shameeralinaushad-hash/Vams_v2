import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from models import db, MailConfig


def get_mail_config():
    return MailConfig.query.first()


def send_email(subject, body, to_emails, html_body=None):
    cfg = get_mail_config()
    if not cfg or not cfg.is_enabled or not cfg.smtp_server:
        return False

    if isinstance(to_emails, str):
        to_emails = [to_emails]

    msg = MIMEMultipart("alternative") if html_body else MIMEText(body, "plain")
    if isinstance(msg, MIMEMultipart):
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

    msg["Subject"] = subject
    msg["From"] = f"{cfg.from_name} <{cfg.from_email}>" if cfg.from_name else cfg.from_email
    msg["To"] = ", ".join(to_emails)

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(cfg.smtp_server, cfg.smtp_port, timeout=15) as server:
            if cfg.use_tls:
                server.starttls(context=ctx)
            if cfg.smtp_username:
                server.login(cfg.smtp_username, cfg.smtp_password)
            server.sendmail(cfg.from_email, to_emails, msg.as_string())
        return True
    except Exception:
        return False


def send_notification_email(user_email, user_name, message, link=None):
    subject = "VAMS Business System — Notification"
    body = f"Hi {user_name},\n\n{message}\n"
    if link:
        body += f"\nView: {link}\n"
    body += "\n— VAMS Business System"
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:24px">
        <h3 style="color:#14181f;">{message}</h3>
        {"<p><a href='" + link + "' style='display:inline-block;background:#0e6b6c;color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:600;'>View Details</a></p>" if link else ""}
        <hr style="border:none;border-top:1px solid #eee;margin:20px 0">
        <p style="color:#888;font-size:0.85rem;">VAMS Business System</p>
    </div>
    """
    return send_email(subject, body, user_email, html_body=html)
