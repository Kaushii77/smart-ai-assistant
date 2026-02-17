from datetime import datetime
from database import get_connection
from scheduler_service import send_email

def check_tasks():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    now = datetime.now()

    cursor.execute("""
        SELECT tasks.*, users.email
        FROM tasks
        JOIN users ON tasks.user_id = users.id
        WHERE tasks.status = 'pending'
        AND tasks.task_time <= %s
    """, (now,))

    due_tasks = cursor.fetchall()

    for task in due_tasks:
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
