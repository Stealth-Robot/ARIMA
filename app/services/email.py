import logging
import os

import resend

logger = logging.getLogger(__name__)


def send_invite_email(to_email, username, app_url):
    """Send a reinvite / invite email with a link to create an account."""
    api_key = os.environ.get('RESEND_API_KEY')
    from_name = os.environ.get('SMTP_FROM_NAME', 'A.R.I.M.A.')
    from_addr = os.environ.get('SMTP_FROM', 'onboarding@resend.dev')

    if not api_key:
        logger.warning('RESEND_API_KEY not configured — skipping invite email to %s', to_email)
        return False

    resend.api_key = api_key

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

    try:
        resend.Emails.send({
            'from': f'{from_name} <{from_addr}>',
            'to': [to_email],
            'subject': 'A.R.I.M.A.',
            'text': body,
        })
        logger.info('Invite email sent to %s', to_email)
        return True
    except Exception:
        logger.exception('Failed to send invite email to %s', to_email)
        return False
