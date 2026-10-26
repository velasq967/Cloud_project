from datetime import datetime, timezone


def current_utc_time() -> datetime:
    return datetime.now(timezone.utc)
