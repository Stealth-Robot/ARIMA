import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr

import resend

logger = logging.getLogger(__name__)

BODY_TEMPLATE = (
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
    "{username}, you're in.\n\n"
    "{app_url}\n"
)


def _send_via_resend(to_email, body, from_name, from_addr):
    resend.api_key = os.environ['RESEND_API_KEY']
    resend.Emails.send({
        'from': f'{from_name} <{from_addr}>',
        'to': [to_email],
        'subject': 'A.R.I.M.A.',
        'text': body,
    })


def _send_via_smtp(to_email, body, from_name, from_addr):
    host = os.environ.get('SMTP_HOST')
    port = int(os.environ.get('SMTP_PORT', 587))
    user = os.environ.get('SMTP_USER')
    password = os.environ.get('SMTP_PASSWORD')

    msg = MIMEText(body)
    msg['Subject'] = 'A.R.I.M.A.'
    msg['From'] = formataddr((from_name, from_addr))
    msg['To'] = to_email

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)


def send_invite_email(to_email, username, app_url):
    """Send a reinvite / invite email with a link to create an account."""
    from_name = os.environ.get('SMTP_FROM_NAME', 'A.R.I.M.A.')
    from_addr = os.environ.get('SMTP_FROM', 'onboarding@resend.dev')
    body = BODY_TEMPLATE.format(username=username, app_url=app_url)

    try:
        if os.environ.get('RESEND_API_KEY'):
            _send_via_resend(to_email, body, from_name, from_addr)
        elif os.environ.get('SMTP_HOST'):
            _send_via_smtp(to_email, body, from_name, from_addr)
        else:
            logger.warning('No email provider configured — skipping invite email to %s', to_email)
            return False
        logger.info('Invite email sent to %s', to_email)
        return True
    except Exception:
        logger.exception('Failed to send invite email to %s', to_email)
        return False
