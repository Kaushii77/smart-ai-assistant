import smtplib
import os
import traceback
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

APP_URL = os.environ.get("APP_URL", "https://smart-ai-assistant-m09y.onrender.com")

# ─────────────────────── private layout helpers ──────────────────────────────

_CARD_OPEN = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#eef0f7;
             font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background:#eef0f7;padding:32px 0;">
    <tr>
      <td align="center">
        <table width="480" cellpadding="0" cellspacing="0" border="0"
               style="background:#ffffff;border-radius:18px;overflow:hidden;
                      box-shadow:0 4px 24px rgba(80,80,160,0.13);max-width:96vw;">

          <!-- ── HEADER ── -->
          <tr>
            <td style="background:linear-gradient(135deg,#3a7bd5 0%,#6c63ff 100%);
                       padding:28px 32px 0 32px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="vertical-align:middle;text-align:left;padding-bottom:20px;">
                    <img src="{LOGO_URL}"
                         alt="Smart Assistant"
                         width="52" height="52"
                         style="border-radius:12px;background:#fff;padding:6px;
                                vertical-align:middle;margin-right:12px;"/>
                    <span style="color:#ffffff;font-size:22px;font-weight:700;
                                 vertical-align:middle;letter-spacing:-0.3px;">
                      Smart Assistant
                    </span>
                  </td>
                </tr>
              </table>
              <div style="line-height:0;margin-bottom:-2px;">
                <svg viewBox="0 0 480 48" xmlns="http://www.w3.org/2000/svg"
                     style="display:block;width:100%;">
                  <path d="M0,32 C80,0 160,48 240,24 C320,0 400,48 480,24 L480,48 L0,48 Z"
                        fill="#ffffff"/>
                </svg>
              </div>
            </td>
          </tr>"""

_CARD_CLOSE = """
          <!-- ── FOOTER ── -->
          <tr>
            <td style="border-top:1px solid #ebebf0;padding:20px 32px 28px 32px;
                       text-align:center;">
              <p style="margin:0 0 6px 0;font-size:20px;color:#6c63ff;">&#10084;</p>
              <p style="margin:0 0 4px 0;font-size:13px;color:#888;">
                Thank you for using Smart Assistant.
              </p>
              <p style="margin:0;font-size:11px;color:#bbb;">
                This is an automated email, please do not reply.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _card(title: str, body_html: str) -> str:
    logo_url = APP_URL.rstrip("/") + "/static/logo.png"
    return (
        _CARD_OPEN
        .replace("{title}", title)
        .replace("{LOGO_URL}", logo_url)
    ) + body_html + _CARD_CLOSE


# ─────────────────────── public HTML builders ─────────────────────────────────

def build_reminder_html(task_message: str, task_time_str: str) -> str:
    body = f"""
          <tr>
            <td style="padding:24px 32px 8px 32px;">
              <p style="margin:0 0 6px 0;font-size:20px;font-weight:700;color:#1a1a2e;">
                Hi there! &#128075;
              </p>
              <p style="margin:0 0 20px 0;font-size:15px;color:#555;line-height:1.5;">
                Just a quick reminder for your task:
              </p>
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background:#f4f6fb;border-radius:12px;
                            border-left:4px solid #6c63ff;margin-bottom:20px;">
                <tr>
                  <td style="padding:16px 18px;vertical-align:top;width:44px;">
                    <div style="background:#e8eaf6;border-radius:8px;width:36px;
                                height:36px;text-align:center;line-height:36px;
                                font-size:20px;">
                      &#128203;
                    </div>
                  </td>
                  <td style="padding:14px 14px 14px 0;vertical-align:middle;">
                    <p style="margin:0;font-size:15px;font-weight:700;color:#1a1a2e;">
                      {task_message}
                    </p>
                    <p style="margin:4px 0 0 0;font-size:13px;color:#777;">
                      Due Date: {task_time_str}
                    </p>
                  </td>
                </tr>
              </table>
              <p style="margin:0 0 24px 0;font-size:15px;color:#444;line-height:1.6;">
                You&#39;re doing great! Keep up the good work and make sure to finish it on time.
              </p>
              <table cellpadding="0" cellspacing="0" border="0"
                     style="margin:0 auto 28px auto;">
                <tr>
                  <td align="center"
                      style="background:linear-gradient(135deg,#3a7bd5,#6c63ff);
                             border-radius:10px;">
                    <a href="{APP_URL}"
                       style="display:inline-block;padding:13px 40px;color:#ffffff;
                              font-size:15px;font-weight:600;text-decoration:none;">
                      View Task
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""
    return _card("Task Reminder", body)


def build_activation_html(name: str, activation_link: str) -> str:
    body = f"""
          <tr>
            <td style="padding:24px 32px 8px 32px;">
              <p style="margin:0 0 6px 0;font-size:20px;font-weight:700;color:#1a1a2e;">
                Welcome, {name}! &#127881;
              </p>
              <p style="margin:0 0 20px 0;font-size:15px;color:#555;line-height:1.5;">
                Thanks for signing up! Click the button below to activate your account
                and get started.
              </p>
              <table cellpadding="0" cellspacing="0" border="0"
                     style="margin:0 auto 20px auto;">
                <tr>
                  <td align="center"
                      style="background:linear-gradient(135deg,#3a7bd5,#6c63ff);
                             border-radius:10px;">
                    <a href="{activation_link}"
                       style="display:inline-block;padding:13px 40px;color:#ffffff;
                              font-size:15px;font-weight:600;text-decoration:none;">
                      Activate Account
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin:0 0 8px 0;font-size:13px;color:#888;">
                This link expires in 24 hours. If you did not create this account,
                you can safely ignore this email.
              </p>
              <p style="margin:0 0 28px 0;font-size:12px;color:#aaa;word-break:break-all;">
                Or copy this link: {activation_link}
              </p>
            </td>
          </tr>"""
    return _card("Activate Your Account", body)


def build_restore_html(name: str, activation_link: str) -> str:
    body = f"""
          <tr>
            <td style="padding:24px 32px 8px 32px;">
              <p style="margin:0 0 6px 0;font-size:20px;font-weight:700;color:#1a1a2e;">
                Welcome back, {name}! &#127881;
              </p>
              <p style="margin:0 0 20px 0;font-size:15px;color:#555;line-height:1.5;">
                Your account has been restored. Click below to activate it and
                pick up right where you left off.
              </p>
              <table cellpadding="0" cellspacing="0" border="0"
                     style="margin:0 auto 20px auto;">
                <tr>
                  <td align="center"
                      style="background:linear-gradient(135deg,#3a7bd5,#6c63ff);
                             border-radius:10px;">
                    <a href="{activation_link}"
                       style="display:inline-block;padding:13px 40px;color:#ffffff;
                              font-size:15px;font-weight:600;text-decoration:none;">
                      Activate Account
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin:0 0 8px 0;font-size:13px;color:#888;">
                This link expires in 24 hours.
              </p>
              <p style="margin:0 0 28px 0;font-size:12px;color:#aaa;word-break:break-all;">
                Or copy this link: {activation_link}
              </p>
            </td>
          </tr>"""
    return _card("Account Restored", body)


def build_reset_html(reset_link: str) -> str:
    body = f"""
          <tr>
            <td style="padding:24px 32px 8px 32px;">
              <p style="margin:0 0 6px 0;font-size:20px;font-weight:700;color:#1a1a2e;">
                Password Reset &#128274;
              </p>
              <p style="margin:0 0 20px 0;font-size:15px;color:#555;line-height:1.5;">
                We received a request to reset your Smart Assistant password.
                Click the button below to choose a new one.
              </p>
              <table cellpadding="0" cellspacing="0" border="0"
                     style="margin:0 auto 20px auto;">
                <tr>
                  <td align="center"
                      style="background:linear-gradient(135deg,#3a7bd5,#6c63ff);
                             border-radius:10px;">
                    <a href="{reset_link}"
                       style="display:inline-block;padding:13px 40px;color:#ffffff;
                              font-size:15px;font-weight:600;text-decoration:none;">
                      Reset Password
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin:0 0 8px 0;font-size:13px;color:#888;">
                This link expires in 10 minutes. If you did not request a reset,
                you can safely ignore this email.
              </p>
              <p style="margin:0 0 28px 0;font-size:12px;color:#aaa;word-break:break-all;">
                Or copy this link: {reset_link}
              </p>
            </td>
          </tr>"""
    return _card("Reset Your Password", body)


def build_otp_html(new_email: str, otp_code: str) -> str:
    body = f"""
          <tr>
            <td style="padding:24px 32px 8px 32px;">
              <p style="margin:0 0 6px 0;font-size:20px;font-weight:700;color:#1a1a2e;">
                Verify Your New Email &#128231;
              </p>
              <p style="margin:0 0 20px 0;font-size:15px;color:#555;line-height:1.5;">
                You requested to change your email to <strong>{new_email}</strong>.
                Enter the code below to confirm the change.
              </p>
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="margin-bottom:20px;">
                <tr>
                  <td align="center">
                    <div style="display:inline-block;background:#f4f6fb;
                                border-radius:12px;padding:18px 40px;
                                border:2px dashed #6c63ff;">
                      <span style="font-size:34px;font-weight:800;
                                   letter-spacing:8px;color:#3a7bd5;">
                        {otp_code}
                      </span>
                    </div>
                  </td>
                </tr>
              </table>
              <p style="margin:0 0 8px 0;font-size:13px;color:#888;">
                This code is valid for 10 minutes.
              </p>
              <p style="margin:0 0 28px 0;font-size:13px;color:#aaa;">
                Do NOT share this code with anyone.
              </p>
            </td>
          </tr>"""
    return _card("Email Verification Code", body)


def build_support_reply_html(reply_message: str) -> str:
    body = f"""
          <tr>
            <td style="padding:24px 32px 8px 32px;">
              <p style="margin:0 0 6px 0;font-size:20px;font-weight:700;color:#1a1a2e;">
                Hi there! &#128075;
              </p>
              <p style="margin:0 0 20px 0;font-size:15px;color:#555;line-height:1.5;">
                Our support team has replied to your ticket:
              </p>
              <table width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="background:#f4f6fb;border-radius:12px;
                            border-left:4px solid #6c63ff;margin-bottom:20px;">
                <tr>
                  <td style="padding:16px 20px;font-size:14px;
                             color:#333;line-height:1.6;">
                    {reply_message}
                  </td>
                </tr>
              </table>
              <table cellpadding="0" cellspacing="0" border="0"
                     style="margin:0 auto 28px auto;">
                <tr>
                  <td align="center"
                      style="background:linear-gradient(135deg,#3a7bd5,#6c63ff);
                             border-radius:10px;">
                    <a href="{APP_URL}"
                       style="display:inline-block;padding:13px 40px;color:#ffffff;
                              font-size:15px;font-weight:600;text-decoration:none;">
                      View Ticket
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""
    return _card("Support Reply", body)


# ─────────────────────── core send function ───────────────────────────────────

def send_email(to_email: str, subject: str, body: str,
               html_body: str = None) -> None:
    sender   = os.environ.get("EMAIL")
    password = os.environ.get("EMAIL_PASSWORD")
    if not sender or not password:
        raise ValueError("EMAIL and EMAIL_PASSWORD environment variables are not set.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Smart Assistant <{sender}>"
    msg["To"]      = to_email
    msg.attach(MIMEText(body, "plain"))
    if html_body:
        msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
            server.ehlo(); server.starttls(); server.ehlo()
            server.login(sender, password)
            server.send_message(msg)
            print(f"[send_email] Sent to {to_email}: {subject}")
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError(
            "Gmail authentication failed. Use an App Password from "
            "myaccount.google.com/apppasswords"
        )
    except Exception:
        traceback.print_exc(); raise


# ─────────────────────── convenience wrappers ─────────────────────────────────

def send_reminder_email(to_email, task_message, task_time_str):
    send_email(
        to_email,
        f"\u23f0 Reminder: {task_message}",
        f"Reminder: {task_message}\nDue: {task_time_str}\n\n— Smart Assistant",
        build_reminder_html(task_message, task_time_str),
    )

def send_activation_email(to_email, name, activation_link):
    send_email(
        to_email,
        "Activate Your Smart Assistant Account",
        f"Hi {name},\n\nActivate your account: {activation_link}\n\n"
        f"Link expires in 24 hours.\n\n— Smart Assistant Team",
        build_activation_html(name, activation_link),
    )

def send_restore_email(to_email, name, activation_link):
    send_email(
        to_email,
        "Welcome Back – Activate Your Smart Assistant Account",
        f"Hi {name},\n\nYour account has been restored! Activate it: {activation_link}\n\n"
        f"Link expires in 24 hours.\n\n— Smart Assistant Team",
        build_restore_html(name, activation_link),
    )

def send_reset_email(to_email, reset_link):
    send_email(
        to_email,
        "Password Reset – Smart Assistant",
        f"Click the link to reset your password:\n\n{reset_link}\n\n"
        f"Link expires in 10 minutes.\n\n— Smart Assistant Team",
        build_reset_html(reset_link),
    )

def send_otp_email(to_email, new_email, otp_code):
    send_email(
        to_email,
        "Verify Your New Email – Smart Assistant",
        f"Your email verification code is: {otp_code}\n\n"
        f"Valid for 10 minutes. Do not share this code.\n\n— Smart Assistant Team",
        build_otp_html(new_email, otp_code),
    )

def send_support_reply_email(to_email, reply_message):
    send_email(
        to_email,
        "Reply to Your Support Ticket – Smart Assistant",
        f"Our team has replied to your ticket:\n\n{reply_message}\n\n"
        f"— Smart Assistant Team",
        build_support_reply_html(reply_message),
    )