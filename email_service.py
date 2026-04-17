import smtplib
import os
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_email(to_email, subject, body):
    sender = os.environ.get("EMAIL")
    password = os.environ.get("EMAIL_PASSWORD")

    if not sender or not password:
        raise ValueError("EMAIL and EMAIL_PASSWORD environment variables are not set.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Smart Assistant <{sender}>"
    msg["To"] = to_email

    # Plain text part
    text_part = MIMEText(body, "plain")
    msg.attach(text_part)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender, password)
            server.send_message(msg)
            print(f"[send_email] Sent to {to_email}: {subject}")
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError(
            "Gmail authentication failed. Make sure you are using an App Password "
            "(not your regular Gmail password). "
            "Generate one at: myaccount.google.com/apppasswords"
        )
    except Exception as e:
        traceback.print_exc()
        raise
