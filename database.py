import os
import psycopg2
from psycopg2.extras import RealDictCursor

def get_connection():
    DATABASE_URL = os.environ.get("DATABASE_URL")

    conn = psycopg2.connect(DATABASE_URL)
    return conn
