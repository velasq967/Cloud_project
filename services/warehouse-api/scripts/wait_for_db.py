"""Espera a que PostgreSQL acepte conexiones antes de migrar."""

import time

from app.database import engine
from sqlalchemy import text

ATTEMPTS = 60
DELAY_SECONDS = 2


def main() -> None:
    last_error: Exception | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            print(f"database_ready attempt={attempt}")
            return
        except Exception as exc:  # pragma: no cover - depende de Docker
            last_error = exc
            print(f"database_not_ready attempt={attempt} error={exc}")
            time.sleep(DELAY_SECONDS)

    raise SystemExit(f"PostgreSQL no respondió después de {ATTEMPTS} intentos: {last_error}")


if __name__ == "__main__":
    main()
