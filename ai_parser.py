import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def parse_command(user_input):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "You extract structured task data and respond only in JSON format."
            },
            {
                "role": "user",
                "content": f"""
                Extract the following and respond strictly in JSON:

                - action
                - time (only return time in 24-hour HH:MM format)
                - message

                Command: {user_input}

                Return a JSON object.
                """
            }

        ]
    )

    return response.choices[0].message.content
