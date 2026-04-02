import logging
import os
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_invite_email(to_email, username, app_url):
    """Send a reinvite / invite email with a link to create an account."""
    host = os.environ.get('SMTP_HOST')
    port = int(os.environ.get('SMTP_PORT', 587))
    user = os.environ.get('SMTP_USER')
    password = os.environ.get('SMTP_PASSWORD')
    from_addr = os.environ.get('SMTP_FROM', user)

    if not all([host, user, password]):
        logger.warning('SMTP not configured — skipping invite email to %s', to_email)
        return False

    body = (
        f"Hi {username},\n\n"
        f"You've been invited to A.R.I.M.A.!\n\n"
        f"Create your account here: {app_url}\n\n"
        f"Use the email address this was sent to when creating your account."
    )

    msg = MIMEText(body)
    msg['Subject'] = 'A.R.I.M.A. — You\'ve been invited'
    msg['From'] = from_addr
    msg['To'] = to_email

    try:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        logger.info('Invite email sent to %s', to_email)
        return True
    except Exception:
        logger.exception('Failed to send invite email to %s', to_email)
        return False
