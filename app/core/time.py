from datetime import UTC, datetime


def utcnow() -> datetime:
    """Naive UTC datetime. All stored/compared datetimes in this app are
    naive and implicitly UTC -- this keeps comparisons consistent across
    Postgres (prod) and SQLite (tests), which disagree on tz-aware storage.
    """
    return datetime.now(UTC).replace(tzinfo=None)
