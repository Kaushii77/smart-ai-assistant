# scheduler_service.py

from datetime import datetime
from database import get_connection
from psycopg2.extras import RealDictCursor
from email_service import send_email
import traceback


class _FakeScheduler:
    """Stub so app.py's `from scheduler_service import scheduler` doesn't crash."""
    running = True


scheduler = _FakeScheduler()


def check_tasks():
    """
    Called by /cron/run-tasks endpoint.
    Finds all pending tasks whose task_time has passed, sends reminder emails,
    and marks them as completed.
    """
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        now = datetime.now()
        print(f"[check_tasks] Running at {now}")

        cursor.execute("""
            SELECT tasks.*, users.email
            FROM tasks
            JOIN users ON tasks.user_id = users.id
            WHERE tasks.status = 'pending'
            AND tasks.is_deleted = FALSE
            AND tasks.task_time <= %s
        """, (now,))

        due_tasks = cursor.fetchall()
        print(f"[check_tasks] Found {len(due_tasks)} due task(s)")

        for task in due_tasks:
            try:
                send_email(
                    task["email"],
                    f"⏰ Reminder: {task['action']}",
                    task["task_message"]
                )
                print(f"[check_tasks] Email sent for task {task['id']} to {task['email']}")
            except Exception as e:
                print(f"[check_tasks] Failed to send email for task {task['id']}: {e}")
                traceback.print_exc()
                # Still mark as completed so it doesn't spam on next run
            finally:
                cursor.execute("""
                    UPDATE tasks
                    SET status = 'completed'
                    WHERE id = %s
                """, (task["id"],))

        conn.commit()
        cursor.close()

    except Exception as e:
        print(f"[check_tasks] ERROR: {e}")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()
