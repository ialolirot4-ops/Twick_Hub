import pytest

from tests.application.fakes import (
    FakeChannelDirectory,
    InMemoryScheduledDownloadRepository,
    make_channel,
)
from twick_hub.application.scheduled_downloads import (
    CancelScheduledDownloadUseCase,
    CreateScheduledDownloadUseCase,
)
from twick_hub.domain.enums import Platform, ScheduleTrigger
from twick_hub.domain.value_objects import PlatformRef


@pytest.fixture
def directory() -> FakeChannelDirectory:
    directory = FakeChannelDirectory()
    directory.add(make_channel("123", "northernlion", Platform.TWITCH))
    return directory


async def test_create_scheduled_download(directory):
    scheduled_downloads = InMemoryScheduledDownloadRepository()
    use_case = CreateScheduledDownloadUseCase(
        channel_directory=directory, scheduled_downloads=scheduled_downloads
    )

    scheduled = await use_case.execute(
        PlatformRef(platform=Platform.TWITCH, external_id="123"), ScheduleTrigger.ON_NEXT_LIVE
    )

    assert scheduled.trigger == ScheduleTrigger.ON_NEXT_LIVE
    assert scheduled.is_active is True
    assert await scheduled_downloads.list_all() == [scheduled]


async def test_create_scheduled_download_for_unknown_channel_raises(directory):
    scheduled_downloads = InMemoryScheduledDownloadRepository()
    use_case = CreateScheduledDownloadUseCase(
        channel_directory=directory, scheduled_downloads=scheduled_downloads
    )

    with pytest.raises(LookupError):
        await use_case.execute(
            PlatformRef(platform=Platform.TWITCH, external_id="nope"), ScheduleTrigger.ON_NEXT_LIVE
        )


async def test_cancel_scheduled_download(directory):
    scheduled_downloads = InMemoryScheduledDownloadRepository()
    created = await CreateScheduledDownloadUseCase(
        channel_directory=directory, scheduled_downloads=scheduled_downloads
    ).execute(PlatformRef(platform=Platform.TWITCH, external_id="123"), ScheduleTrigger.RECURRING)

    await CancelScheduledDownloadUseCase(scheduled_downloads=scheduled_downloads).execute(
        created.id
    )

    assert await scheduled_downloads.list_all() == []
