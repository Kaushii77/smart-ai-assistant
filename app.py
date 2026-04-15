from psycopg2.extras import RealDictCursor
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

app.config["SECRET_KEY"] = "super_secret_key"

csrf = CSRFProtect(app)

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["SESSION_COOKIE_NAME"] = "smart_assistant_session"
app.config["SESSION_REFRESH_EACH_REQUEST"] = True

serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])

@app.route("/cron/run-tasks")
def cron_run_tasks():
    check_tasks()
    return "OK"

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        # 🔐 Email validation
        email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
        if not re.match(email_pattern, email):
            flash("Invalid email format.", "danger")
            return render_template("register.html",
                                username=username,
                                email=email)

        # 🔐 Password match
        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html",
                       username=username,
                       email=email)
        # 🔐 Strong password rules
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("register.html",
                       username=username,
                       email=email)
        if not re.search(r"[A-Z]", password):
            flash("Password must contain at least one uppercase letter.", "danger")
            return render_template("register.html",
                       username=username,
                       email=email)
        if not re.search(r"[a-z]", password):
            flash("Password must contain at least one lowercase letter.", "danger")
            return render_template("register.html",
                       username=username,
                       email=email)
        if not re.search(r"\d", password):
            flash("Password must contain at least one number.", "danger")
            return render_template("register.html",
                       username=username,
                       email=email)
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            flash("Password must contain at least one special character.", "danger")
            return render_template("register.html",
                       username=username,
                       email=email)
        hashed_password = generate_password_hash(password)

        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # 🔐 Check duplicate username or email
        cursor.execute("SELECT * FROM users WHERE username=%s OR email=%s", (username, email))
        existing_user = cursor.fetchone()

        if existing_user:
            flash("Username or Email already exists.", "danger")
            cursor.close()
            conn.close()
            return render_template("register.html",
                       username=username,
                       email=email)
        cursor.execute(
            "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
            (username, email, hashed_password)
        )
        conn.commit()

        cursor.close()
        conn.close()

        flash("Account created successfully! Please login.", "success")
        return redirect("/login")

    return render_template("register.html")

@app.route("/check-username")
def check_username():

    username = request.args.get("username")

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("SELECT id FROM users WHERE username=%s", (username,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if user:
        return {"available": False}
    else:
        return {"available": True}

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"].strip()
        password = request.form["password"]

        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        # 🔹 If user does not exist
        if user is None:
            flash("Invalid username or password.", "danger")
            return redirect("/login")

        # 🔹 If account is suspended
        if not user.get("is_active", True):
            flash("Account suspended.", "danger")
            return redirect("/login")

        # 🔹 If password correct
        if check_password_hash(user["password"], password):

            session.clear()

            remember = request.form.get("remember")
            session.permanent = bool(remember)

            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["is_admin"] = user["is_admin"]

            return redirect("/")

        else:
            flash("Invalid username or password.", "danger")
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

            base_url = os.environ.get("BASE_URL", "http://127.0.0.1:5000")
            reset_link = f"{base_url}/reset-password/{token}"

            from email_service import send_email

            send_email(
                email,
                "Password Reset - Smart AI Assistant",
                f"""
            Hello,

            Click the link below to reset your password:

            {reset_link}

            This link will expire in 10 minutes.

            Regards,
            Smart AI Assistant
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

        new_username = request.form["username"]
        new_email = request.form["email"]

        cursor.execute(
            "UPDATE users SET username=%s, email=%s WHERE id=%s",
            (new_username, new_email, session["user_id"])
        )

        conn.commit()
        session["username"] = new_username

        cursor.close()
        conn.close()

        flash("Profile updated successfully!", "success")
        return redirect("/profile")

    cursor.close()
    conn.close()

    return render_template("profile.html", user=user)

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

    if "user_id" not in session:
        return redirect("/login")

    current_password = request.form["current_password"]

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("SELECT password FROM users WHERE id=%s", (session["user_id"],))
    user = cursor.fetchone()

    if not user:
        cursor.close()
        conn.close()
        return redirect("/profile")

    if not check_password_hash(user["password"], current_password):
        cursor.close()
        conn.close()
        return redirect("/profile")

    cursor.execute("DELETE FROM users WHERE id=%s", (session["user_id"],))
    conn.commit()

    cursor.close()
    conn.close()

    session.clear()

    return redirect("/login")

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
    cursor.execute("SELECT id, username, email, is_admin FROM users")
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
    cursor = conn.cursor()

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

    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
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
Smart AI Assistant Team
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

    conn = get_connection()
    cursor = conn.cursor()

    # Save to database
    cursor.execute(
        "INSERT INTO support_tickets (user_id, subject, message) VALUES (%s, %s, %s)",
        (session["user_id"], subject, message)
    )

    conn.commit()
    cursor.close()
    conn.close()

    return render_template("help.html", message="Support request submitted successfully!")

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

        now = datetime.utcnow()

        # Create datetime for today
        task_datetime = datetime.strptime(
            f"{now.strftime('%Y-%m-%d')} {time_only}",
            "%Y-%m-%d %H:%M"
        )

        # If time already passed today → schedule for tomorrow
        if task_datetime <= now:
            task_datetime += timedelta(days=1)

        full_datetime = task_datetime.strftime("%Y-%m-%d %H:%M:%S")

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

        now = datetime.now()

        task_datetime = datetime.strptime(
            f"{now.strftime('%Y-%m-%d')} {time_only}",
            "%Y-%m-%d %H:%M"
        )

        # If time already passed today → schedule tomorrow
        if task_datetime <= now:
            task_datetime += timedelta(days=1)

        full_datetime = task_datetime.strftime("%Y-%m-%d %H:%M:%S")

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

@app.before_request
def session_management():

    if "user_id" in session:
        session.modified = True

if __name__ == "__main__":
    app.run()
