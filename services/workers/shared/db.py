import psycopg2
from psycopg2.extras import RealDictCursor

from shared.config import settings


def get_connection():
    return psycopg2.connect(settings.DATABASE_URL)


def get_cursor(connection, dictionary: bool = True):
    if dictionary:
        return connection.cursor(cursor_factory=RealDictCursor)
    return connection.cursor()
