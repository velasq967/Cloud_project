"""Idempotencia persistente de consumidores (fase 10)."""

from shared.db import get_connection


def already_processed(event_id: str, consumer: str) -> bool:
    if not event_id:
        return False
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM processed_events
                WHERE event_id = %s AND consumer = %s
                """,
                (event_id, consumer),
            )
            return cursor.fetchone() is not None
    finally:
        connection.close()


def mark_processed(event_id: str, consumer: str) -> None:
    if not event_id:
        return
    connection = get_connection()
    try:
        with connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO processed_events (event_id, consumer)
                VALUES (%s, %s)
                ON CONFLICT (event_id, consumer) DO NOTHING
                """,
                (event_id, consumer),
            )
    finally:
        connection.close()
