import os
import json
from datetime import datetime, timedelta
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def parse_command(user_input):
    today = datetime.now().strftime("%Y-%m-%d")
    current_time = datetime.now().strftime("%H:%M")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You extract structured task/reminder data from user commands. "
                    "Respond ONLY with valid JSON. No explanation."
                )
            },
            {
                "role": "user",
                "content": f"""
Today's date is {today} and current time is {current_time}.

Extract the following fields from the command and respond strictly in JSON:

- "action"   : short description of what to do (e.g. "send email reminder", "meeting reminder")
- "date"     : the date for the task in YYYY-MM-DD format. Use today's date unless the user says "tomorrow" or another day.
- "time"     : the time for the task in 24-hour HH:MM format
- "message"  : the full reminder message to send in the email

Command: {user_input}

Return a JSON object with exactly these four keys: action, date, time, message.
"""
            }
        ]
    )

    return response.choices[0].message.content
