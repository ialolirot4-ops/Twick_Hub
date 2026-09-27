from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from tests.application.fakes import (
    FakeChannelDirectory,
    FakeSecretTokenStore,
    InMemoryDownloadRepository,
    InMemoryFavoriteRepository,
    InMemoryLegacyMigrationRunRepository,
    InMemoryScheduledDownloadRepository,
    InMemorySettingsRepository,
    make_channel,
)
from twick_hub.application.migration import LegacyFileNotFoundError, LegacyMigrationService
from twick_hub.application.platform_registry import PlatformAdapters, PlatformRegistry
from twick_hub.domain.enums import LegacyMigrationStatus, Platform, Theme
from twick_hub.domain.settings import Settings
from twick_hub.infrastructure.migration.legacy_codec import LegacyCodecError
from twick_hub.infrastructure.migration.legacy_reader import LegacyValidationError

_TOKEN_KEY = "user-session-token"


def _obj(class_name: str, module: str = "AppData.Preferences", **fields):
    return {"__type__": f"obj:{module}:{class_name}", **fields}


def _s(value: str) -> str:
    return f"str:{value}"


def _user(user_id: str, login: str) -> dict:
    return _obj(
        "User", module="Services.Twitch.GQL.TwitchGQLModels", id=_s(user_id), login=_s(login)
    )


def _legacy_payload(
    *,
    bookmarks: list[str] | None = None,
    presets: list[dict] | None = None,
    include_account: bool = True,
    history: list[dict] | None = None,
    account_expiration: str = "datetime:2027-01-01T00:00:00.000Z",
) -> dict:
    payload: dict = {
        "general": _obj("General", _notify=True, _bookmarks=[_s(b) for b in bookmarks or []]),
        "advanced": _obj("Advanced", _themeMode=_s("dark")),
        "download": _obj("Download", _downloadSpeed=4),
        "scheduledDownloads": _obj(
            "ScheduledDownloads", _enabled=True, _scheduledDownloadPresets=presets or []
        ),
        "temp": _obj("Temp", _downloadHistory=history or []),
    }
    if include_account:
        payload["account"] = _obj(
            "Account",
            _accountData={
                "__type__": "tuple",
                "data": [
                    _user("111", "legacyuser"),
                    _obj(
                        "OAuthToken",
                        module="Services.Twitch.Authentication.OAuth.OAuthToken",
                        value=_s("SECRET-TOKEN"),
                        expiration=account_expiration,
                    ),
                ],
            },
        )
    return payload


def _preset(channel: str, enabled: bool = True) -> dict:
    return _obj(
        "ScheduledDownloadPreset",
        module="Download.ScheduledDownloadPreset",
        channel=_s(channel),
        preferredQualityIndex=2,
        fileFormat=_s("mp4"),
        directory=_s("D:/Recordings"),
        enabled=enabled,
    )


def _history_entry(content_id: str, channel_id: str) -> dict:
    content = _obj(
        "Stream",
        module="Services.Twitch.GQL.TwitchGQLModels",
        id=_s(content_id),
        title=_s("A stream"),
        broadcaster=_user(channel_id, "achannel"),
    )
    download_info = _obj(
        "StreamDownloadInfo",
        module="Download.DownloadInfo",
        content=content,
        directory=_s("D:/Downloads"),
        fileName=_s(f"file-{content_id}"),
        fileFormat=_s("mp4"),
    )
    return _obj(
        "DownloadHistory",
        module="Download.History.DownloadHistory",
        downloadInfo=download_info,
        startedAt="datetime:2026-01-01T00:00:00.000Z",
        completedAt="datetime:2026-01-01T01:00:00.000Z",
        result=_s("download-complete"),
    )


class _FrozenClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now


def _write_legacy_file(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "settings.json"
    path.write_bytes(json.dumps(payload).encode())
    return path


def _service(
    tmp_path: Path,
    *,
    registry: PlatformRegistry | None = None,
    favorites=None,
    scheduled=None,
    downloads=None,
    settings=None,
    runs=None,
    token_store=None,
) -> LegacyMigrationService:
    return LegacyMigrationService(
        settings=settings or InMemorySettingsRepository(),
        favorites=favorites or InMemoryFavoriteRepository(),
        scheduled_downloads=scheduled or InMemoryScheduledDownloadRepository(),
        downloads=downloads or InMemoryDownloadRepository(),
        migration_runs=runs or InMemoryLegacyMigrationRunRepository(),
        token_store=token_store or FakeSecretTokenStore(),
        token_store_key=_TOKEN_KEY,
        backup_dir=tmp_path / "backups",
        registry=registry,
        clock=_FrozenClock(datetime(2026, 9, 25, 12, 0)),
    )


def _registry_with(*channels) -> PlatformRegistry:
    directory = FakeChannelDirectory()
    for channel in channels:
        directory.add(channel)
    adapters = {Platform.TWITCH: PlatformAdapters(channel_directory=directory)}
    return PlatformRegistry(_adapters=adapters)


# --- run(): not found -------------------------------------------------


async def test_run_raises_when_no_legacy_file_exists(tmp_path: Path):
    service = _service(tmp_path)

    with pytest.raises(LegacyFileNotFoundError):
        await service.run(legacy_path=tmp_path / "nope.json")


# --- run(): settings + account -------------------------------------------------


async def test_run_migrates_settings_onto_the_existing_row_without_resetting_it(tmp_path: Path):
    legacy_file = _write_legacy_file(tmp_path, _legacy_payload(include_account=False))
    settings_repo = InMemorySettingsRepository()
    await settings_repo.save(Settings().updated(max_concurrent_downloads=1))
    service = _service(tmp_path, settings=settings_repo)

    run = await service.run(legacy_path=legacy_file)

    assert run.settings_migrated is True
    updated = await settings_repo.get()
    assert updated.theme is Theme.DARK
    assert updated.max_concurrent_downloads == 4  # legacy's _downloadSpeed, not left at 1


async def test_run_migrates_the_account_token_into_the_token_store(tmp_path: Path):
    legacy_file = _write_legacy_file(tmp_path, _legacy_payload())
    token_store = FakeSecretTokenStore()
    service = _service(tmp_path, token_store=token_store)

    run = await service.run(legacy_path=legacy_file)

    assert run.account_token_migrated is True
    assert token_store.load(_TOKEN_KEY) == "SECRET-TOKEN"


async def test_run_records_a_warning_when_the_token_store_fails(tmp_path: Path):
    legacy_file = _write_legacy_file(tmp_path, _legacy_payload())
    token_store = FakeSecretTokenStore(fail_on_save=RuntimeError("no keyring backend"))
    service = _service(tmp_path, token_store=token_store)

    run = await service.run(legacy_path=legacy_file)

    assert run.account_token_migrated is False
    assert run.status is LegacyMigrationStatus.COMPLETED_WITH_WARNINGS
    assert any("token" in w for w in run.warnings)


async def test_run_with_no_signed_in_account_does_not_touch_the_token_store(tmp_path: Path):
    legacy_file = _write_legacy_file(tmp_path, _legacy_payload(include_account=False))
    token_store = FakeSecretTokenStore()
    service = _service(tmp_path, token_store=token_store)

    run = await service.run(legacy_path=legacy_file)

    assert run.account_token_migrated is False
    assert token_store.tokens == {}


async def test_run_warns_when_the_migrated_token_had_already_expired(tmp_path: Path):
    """Distinct from test_run_records_a_warning_when_the_token_store_fails
    above: here saving to the token store succeeds — the warning is about
    the token's own expiration already being in the past by the time it's
    migrated, not about the credential store failing."""
    legacy_file = _write_legacy_file(
        tmp_path, _legacy_payload(account_expiration="datetime:2020-01-01T00:00:00.000Z")
    )
    token_store = FakeSecretTokenStore()
    service = _service(tmp_path, token_store=token_store)

    run = await service.run(legacy_path=legacy_file)

    assert run.account_token_migrated is True
    assert any("already expired" in w for w in run.warnings)


# --- run(): bookmarks / scheduled downloads -------------------------------------------------


async def test_run_migrates_resolvable_bookmarks_into_favorites(tmp_path: Path):
    legacy_file = _write_legacy_file(
        tmp_path, _legacy_payload(bookmarks=["Shroud", "Ninja"], include_account=False)
    )
    shroud = make_channel("shroud", "shroud", Platform.TWITCH)
    registry = _registry_with(shroud)  # "ninja" deliberately unresolvable
    favorites = InMemoryFavoriteRepository()
    service = _service(tmp_path, registry=registry, favorites=favorites)

    run = await service.run(legacy_path=legacy_file)

    assert len(run.created_favorite_ids) == 1
    assert run.skipped_bookmark_logins == ("ninja",)
    saved = await favorites.list_all()
    assert len(saved) == 1
    assert saved[0].channel_ref == shroud.ref


async def test_run_without_a_registry_skips_every_bookmark_with_a_warning(tmp_path: Path):
    legacy_file = _write_legacy_file(
        tmp_path, _legacy_payload(bookmarks=["shroud"], include_account=False)
    )
    service = _service(tmp_path, registry=None)

    run = await service.run(legacy_path=legacy_file)

    assert run.skipped_bookmark_logins == ("shroud",)
    assert run.status is LegacyMigrationStatus.COMPLETED_WITH_WARNINGS
    assert any("channel directory" in w for w in run.warnings)


async def test_run_migrates_resolvable_scheduled_download_presets(tmp_path: Path):
    legacy_file = _write_legacy_file(
        tmp_path,
        _legacy_payload(presets=[_preset("xqc"), _preset("baduser")], include_account=False),
    )
    xqc = make_channel("xqc", "xqc", Platform.TWITCH)
    registry = _registry_with(xqc)
    scheduled = InMemoryScheduledDownloadRepository()
    service = _service(tmp_path, registry=registry, scheduled=scheduled)

    run = await service.run(legacy_path=legacy_file)

    assert len(run.created_scheduled_download_ids) == 1
    assert run.skipped_scheduled_download_logins == ("baduser",)
    saved = await scheduled.list_all()
    assert len(saved) == 1
    assert saved[0].channel_ref == xqc.ref


async def test_run_disabled_master_switch_deactivates_every_migrated_preset(tmp_path: Path):
    payload = _legacy_payload(presets=[_preset("xqc")], include_account=False)
    payload["scheduledDownloads"] = _obj(
        "ScheduledDownloads", _enabled=False, _scheduledDownloadPresets=[_preset("xqc")]
    )
    legacy_file = _write_legacy_file(tmp_path, payload)
    xqc = make_channel("xqc", "xqc", Platform.TWITCH)
    registry = _registry_with(xqc)
    scheduled = InMemoryScheduledDownloadRepository()
    service = _service(tmp_path, registry=registry, scheduled=scheduled)

    await service.run(legacy_path=legacy_file)

    saved = await scheduled.list_all()
    assert saved[0].is_active is False


# --- run(): download history -------------------------------------------------


async def test_run_migrates_download_history_without_needing_a_registry(tmp_path: Path):
    legacy_file = _write_legacy_file(
        tmp_path,
        _legacy_payload(
            include_account=False, history=[_history_entry("1", "10"), _history_entry("2", "20")]
        ),
    )
    downloads = InMemoryDownloadRepository()
    service = _service(tmp_path, registry=None, downloads=downloads)

    run = await service.run(legacy_path=legacy_file)

    assert len(run.created_download_ids) == 2
    saved = await downloads.list_all()
    assert len(saved) == 2
    assert {
        d.media.channel_ref.external_id for d in saved if d.media.channel_ref is not None
    } == {"10", "20"}


# --- idempotency -------------------------------------------------


async def test_running_twice_against_the_same_file_is_a_no_op(tmp_path: Path):
    legacy_file = _write_legacy_file(
        tmp_path, _legacy_payload(bookmarks=["shroud"], include_account=False)
    )
    shroud = make_channel("shroud", "shroud", Platform.TWITCH)
    registry = _registry_with(shroud)
    favorites = InMemoryFavoriteRepository()
    runs = InMemoryLegacyMigrationRunRepository()
    service = _service(tmp_path, registry=registry, favorites=favorites, runs=runs)

    first = await service.run(legacy_path=legacy_file)
    second = await service.run(legacy_path=legacy_file)

    assert second.id == first.id
    assert len(await favorites.list_all()) == 1


async def test_a_changed_legacy_file_produces_a_new_run(tmp_path: Path):
    legacy_file = _write_legacy_file(
        tmp_path, _legacy_payload(bookmarks=["shroud"], include_account=False)
    )
    shroud = make_channel("shroud", "shroud", Platform.TWITCH)
    registry = _registry_with(shroud)
    runs = InMemoryLegacyMigrationRunRepository()
    service = _service(tmp_path, registry=registry, runs=runs)
    first = await service.run(legacy_path=legacy_file)

    legacy_file.write_bytes(
        json.dumps(_legacy_payload(bookmarks=["shroud", "ninja"], include_account=False)).encode()
    )
    second = await service.run(legacy_path=legacy_file)

    assert second.id != first.id


async def test_a_failed_run_is_retried_rather_than_treated_as_done(tmp_path: Path):
    legacy_file = tmp_path / "settings.json"
    legacy_file.write_bytes(b"not valid json")
    service = _service(tmp_path)

    with pytest.raises(LegacyCodecError):
        await service.run(legacy_path=legacy_file)

    legacy_file.write_bytes(json.dumps(_legacy_payload(include_account=False)).encode())
    run = await service.run(legacy_path=legacy_file)  # must not return a cached failure
    assert run.status in (
        LegacyMigrationStatus.COMPLETED,
        LegacyMigrationStatus.COMPLETED_WITH_WARNINGS,
    )


# --- failure persists a FAILED run and re-raises -------------------------------------------------


async def test_an_invalid_file_persists_a_failed_run_and_raises(tmp_path: Path):
    legacy_file = tmp_path / "settings.json"
    legacy_file.write_bytes(json.dumps({"nothingRecognisable": True}).encode())
    runs = InMemoryLegacyMigrationRunRepository()
    service = _service(tmp_path, runs=runs)

    with pytest.raises(LegacyValidationError):
        await service.run(legacy_path=legacy_file)

    all_runs = await runs.list_all()
    assert len(all_runs) == 1
    assert all_runs[0].status is LegacyMigrationStatus.FAILED
    assert all_runs[0].error_message is not None


async def test_an_unexpected_failure_mid_transform_marks_the_run_failed_and_reraises(
    tmp_path: Path,
):
    """Distinct from test_an_invalid_file_persists_a_failed_run_and_raises
    above — that one fails at ``parse_snapshot``, its own separate except
    clause. This is ``_transform_and_write``'s own generic handler,
    reached only once parsing already succeeded and something later in
    the pipeline breaks unexpectedly (e.g. the settings repository itself
    failing to save)."""
    legacy_file = _write_legacy_file(tmp_path, _legacy_payload(include_account=False))
    settings_repo = InMemorySettingsRepository()

    async def broken_save(settings):
        raise RuntimeError("disk full")

    settings_repo.save = broken_save  # type: ignore[method-assign]
    runs = InMemoryLegacyMigrationRunRepository()
    service = _service(tmp_path, settings=settings_repo, runs=runs)

    with pytest.raises(RuntimeError, match="disk full"):
        await service.run(legacy_path=legacy_file)

    all_runs = await runs.list_all()
    assert len(all_runs) == 1
    assert all_runs[0].status is LegacyMigrationStatus.FAILED
    assert all_runs[0].error_message == "disk full"


async def test_backup_is_made_even_though_the_file_turns_out_invalid(tmp_path: Path):
    legacy_file = tmp_path / "settings.json"
    legacy_file.write_bytes(json.dumps({"nothingRecognisable": True}).encode())
    service = _service(tmp_path)

    with pytest.raises(LegacyValidationError):
        await service.run(legacy_path=legacy_file)

    backups = list((tmp_path / "backups").iterdir())
    assert len(backups) == 1


# --- rollback -------------------------------------------------


async def test_rollback_removes_favorites_and_scheduled_downloads_this_run_created(
    tmp_path: Path,
):
    legacy_file = _write_legacy_file(
        tmp_path,
        _legacy_payload(bookmarks=["shroud"], presets=[_preset("xqc")], include_account=False),
    )
    shroud = make_channel("shroud", "shroud", Platform.TWITCH)
    xqc = make_channel("xqc", "xqc", Platform.TWITCH)
    registry = _registry_with(shroud, xqc)
    favorites = InMemoryFavoriteRepository()
    scheduled = InMemoryScheduledDownloadRepository()
    service = _service(tmp_path, registry=registry, favorites=favorites, scheduled=scheduled)
    run = await service.run(legacy_path=legacy_file)

    rolled_back = await service.rollback(run)

    assert rolled_back.status is LegacyMigrationStatus.ROLLED_BACK
    assert await favorites.list_all() == []
    assert await scheduled.list_all() == []


async def test_rollback_restores_the_exact_pre_migration_settings(tmp_path: Path):
    legacy_file = _write_legacy_file(tmp_path, _legacy_payload(include_account=False))
    settings_repo = InMemorySettingsRepository()
    original = Settings().updated(language="fr", max_concurrent_downloads=2)
    await settings_repo.save(original)
    service = _service(tmp_path, settings=settings_repo)
    run = await service.run(legacy_path=legacy_file)
    assert (await settings_repo.get()) != original  # sanity: migration did change it

    await service.rollback(run)

    assert await settings_repo.get() == original


async def test_rollback_deletes_the_migrated_token(tmp_path: Path):
    legacy_file = _write_legacy_file(tmp_path, _legacy_payload())
    token_store = FakeSecretTokenStore()
    service = _service(tmp_path, token_store=token_store)
    run = await service.run(legacy_path=legacy_file)
    assert token_store.load(_TOKEN_KEY) is not None

    await service.rollback(run)

    assert token_store.load(_TOKEN_KEY) is None


async def test_rollback_does_not_remove_migrated_download_history(tmp_path: Path):
    """Documented limitation (application/migration.py's rollback()
    docstring): DownloadRepository has no delete operation anywhere in
    this codebase, so a history rollback is deliberately partial."""
    legacy_file = _write_legacy_file(
        tmp_path, _legacy_payload(include_account=False, history=[_history_entry("1", "10")])
    )
    downloads = InMemoryDownloadRepository()
    service = _service(tmp_path, downloads=downloads)
    run = await service.run(legacy_path=legacy_file)

    await service.rollback(run)

    assert len(await downloads.list_all()) == 1


async def test_rollback_refuses_a_run_that_is_still_running_or_already_failed(tmp_path: Path):
    from twick_hub.domain.migration import LegacyMigrationRun

    service = _service(tmp_path)
    still_running = LegacyMigrationRun(
        source_path="x", source_sha256="a" * 64, backup_path="y"
    )

    with pytest.raises(ValueError):
        await service.rollback(still_running)
