"""[Sol] Vérifie les dates après une vraie relecture SQLite."""

from datetime import datetime, timedelta, timezone

from yumnews.domain.models import LoginAttempt


def test_sqlite_roundtrip_preserves_instant_and_restores_utc(container):
    instant = datetime(2026, 9, 10, 12, 0, tzinfo=timezone(timedelta(hours=2)))
    with container.db.session_scope() as session:
        attempt = LoginAttempt(
            email="date@example.com",
            ip_address="127.0.0.1",
            last_failed_at=instant,
            locked_until=None,
        )
        session.add(attempt)
        session.flush()
        attempt_id = attempt.id
    container.db.remove()
    with container.db.session_scope() as session:
        restored = session.get(LoginAttempt, attempt_id)
        assert restored.last_failed_at == instant
        assert restored.last_failed_at.tzinfo == timezone.utc
        assert restored.last_failed_at.hour == 10
        assert restored.locked_until is None
