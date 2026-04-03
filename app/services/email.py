import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr

logger = logging.getLogger(__name__)


def send_invite_email(to_email, username, app_url):
    """Send a reinvite / invite email with a link to create an account."""
    host = os.environ.get('SMTP_HOST')
    port = int(os.environ.get('SMTP_PORT', 587))
    user = os.environ.get('SMTP_USER')
    password = os.environ.get('SMTP_PASSWORD')
    from_addr = os.environ.get('SMTP_FROM', user)
    from_name = os.environ.get('SMTP_FROM_NAME', 'A.R.I.M.A.')

    if not all([host, user, password]):
        logger.warning('SMTP not configured — skipping invite email to %s', to_email)
        return False

    body = (
        "  ______       _______       ______      __       __       ______\n"
        " /      \\     |       \\     |      \\    |  \\     /  \\     /      \\\n"
        "|  $$$$$$\\    | $$$$$$$\\     \\$$$$$$    | $$\\   /  $$    |  $$$$$$\\\n"
        "| $$__| $$    | $$__| $$      | $$      | $$$\\ /  $$$    | $$__| $$\n"
        "| $$    $$    | $$    $$      | $$      | $$$$\\  $$$$    | $$    $$\n"
        "| $$$$$$$$    | $$$$$$$\\      | $$      | $$\\$$ $$ $$    | $$$$$$$$\n"
        "| $$  | $$ __ | $$  | $$ __  _| $$_  __ | $$ \\$$$| $$ __ | $$  | $$ __\n"
        "| $$  | $$|  \\| $$  | $$|  \\|   $$ \\|  \\| $$  \\$ | $$|  \\| $$  | $$|  \\\n"
        " \\$$   \\$$ \\$$ \\$$   \\$$ \\$$ \\$$$$$$ \\$$ \\$$      \\$$ \\$$ \\$$   \\$$ \\$$\n"
        "\n\n"
        f"{username}, you're in.\n\n"
        f"{app_url}\n"
    )

    msg = MIMEText(body)
    msg['Subject'] = 'A.R.I.M.A.'
    msg['From'] = formataddr((from_name, from_addr))
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
