from threading import Event

import pytest

from app import notification_worker


class FakeDB:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class StopAfterWait(Event):
    def wait(self, timeout=None):
        self.set()
        return True


def test_worker_processes_queue_and_closes_session(monkeypatch):
    fake_db = FakeDB()
    calls = {"process": 0, "close": 0}

    monkeypatch.setattr(notification_worker, "SessionLocal", lambda: fake_db)

    def process(db):
        calls["process"] += 1
        assert db is fake_db
        return 2

    monkeypatch.setattr(notification_worker, "process_pending", process)
    notification_worker.run_worker(stop_event=StopAfterWait(), poll_seconds=1)
    assert calls["process"] == 1
    assert fake_db.closed is True


@pytest.mark.parametrize("poll_seconds", [0, -1, 301, "5"])
def test_worker_rejects_invalid_poll_interval(poll_seconds):
    with pytest.raises(ValueError):
        notification_worker.run_worker(stop_event=Event(), poll_seconds=poll_seconds)


def test_poll_interval_environment_validation(monkeypatch):
    monkeypatch.setenv("NOTIFICATION_WORKER_POLL_SECONDS", "0")
    with pytest.raises(RuntimeError, match="between 1 and 300"):
        notification_worker._poll_seconds()
    monkeypatch.setenv("NOTIFICATION_WORKER_POLL_SECONDS", "not-a-number")
    with pytest.raises(RuntimeError, match="integer"):
        notification_worker._poll_seconds()
