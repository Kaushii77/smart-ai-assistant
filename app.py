from psycopg2.extras import RealDictCursor
from asyncio import tasks
import email
import os
from flask import (
    Flask, render_template, request, redirect,
    session, flash, jsonify, url_for
)
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_connection
from ai_parser import parse_command
from datetime import datetime
from flask import request, jsonify
from itsdangerous import URLSafeTimedSerializer
from flask_wtf.csrf import CSRFProtect
import re
import json
import scheduler_service
from scheduler_service import check_tasks



app = Flask(__name__)   # 👈 THIS MUST BE ABOVE @app.route

from scheduler_service import scheduler

if __name__ != "__main__":
    if not scheduler.running:
        print("🚀 Scheduler started")

from datetime import timedelta

# IST is UTC+5:30. Tasks entered by users are in IST, but the server runs in UTC.
# We convert user-entered IST times to UTC before storing in the database.
IST_OFFSET = timedelta(hours=5, minutes=30)

app.config["SECRET_KEY"] = "super_secret_key"

csrf = CSRFProtect(app)

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["SESSION_COOKIE_NAME"] = "smart_assistant_session"
app.config["SESSION_REFRESH_EACH_REQUEST"] = True

serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])

@app.route("/cron/run-tasks")
def cron_run_tasks():
    try:
        check_tasks()
        return jsonify({"status": "ok", "message": "Tasks checked"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/debug/pending-tasks")
def debug_pending_tasks():
    """Debug: shows your pending tasks and current server time."""
    if "user_id" not in session:
        return redirect("/login")
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("""
        SELECT id, action, task_time, task_message, status
        FROM tasks
        WHERE user_id = %s AND status = 'pending' AND is_deleted = FALSE
        ORDER BY task_time
    """, (session["user_id"],))
    tasks = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify({
        "server_time_now": str(datetime.now()),
        "pending_tasks": [dict(t) for t in tasks]
    })


@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name  = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        # 🔐 Email format check
        email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not re.match(email_pattern, email):
            flash("Invalid email format.", "danger")
            return render_template("register.html", name=name, email=email)

        # 🔐 Name length
        if len(name) < 2:
            flash("Name must be at least 2 characters.", "danger")
            return render_template("register.html", name=name, email=email)

        # 🔐 Password match
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html", name=name, email=email)

        # 🔐 Strong password rules
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("register.html", name=name, email=email)
        if not re.search(r"[A-Z]", password):
            flash("Password must contain at least one uppercase letter.", "danger")
            return render_template("register.html", name=name, email=email)
        if not re.search(r"[a-z]", password):
            flash("Password must contain at least one lowercase letter.", "danger")
            return render_template("register.html", name=name, email=email)
        if not re.search(r"\d", password):
            flash("Password must contain at least one number.", "danger")
            return render_template("register.html", name=name, email=email)
        if not re.search(r'[!@#$%^&*(),.?\":{}<>]', password):
            flash("Password must contain at least one special character.", "danger")
            return render_template("register.html", name=name, email=email)

        hashed_password = generate_password_hash(password)

        # Auto-generate a unique username from name (kept for DB compatibility)
        import uuid
        base_username = re.sub(r"[^a-z0-9]", "", name.lower()) or "user"
        username = base_username + "_" + uuid.uuid4().hex[:6]

        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # 🔐 Check if email already exists
        cursor.execute("SELECT id, is_active, password FROM users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            # If the account is active (not soft-deleted), block registration
            if existing_user["is_active"] and existing_user["password"]:
                flash("An account with this email already exists.", "danger")
                cursor.close()
                conn.close()
                return render_template("register.html", name=name, email=email)

            # Account was soft-deleted — restore it with new credentials
            # Tasks and support tickets linked to the old user_id are preserved!
            old_user_id = existing_user["id"]
            cursor.execute("""
                UPDATE users
                SET username    = %s,
                    password    = %s,
                    is_active   = TRUE,
                    is_verified = FALSE,
                    is_delete   = FALSE,
                    deleted_at  = NULL
                WHERE id = %s
            """, (username, hashed_password, old_user_id))

            # Re-activate any soft-deleted tasks for this user
            cursor.execute("""
                UPDATE tasks SET is_deleted = FALSE
                WHERE user_id = %s AND is_deleted = TRUE
            """, (old_user_id,))

            conn.commit()
            cursor.close()
            conn.close()

            # Generate activation token and send email (same flow as new user)
            activation_token = serializer.dumps(email, salt="email-activation-salt")
            base_url = os.environ.get("APP_URL", request.host_url.rstrip("/"))
            activation_link = f"{base_url}/activate/{activation_token}"
            from email_service import send_email
            send_email(
                email,
                "Activate Your Smart Assistant Account",
                f"""Hi {name},

Welcome back to Smart Assistant! Your account has been restored. Please click the link below to activate:

{activation_link}

This link will expire in 24 hours.

Regards,
Smart Assistant Team"""
            )
            flash("Account restored! Please check your email to activate.", "success")
            return redirect("/login")

        # Generate activation token (expires in 24 hours)
        activation_token = serializer.dumps(email, salt="email-activation-salt")

        cursor.execute(
            """INSERT INTO users (username, email, password, is_verified)
               VALUES (%s, %s, %s, FALSE)""",
            (username, email, hashed_password)
        )
        conn.commit()
        cursor.close()
        conn.close()

        # Build activation link
        base_url = os.environ.get("APP_URL", request.host_url.rstrip("/"))
        activation_link = f"{base_url}/activate/{activation_token}"

        # Send activation email
        from email_service import send_email
        send_email(
            email,
            "Activate Your Smart Assistant Account",
            f"""Hi {name},

Welcome to Smart Assistant! Please click the link below to activate your account:

{activation_link}

This link will expire in 24 hours.

If you did not create this account, please ignore this email.

Regards,
Smart Assistant Team"""
        )

        flash("Account created! Please check your email to activate your account.", "info")
        return redirect("/login")

    return render_template("register.html")


@app.route("/check-email")
def check_email():
    email = request.args.get("email", "").strip().lower()
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return {"available": user is None}

@app.route("/activate/<token>")
def activate_account(token):
    try:
        email = serializer.loads(
            token,
            salt="email-activation-salt",
            max_age=86400  # 24 hours
        )
    except Exception:
        flash("Activation link is invalid or has expired. Please register again.", "danger")
        return redirect("/register")

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
    user = cursor.fetchone()

    if not user:
        flash("Account not found. Please register again.", "danger")
        cursor.close()
        conn.close()
        return redirect("/register")

    if user.get("is_verified"):
        flash("Account already activated. Please login.", "info")
        cursor.close()
        conn.close()
        return redirect("/login")

    cursor.execute("UPDATE users SET is_verified=TRUE WHERE email=%s", (email,))
    conn.commit()
    cursor.close()
    conn.close()

    flash("🎉 Account activated successfully! You can now log in.", "success")
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email    = request.form["email"].strip().lower()
        password = request.form["password"]

        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        # User not found
        if user is None:
            flash("Invalid email or password.", "danger")
            return redirect("/login")

        # Account suspended by admin
        if not user.get("is_active", True):
            flash("Your account has been suspended. Please contact support.", "danger")
            return redirect("/login")

        # Email not yet verified
        if not user.get("is_verified", False):
            flash("Please activate your account first. Check your email for the activation link.", "warning")
            return redirect("/login")

        # Password check
        if check_password_hash(user["password"], password):
            session.clear()
            remember = request.form.get("remember")
            session.permanent = bool(remember)
            session["user_id"]  = user["id"]
            session["username"] = user["username"]
            session["name"]     = user.get("name") or user["username"]
            session["is_admin"] = user["is_admin"]
            return redirect("/")
        else:
            flash("Invalid email or password.", "danger")
            return redirect("/login")

    return render_template("login.html")

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":
        email = request.form["email"]

        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if user:
            token = serializer.dumps(email, salt="password-reset-salt")

            reset_link = f"{request.host_url}reset-password/{token}"

            from email_service import send_email

            send_email(
                email,
                "Password Reset - Smart Assistant",
                f"""
            Hello,

            Click the link below to reset your password:

            {reset_link}

            This link will expire in 10 minutes.

            Regards,
            Smart Assistant
            """
            )


        flash("If the email exists, a reset link has been sent.", "info")
        return redirect("/login")

    return render_template("forgot_password.html")

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):

    try:
        email = serializer.loads(
            token,
            salt="password-reset-salt",
            max_age=600  # 10 minutes expiry
        )
    except:
        flash("Reset link expired or invalid.", "danger")
        return redirect("/login")

    if request.method == "POST":

        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        # 🔐 Match check
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(request.url)

        # 🔐 Strong password validation
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return redirect(request.url)

        if not re.search(r"[A-Z]", password):
            flash("Must contain at least one uppercase letter.", "danger")
            return redirect(request.url)

        if not re.search(r"[a-z]", password):
            flash("Must contain at least one lowercase letter.", "danger")
            return redirect(request.url)

        if not re.search(r"\d", password):
            flash("Must contain at least one number.", "danger")
            return redirect(request.url)

        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            flash("Must contain at least one special character.", "danger")
            return redirect(request.url)

        hashed_password = generate_password_hash(password)

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE users SET password=%s WHERE email=%s",
            (hashed_password, email)
        )
        conn.commit()

        cursor.close()
        conn.close()

        flash("Password reset successful. Please login.", "success")
        return redirect("/login")

    return render_template("reset_password.html")

@app.route("/profile", methods=["GET", "POST"])
def profile():

    if "user_id" not in session:
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],))
    user = cursor.fetchone()

    if request.method == "POST":

        new_name = request.form.get("name", "").strip()

        if not new_name or len(new_name) < 2:
            flash("Name must be at least 2 characters.", "danger")
            cursor.close()
            conn.close()
            return render_template("profile.html", user=user)

        # Only update username — email changes require OTP verification via /request-email-change
        cursor.execute(
            "UPDATE users SET username=%s WHERE id=%s",
            (new_name, session["user_id"])
        )
        conn.commit()
        session["username"] = new_name
        session["name"]     = new_name

        cursor.close()
        conn.close()

        flash("Profile updated successfully!", "success")
        return redirect("/profile")

    cursor.close()
    conn.close()

    return render_template("profile.html", user=user)


@app.route("/request-email-change", methods=["POST"])
def request_email_change():
    """Step 1: User submits new email → send 6-digit OTP to the new email."""
    if "user_id" not in session:
        return redirect("/login")

    new_email = request.form.get("new_email", "").strip().lower()

    # Basic email format check
    import re as _re
    if not _re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', new_email):
        flash("Invalid email format.", "danger")
        return redirect("/profile")

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Make sure no other active account uses this email
    cursor.execute("SELECT id FROM users WHERE email = %s AND id != %s", (new_email, session["user_id"]))
    if cursor.fetchone():
        flash("That email is already in use by another account.", "danger")
        cursor.close()
        conn.close()
        return redirect("/profile")

    cursor.close()
    conn.close()

    # Generate a 6-digit OTP and store it in session (expires after 10 minutes)
    import random, time
    otp = str(random.randint(100000, 999999))
    session["email_change_otp"]      = otp
    session["email_change_new"]      = new_email
    session["email_change_expires"]  = time.time() + 600  # 10 minutes

    from email_service import send_email
    try:
        send_email(
            new_email,
            "Verify Your New Email – Smart Assistant",
            f"""Hi,

You requested to change your email address on Smart Assistant.

Your verification code is:

    {otp}

This code is valid for 10 minutes. Do NOT share it with anyone.

If you did not request this change, please ignore this email.

— Smart Assistant Team"""
        )
        flash(f"A 6-digit verification code has been sent to {new_email}. Please enter it below.", "info")
    except Exception as e:
        flash(f"Failed to send verification email: {str(e)}", "danger")

    return redirect("/profile")


@app.route("/verify-email-change", methods=["POST"])
def verify_email_change():
    """Step 2: User submits the OTP → update email if correct and not expired."""
    if "user_id" not in session:
        return redirect("/login")

    import time
    entered_otp  = request.form.get("otp", "").strip()
    stored_otp   = session.get("email_change_otp")
    new_email    = session.get("email_change_new")
    expires_at   = session.get("email_change_expires", 0)

    if not stored_otp or not new_email:
        flash("No pending email change request found. Please start again.", "danger")
        return redirect("/profile")

    if time.time() > expires_at:
        # Clear stale OTP data
        session.pop("email_change_otp", None)
        session.pop("email_change_new", None)
        session.pop("email_change_expires", None)
        flash("The verification code has expired. Please request a new one.", "danger")
        return redirect("/profile")

    if entered_otp != stored_otp:
        flash("Incorrect verification code. Please try again.", "danger")
        return redirect("/profile")

    # OTP correct — update the email
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Double-check no one grabbed this email in the meantime
    cursor.execute("SELECT id FROM users WHERE email = %s AND id != %s", (new_email, session["user_id"]))
    if cursor.fetchone():
        flash("That email is already in use. Please choose a different one.", "danger")
        cursor.close()
        conn.close()
        return redirect("/profile")

    cursor.execute("UPDATE users SET email = %s WHERE id = %s", (new_email, session["user_id"]))
    conn.commit()
    cursor.close()
    conn.close()

    # Clear OTP session keys
    session.pop("email_change_otp", None)
    session.pop("email_change_new", None)
    session.pop("email_change_expires", None)

    flash(f"Email address successfully updated to {new_email}!", "success")
    return redirect("/profile")

@app.route("/change-password", methods=["POST"])
def change_password():

    if "user_id" not in session:
        return redirect("/login")

    current_password = request.form["current_password"]
    new_password = request.form["new_password"]

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("SELECT password FROM users WHERE id=%s", (session["user_id"],))
    user = cursor.fetchone()

    if not check_password_hash(user["password"], current_password):
        flash("Current password is incorrect.", "danger")
        cursor.close()
        conn.close()
        return redirect("/profile")

    hashed_password = generate_password_hash(new_password)

    cursor.execute(
        "UPDATE users SET password=%s WHERE id=%s",
        (hashed_password, session["user_id"])
    )
    conn.commit()

    cursor.close()
    conn.close()

    flash("Password updated successfully!", "success")
    return redirect("/profile")

@app.route("/delete-account", methods=["POST"])
def delete_account():
    """
    Permanently delete account (soft-delete):
    - Clears password, username, and marks the user as deleted.
    - Tasks and support tickets are KEPT so they can be restored if
      the user re-registers with the same email address.
    - On re-registration, the new account's user_id will be linked
      to the old tasks/tickets via email matching in register().
    """
    if "user_id" not in session:
        return redirect("/login")

    current_password = request.form.get("current_password", "").strip()
    if not current_password:
        flash("Please enter your password to confirm deletion.", "danger")
        return redirect("/profile")

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute("SELECT id, password FROM users WHERE id = %s", (session["user_id"],))
        user = cursor.fetchone()

        if not user:
            flash("User not found.", "danger")
            return redirect("/profile")

        if not check_password_hash(user["password"], current_password):
            flash("Incorrect password. Account was NOT deleted.", "danger")
            return redirect("/profile")

        user_id = session["user_id"]

        # Soft-delete: clear sensitive fields but keep the row so
        # tasks/tickets remain linked by user_id.
        # We store a tombstone marker so we know it was deleted.
        cursor.execute("""
            UPDATE users
            SET password    = '',
                username    = CONCAT('deleted_', id),
                is_active   = FALSE,
                is_verified = FALSE,
                is_delete   = TRUE,
                deleted_at  = NOW()
            WHERE id = %s
        """, (user_id,))

        # Mark all user's pending tasks as deleted too
        cursor.execute("""
            UPDATE tasks SET is_deleted = TRUE
            WHERE user_id = %s AND status = 'pending'
        """, (user_id,))

        conn.commit()
        session.clear()
        flash("Your account has been permanently deleted.", "info")
        return redirect("/login")

    except Exception as e:
        conn.rollback()
        flash(f"An error occurred while deleting your account: {str(e)}", "danger")
        return redirect("/profile")
    finally:
        cursor.close()
        conn.close()

@app.route("/admin")
def admin_dashboard():

    if "user_id" not in session:
        return redirect("/login")

    if not session.get("is_admin"):
        return redirect("/")

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # --------------------
    # STATISTICS
    # --------------------
    cursor.execute("SELECT COUNT(*) AS total_users FROM users")
    total_users = cursor.fetchone()["total_users"]

    cursor.execute("SELECT COUNT(*) AS total_tasks FROM tasks WHERE is_deleted = FALSE")
    total_tasks = cursor.fetchone()["total_tasks"]

    cursor.execute("SELECT COUNT(*) AS pending FROM tasks WHERE status='pending'")
    pending = cursor.fetchone()["pending"]

    cursor.execute("SELECT COUNT(*) AS completed FROM tasks WHERE status='completed'")
    completed = cursor.fetchone()["completed"]

    # --------------------
    # USERS
    # --------------------
    cursor.execute("SELECT id, username, email, is_admin, is_active, is_delete FROM users")
    users = cursor.fetchall()

    # --------------------
    # ALL TASKS
    # --------------------
    cursor.execute("""
        SELECT tasks.*, users.username
        FROM tasks
        JOIN users ON tasks.user_id = users.id
        WHERE tasks.is_deleted = FALSE
        ORDER BY tasks.id DESC
    """)
    all_tasks = cursor.fetchall()

    # --------------------
    # SUPPORT TICKETS
    # --------------------
    cursor.execute("""
        SELECT support_tickets.*, users.username
        FROM support_tickets
        JOIN users ON support_tickets.user_id = users.id
        ORDER BY support_tickets.created_at DESC
    """)
    tickets = cursor.fetchall()

    cursor.execute("""
        SELECT * FROM ticket_replies
        ORDER BY created_at ASC
    """)

    replies = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "admin.html",
        total_users=total_users,
        total_tasks=total_tasks,
        pending=pending or 0,
        completed=completed or 0,
        users=users,
        all_tasks=all_tasks,
        tickets=tickets,
        replies=replies
    )

@app.route("/suspend/<int:user_id>")
def suspend_user(user_id):

    if not session.get("is_admin"):
        return redirect("/")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("UPDATE users SET is_active = FALSE WHERE id = %s", (user_id,))
    conn.commit()

    cursor.close()
    conn.close()

    return redirect("/admin")

@app.route("/activate/<int:user_id>")
def activate_user(user_id):

    if not session.get("is_admin"):
        return redirect("/")

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Only reactivate accounts that were suspended (is_delete = FALSE)
    # Do NOT reactivate accounts that were fully deleted (is_delete = TRUE)
    cursor.execute("SELECT is_delete FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()

    if user and not user["is_delete"]:
        cursor.execute("UPDATE users SET is_active = TRUE WHERE id = %s", (user_id,))
        conn.commit()

    cursor.close()
    conn.close()

    return redirect("/admin")

@app.route("/delete-user/<int:user_id>")
def delete_user(user_id):

    if not session.get("is_admin"):
        return redirect("/")

    conn = get_connection()
    cursor = conn.cursor()

    # Soft-delete: same approach as user self-deletion
    cursor.execute("""
        UPDATE users
        SET password    = '',
            username    = CONCAT('deleted_', id),
            is_active   = FALSE,
            is_verified = FALSE,
            is_delete   = TRUE,
            deleted_at  = NOW()
        WHERE id = %s
    """, (user_id,))

    # Mark all pending tasks as deleted too
    cursor.execute("""
        UPDATE tasks SET is_deleted = TRUE
        WHERE user_id = %s AND status = 'pending'
    """, (user_id,))

    conn.commit()
    cursor.close()
    conn.close()

    return redirect("/admin")

@app.route("/reply-ticket/<int:ticket_id>", methods=["POST"])
def reply_ticket(ticket_id):

    if "user_id" not in session:
        return redirect("/login")

    if not session.get("is_admin"):
        return redirect("/")

    reply_message = request.form.get("reply")

    if not reply_message:
        return redirect("/admin")

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT support_tickets.*, users.email
        FROM support_tickets
        JOIN users ON support_tickets.user_id = users.id
        WHERE support_tickets.id = %s
    """, (ticket_id,))
    
    ticket = cursor.fetchone()

    if not ticket:
        cursor.close()
        conn.close()
        return redirect("/admin")

    user_email = ticket["email"]

    # Insert reply history
    cursor.execute("""
        INSERT INTO ticket_replies (ticket_id, sender, message)
        VALUES (%s, 'admin', %s)
    """, (ticket_id, reply_message))

    # Update ticket
    cursor.execute("""
        UPDATE support_tickets
        SET status='resolved',
            replied_at=NOW()
        WHERE id=%s
    """, (ticket_id,))

    conn.commit()
    cursor.close()
    conn.close()

    from email_service import send_email

    send_email(
        user_email,
        "Reply to your Support Ticket",
        f"""
Hello,

Admin has replied to your support request.

Reply:
{reply_message}

Thank you,
Smart Assistant Team
        """
    )

    return redirect("/admin")

@app.route("/help")
def help_page():

    if "user_id" not in session:
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Get user's tickets
    cursor.execute("""
        SELECT *
        FROM support_tickets
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (session["user_id"],))

    tickets = cursor.fetchall()

    # For each ticket → attach replies
    for ticket in tickets:
        cursor.execute("""
            SELECT *
            FROM ticket_replies
            WHERE ticket_id = %s
            ORDER BY created_at ASC
        """, (ticket["id"],))

        ticket["replies"] = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("help.html", tickets=tickets)

@app.route("/support", methods=["POST"])
def support():

    if "user_id" not in session:
        return redirect("/login")

    subject = request.form["subject"]
    message = request.form["message"]

    # Basic validation
    if not subject or not subject.strip():
        flash("Please enter a subject.", "danger")
        return redirect("/help")
    if not message or not message.strip():
        flash("Please enter a message.", "danger")
        return redirect("/help")

    conn = get_connection()
    cursor = conn.cursor()

    # Save to database
    cursor.execute(
        "INSERT INTO support_tickets (user_id, subject, message) VALUES (%s, %s, %s)",
        (session["user_id"], subject.strip(), message.strip())
    )

    conn.commit()
    cursor.close()
    conn.close()

    # Redirect so the full help page (with ticket history) reloads properly
    flash("Your support request has been submitted successfully!", "success")
    return redirect("/help")

@app.route("/", methods=["GET", "POST"])
def home():

    if "user_id" not in session:
        return redirect("/login")
    

    message = ""

    # =========================
    # Handle Task Creation
    # =========================
    if request.method == "POST":

        user_input = request.form["command"]

        parsed_result = parse_command(user_input)
        data = json.loads(parsed_result)

        action = data["action"]
        time_only = data["time"]
        task_message = data["message"]
        task_date = data.get("date", datetime.now().strftime("%Y-%m-%d"))

        now = datetime.now()

        # Build the full datetime from parsed date + time
        try:
            task_datetime = datetime.strptime(
                f"{task_date} {time_only}",
                "%Y-%m-%d %H:%M"
            )
        except ValueError:
            # Fallback: use today's date if parsing fails
            task_datetime = datetime.strptime(
                f"{now.strftime('%Y-%m-%d')} {time_only}",
                "%Y-%m-%d %H:%M"
            )

        # Convert IST (user-entered) to UTC for DB storage (server runs in UTC)
        task_datetime_utc = task_datetime - IST_OFFSET
        now_utc = datetime.utcnow()

        # If UTC time already passed today → schedule for tomorrow
        if task_datetime_utc <= now_utc:
            task_datetime_utc += timedelta(days=1)

        full_datetime = task_datetime_utc.strftime("%Y-%m-%d %H:%M:%S")

        conn = get_connection()
        cursor = conn.cursor()

        query = """
        INSERT INTO tasks (command, action, task_time, task_message, user_id)
        VALUES (%s, %s, %s, %s, %s)
        """

        cursor.execute(
            query,
            (user_input, action, full_datetime, task_message, session["user_id"])
        )

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for("home"))

    filter_status = request.args.get("filter", "all")

    # =========================
    # Pagination Setup
    # =========================
    page = request.args.get("page", 1, type=int)
    per_page = 5
    offset = (page - 1) * per_page

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Count total tasks (not deleted)
    count_query = """
    SELECT COUNT(*) AS total FROM tasks
    WHERE user_id = %s AND is_deleted = FALSE
    """

    count_params = [session["user_id"]]

    if filter_status == "pending":
        count_query += " AND status = 'pending'"
    elif filter_status == "completed":
        count_query += " AND status = 'completed'"

    cursor.execute(count_query, tuple(count_params))
    total_tasks = cursor.fetchone()["total"]

    # Fetch paginated tasks
    query = """
    SELECT * FROM tasks
    WHERE user_id = %s AND is_deleted = FALSE
    """

    params = [session["user_id"]]

    # Add filter condition
    if filter_status == "pending":
        query += " AND status = 'pending'"
    elif filter_status == "completed":
        query += " AND status = 'completed'"

    query += " ORDER BY id DESC LIMIT %s OFFSET %s"
    params.extend([per_page, offset])

    cursor.execute(query, tuple(params))
    tasks = cursor.fetchall()

    total_pages = (total_tasks + per_page - 1) // per_page

    cursor.close()
    conn.close()

    return render_template(
        "index.html",
        message=message,
        tasks=tasks,
        page=page,
        total_pages=total_pages,
        filter_status=filter_status,
        total_tasks=total_tasks
    )


@app.route("/delete/<int:task_id>")
def delete_task(task_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE tasks
        SET is_deleted = TRUE
        WHERE id = %s AND user_id = %s
        """,
        (task_id, session["user_id"])
    )
    conn.commit()

    cursor.close()
    conn.close()

    return redirect("/")

@app.route("/tasks")
def get_tasks():
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM tasks WHERE user_id=%s ORDER BY id DESC",(session["user_id"],))
    tasks = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("task_table.html", tasks=tasks)

@app.route("/clear-completed")
def clear_completed():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE status='completed'")
    conn.commit()
    cursor.close()
    conn.close()
    return redirect("/")

@app.route("/delete-multiple", methods=["POST"])
def delete_multiple():

    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    ids = data.get("ids", [])

    if not ids:
        return jsonify({"error": "No IDs provided"}), 400

    conn = get_connection()
    cursor = conn.cursor()

    # Create placeholders dynamically
    placeholders = ",".join(["%s"] * len(ids))

    query = f"""
        UPDATE tasks
        SET is_deleted = TRUE
        WHERE id IN ({placeholders})
        AND user_id = %s
    """

    cursor.execute(query, ids + [session["user_id"]])
    conn.commit()

    cursor.close()
    conn.close()

    return jsonify({"success": True})

@app.route("/edit-task/<int:task_id>", methods=["GET", "POST"])
def edit_task(task_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    if request.method == "POST":
        new_command = request.form["command"]

        # 🔹 Parse again using AI
        parsed_result = parse_command(new_command)
        data = json.loads(parsed_result)

        action = data["action"]
        time_only = data["time"]
        task_message = data["message"]
        task_date = data.get("date", datetime.now().strftime("%Y-%m-%d"))

        now = datetime.now()

        try:
            task_datetime = datetime.strptime(
                f"{task_date} {time_only}",
                "%Y-%m-%d %H:%M"
            )
        except ValueError:
            task_datetime = datetime.strptime(
                f"{now.strftime('%Y-%m-%d')} {time_only}",
                "%Y-%m-%d %H:%M"
            )

        # Convert IST to UTC for DB storage
        task_datetime_utc = task_datetime - IST_OFFSET
        now_utc = datetime.utcnow()

        # If UTC time already passed today → schedule tomorrow
        if task_datetime_utc <= now_utc:
            task_datetime_utc += timedelta(days=1)

        full_datetime = task_datetime_utc.strftime("%Y-%m-%d %H:%M:%S")

        # 🔹 Update EVERYTHING
        cursor.execute("""
            UPDATE tasks
            SET command = %s,
                action = %s,
                task_time = %s,
                task_message = %s,
                status = 'pending'
            WHERE id = %s AND user_id = %s
        """, (
            new_command,
            action,
            full_datetime,
            task_message,
            task_id,
            session["user_id"]
        ))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect("/")

    # GET request
    cursor.execute(
        "SELECT * FROM tasks WHERE id = %s AND user_id = %s",
        (task_id, session["user_id"])
    )

    task = cursor.fetchone()
    cursor.close()
    conn.close()

    return render_template("edit_task.html", task=task)

@app.route("/mark-complete/<int:task_id>")
def mark_complete(task_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE tasks
        SET status = 'completed'
        WHERE id = %s AND user_id = %s
        """,
        (task_id, session["user_id"])
    )

    conn.commit()
    cursor.close()
    conn.close()

    return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# Public routes that don't need session validation
_PUBLIC_ROUTES = {
    "login", "register", "forgot_password", "reset_password",
    "activate_account", "check_email", "session_ended", "static",
    "cron_run_tasks"
}

@app.before_request
def session_management():
    if "user_id" not in session:
        return  # Not logged in — nothing to check

    session.modified = True

    # Skip check for public/auth routes to avoid DB hit on every static file
    if request.endpoint in _PUBLIC_ROUTES:
        return

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(
        "SELECT is_active, is_delete FROM users WHERE id = %s",
        (session["user_id"],)
    )
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user:
        session.clear()
        return redirect(url_for("session_ended", reason="deleted"))

    if user["is_delete"]:
        session.clear()
        return redirect(url_for("session_ended", reason="deleted"))

    if not user["is_active"]:
        session.clear()
        return redirect(url_for("session_ended", reason="suspended"))


@app.route("/session-ended")
def session_ended():
    reason = request.args.get("reason", "suspended")
    return render_template("session_ended.html", reason=reason)

if __name__ == "__main__":
    app.run(debug=True)