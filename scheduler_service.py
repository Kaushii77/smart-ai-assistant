from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from database import get_connection
from psycopg2.extras import RealDictCursor
from email_service import send_email

scheduler = BackgroundScheduler()

def check_tasks():
    print("Scheduler running...")
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)


    cursor.execute("""
        SELECT tasks.*, users.email
        FROM tasks
        JOIN users ON tasks.user_id = users.id
        WHERE tasks.status = 'pending'
    """)

    due_tasks = cursor.fetchall()

    for task in due_tasks:
        print("Executing task:", task["id"])
        send_email(
            task["email"],
            "Task Reminder",
            task["task_message"]
        )

        cursor.execute("""
            UPDATE tasks
            SET status='completed'
            WHERE id=%s
        """, (task["id"],))

    conn.commit()
    cursor.close()
    conn.close()

scheduler.add_job(check_tasks, 'interval', seconds=30)
scheduler.start()
