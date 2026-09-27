from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from sqlalchemy.orm import sessionmaker

from twick_hub.domain.collections import ScheduledDownload
from twick_hub.domain.enums import Platform, ScheduleTrigger
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.persistence.scheduled_download_repository import (
    SqlScheduledDownloadRepository,
)


def _scheduled(external_id: str = "c1", created_at: datetime | None = None) -> ScheduledDownload:
    return ScheduledDownload(
        channel_ref=PlatformRef(platform=Platform.TWITCH, external_id=external_id),
        trigger=ScheduleTrigger.ON_NEXT_LIVE,
        created_at=created_at or datetime.now(),
    )


async def test_save_then_list_all_round_trips(session_factory: sessionmaker):
    repo = SqlScheduledDownloadRepository(session_factory)
    scheduled = _scheduled()

    await repo.save(scheduled)
    result = await repo.list_all()

    assert result == [scheduled]


async def test_save_upserts_last_triggered_at_by_id(session_factory: sessionmaker):
    repo = SqlScheduledDownloadRepository(session_factory)
    scheduled = _scheduled()
    await repo.save(scheduled)

    triggered = replace(scheduled, last_triggered_at=datetime(2026, 3, 1, 9, 0, 0))
    await repo.save(triggered)

    result = await repo.list_all()
    assert result == [triggered]


async def test_delete_removes_it(session_factory: sessionmaker):
    repo = SqlScheduledDownloadRepository(session_factory)
    scheduled = _scheduled()
    await repo.save(scheduled)

    await repo.delete(scheduled.id)

    assert await repo.list_all() == []


async def test_delete_of_unknown_id_does_not_raise(session_factory: sessionmaker):
    repo = SqlScheduledDownloadRepository(session_factory)
    await repo.delete("does-not-exist")


async def test_recurring_trigger_round_trips(session_factory: sessionmaker):
    repo = SqlScheduledDownloadRepository(session_factory)
    scheduled = replace(_scheduled(), trigger=ScheduleTrigger.RECURRING, is_active=False)

    await repo.save(scheduled)
    result = await repo.list_all()

    assert result[0].trigger == ScheduleTrigger.RECURRING
    assert result[0].is_active is False


async def test_list_all_respects_limit_and_offset(session_factory: sessionmaker):
    repo = SqlScheduledDownloadRepository(session_factory)
    base = datetime(2026, 1, 1)
    for i in range(5):
        await repo.save(_scheduled(f"c{i}", base + timedelta(minutes=i)))

    page = await repo.list_all(limit=2, offset=1)

    assert [s.channel_ref.external_id for s in page] == ["c3", "c2"]


async def test_at_time_fields_round_trip(session_factory: sessionmaker):
    repo = SqlScheduledDownloadRepository(session_factory)
    scheduled = ScheduledDownload(
        channel_ref=PlatformRef(platform=Platform.TWITCH, external_id="c2"),
        trigger=ScheduleTrigger.AT_TIME,
        run_at=datetime(2026, 9, 21, 20, 0),
        weekdays=(0, 2, 4),
        window_seconds=1800,
        priority=5,
        max_attempts=7,
        download_directory="D:/rec",
        preferred_format="mkv",
    ).with_first_due(datetime(2026, 9, 20, 0, 0))

    await repo.save(scheduled)
    (result,) = await repo.list_all()

    assert result == scheduled
    assert result.weekdays == (0, 2, 4)
    assert result.next_due_at == datetime(2026, 9, 21, 20, 0)


async def test_recovery_state_round_trips(session_factory: sessionmaker):
    from twick_hub.domain.enums import ScheduleOutcome

    repo = SqlScheduledDownloadRepository(session_factory)
    scheduled = _scheduled()
    await repo.save(scheduled)

    running = replace(scheduled, attempts=2, download_id="d1")
    await repo.save(running)
    assert (await repo.list_all())[0].download_id == "d1"

    finished = replace(
        running, attempts=0, download_id=None, last_outcome=ScheduleOutcome.COMPLETED
    )
    await repo.save(finished)

    (result,) = await repo.list_all()
    assert (result.attempts, result.download_id, result.last_outcome) == (
        0,
        None,
        ScheduleOutcome.COMPLETED,
    )


def test_a_default_scheduled_download_has_empty_weekdays_and_no_recovery_state():
    plain = _scheduled()
    assert plain.weekdays == () and plain.download_id is None and plain.last_outcome is None
