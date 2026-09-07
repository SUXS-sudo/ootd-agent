from datetime import UTC, datetime as _datetime


class datetime(_datetime):
    """Backward-compatible UTC datetime without using the deprecated utcnow()."""

    @classmethod
    def utcnow(cls):
        return cls.now(UTC).replace(tzinfo=None)
