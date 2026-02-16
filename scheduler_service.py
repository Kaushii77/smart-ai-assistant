from psycopg2.extras import RealDictCursor
from apscheduler.schedulers.background import BackgroundScheduler
from database import get_connection
from datetime import datetime
import smtplib
from email.message import EmailMessage
import os
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

load_dotenv()

scheduler = BackgroundScheduler()


def check_tasks():
    print("Checking tasks...")  # 👈 confirms scheduler is running

    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    query = """
    SELECT * FROM tasks 
    WHERE status='pending' AND task_time <= %s
    """
    cursor.execute(query, (now,))
    tasks = cursor.fetchall()

    print(f"Tasks found: {len(tasks)}")  # 👈 shows if tasks found

    for task in tasks:
        print(f"Executing task ID: {task['id']}")

        # 🔎 Get user's email
        cursor.execute("SELECT email FROM users WHERE id=%s", (task["user_id"],))
        user = cursor.fetchone()
        if user:
            recipient_email = user["email"]
            send_email(
                recipient_email,
                "Task Reminder",
                task["task_message"]
            )

        # Mark as completed
        update_query = "UPDATE tasks SET status='completed' WHERE id=%s"
        cursor.execute(update_query, (task["id"],))
        conn.commit()


    cursor.close()
    conn.close()


def send_email(to_email, subject, body):

    sender_email = os.getenv("EMAIL")
    sender_password = os.getenv("EMAIL_PASSWORD")

    if not sender_email or not sender_password:
        print("Email credentials missing!")
        return

    if not to_email:
        print("Recipient email missing!")
        return

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        print("Email sent successfully")

    except Exception as e:
        print("Email sending failed:", e)

# Run every 30 seconds
scheduler.add_job(
    check_tasks,
    'interval',
    seconds=10,
    max_instances=3,
    coalesce=True
)
