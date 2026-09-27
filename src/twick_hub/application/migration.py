"""Orchestrates TwitchLink 3.5.x's detect-backup-read-validate-transform-
write-verify migration (Master Plan §52, FASE 15) and its rollback,
gluing ``infrastructure.migration``'s pure helpers to real repositories —
the same "one service, one persisted attempt/run per cycle" shape
``application.updates.service.UpdateService`` already established in
FASE 14, applied here to a different kind of one-time operation.

"Verify" (the flow's last named step) is the run's own final status:
every write in this module is immediately followed by a check of what
was actually written (``get``/``get_by_channel`` before/after each
save), rather than trusting each write blindly — that check is what lets
``created_*_ids`` distinguish "this run made this" from "this already
existed," which is what makes both idempotency (re-running is a no-op)
and rollback (undo only what this run actually added) possible at all.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from twick_hub.application.favorites import AddFavoriteUseCase
from twick_hub.application.platform_registry import PlatformRegistry
from twick_hub.domain.enums import LegacyMigrationStatus, Platform, Theme
from twick_hub.domain.migration import LegacyMigrationRun
from twick_hub.domain.protocols import (
    DownloadRepository,
    FavoriteRepository,
    LegacyMigrationRunRepository,
    ScheduledDownloadRepository,
    SecretTokenStore,
    SettingsRepository,
)
from twick_hub.domain.settings import Settings
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.migration import legacy_locator, legacy_reader, legacy_transform
from twick_hub.infrastructure.migration.legacy_codec import LegacyCodecError
from twick_hub.infrastructure.migration.legacy_reader import (
    LegacyPreferencesSnapshot,
    LegacyValidationError,
)

_TERMINAL_SUCCESS = (LegacyMigrationStatus.COMPLETED, LegacyMigrationStatus.COMPLETED_WITH_WARNINGS)

# Generous on purpose: a real legacy install has at most a few dozen
# scheduled-download presets, never hundreds — this is "don't truncate,"
# not "expect a large result" (FavoriteRepository/ScheduledDownloadRepository's
# own _DEFAULT_LIST_LIMIT of 500 is sized for the app's normal runtime use,
# not a one-time bulk import).
_MIGRATION_LIST_LIMIT = 10_000


class LegacyFileNotFoundError(Exception):
    """No TwitchLink 3.5.x ``settings.json`` was found — the common,
    expected outcome for anyone who never ran the legacy app. Callers
    should treat this as "nothing to migrate," not a failure."""


class LegacyMigrationService:
    def __init__(
        self,
        *,
        settings: SettingsRepository,
        favorites: FavoriteRepository,
        scheduled_downloads: ScheduledDownloadRepository,
        downloads: DownloadRepository,
        migration_runs: LegacyMigrationRunRepository,
        token_store: SecretTokenStore,
        token_store_key: str,
        backup_dir: Path,
        registry: PlatformRegistry | None = None,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._settings = settings
        self._favorites = favorites
        self._scheduled_downloads = scheduled_downloads
        self._downloads = downloads
        self._migration_runs = migration_runs
        self._token_store = token_store
        self._token_store_key = token_store_key
        self._backup_dir = backup_dir
        self._registry = registry
        self._clock = clock

    async def run(self, *, legacy_path: Path | None = None) -> LegacyMigrationRun:
        """FASE 15's full flow. Raises :class:`LegacyFileNotFoundError` if
        there's nothing to migrate, or re-raises whatever
        :class:`~twick_hub.infrastructure.migration.legacy_codec.LegacyCodecError`
        / :class:`~twick_hub.infrastructure.migration.legacy_reader.LegacyValidationError`
        / other exception stopped the run — always after persisting a
        ``FAILED`` :class:`LegacyMigrationRun` first, so the failure is
        inspectable afterwards (same "persist, then raise" shape as
        ``UpdateService.prepare``/``install``).

        Re-running against a byte-identical file that already completed
        (with or without warnings) is a no-op: the existing run is
        returned directly, nothing is read or written again.
        """
        detection = legacy_locator.detect(legacy_path)
        if not detection.found:
            raise LegacyFileNotFoundError(
                detection.reason or "no legacy TwitchLink settings file was found"
            )
        assert detection.path is not None  # detect() only sets found=True alongside a path

        now = self._clock()
        backup_path = legacy_locator.backup(detection.path, self._backup_dir, now=now)
        raw_bytes = legacy_reader.read_legacy_file(backup_path)
        source_sha256 = legacy_reader.sha256_of(raw_bytes)

        existing_run = await self._migration_runs.find_by_source_hash(source_sha256)
        if existing_run is not None and existing_run.status in _TERMINAL_SUCCESS:
            return existing_run

        run = LegacyMigrationRun(
            source_path=str(detection.path),
            source_sha256=source_sha256,
            backup_path=str(backup_path),
            status=LegacyMigrationStatus.RUNNING,
            started_at=now,
        )
        await self._migration_runs.save(run)

        try:
            snapshot = legacy_reader.parse_snapshot(raw_bytes)
        except (LegacyCodecError, LegacyValidationError) as exc:
            run = run.advanced(
                LegacyMigrationStatus.FAILED, now=self._clock(), error_message=str(exc)
            )
            await self._migration_runs.save(run)
            raise

        try:
            run = await self._transform_and_write(run, snapshot)
        except Exception as exc:
            run = run.advanced(
                LegacyMigrationStatus.FAILED, now=self._clock(), error_message=str(exc)
            )
            await self._migration_runs.save(run)
            raise

        await self._migration_runs.save(run)
        return run

    async def rollback(self, run: LegacyMigrationRun) -> LegacyMigrationRun:
        """Reverses everything this *specific* run created: favorites,
        scheduled downloads, the Settings row (restored to its exact
        pre-migration snapshot — see domain/migration.py's docstring for
        why that snapshot exists), and the credential-store token.

        Deliberately does **not** remove migrated download-history rows:
        ``DownloadRepository`` has no delete operation anywhere in this
        codebase (downloads are an append-only record everywhere else
        they're used), and adding one solely for this phase's rollback
        would be exactly the kind of invented capability Master Plan
        §0.5 rules out. A history rollback is therefore partial by
        design — documented in docs/architecture-decisions.md's FASE 15
        entry, not silently glossed over.
        """
        if run.status not in _TERMINAL_SUCCESS:
            raise ValueError(f"cannot roll back a run with status {run.status.value!r}")

        for favorite_id in run.created_favorite_ids:
            await self._favorites.delete(favorite_id)
        for scheduled_id in run.created_scheduled_download_ids:
            await self._scheduled_downloads.delete(scheduled_id)

        if run.settings_migrated and run.previous_settings_json is not None:
            data = json.loads(run.previous_settings_json)
            data["theme"] = Theme(data["theme"])
            await self._settings.save(Settings(**data))

        if run.account_token_migrated:
            self._token_store.delete(self._token_store_key)

        rolled_back = run.advanced(LegacyMigrationStatus.ROLLED_BACK, now=self._clock())
        await self._migration_runs.save(rolled_back)
        return rolled_back

    # --- transform + write (the "verify" step is inline: every write is
    # immediately checked against what already existed) -----------------

    async def _transform_and_write(
        self, run: LegacyMigrationRun, snapshot: LegacyPreferencesSnapshot
    ) -> LegacyMigrationRun:
        warnings: list[str] = list(snapshot.warnings)
        settings_migrated = False
        previous_settings_json: str | None = None
        account_token_migrated = False
        created_favorite_ids: list[str] = []
        created_scheduled_ids: list[str] = []
        created_download_ids: list[str] = []
        skipped_bookmarks: list[str] = []
        skipped_scheduled: list[str] = []

        overrides = legacy_transform.settings_overrides_from_legacy(snapshot)
        if overrides:
            existing_settings = await self._settings.get()
            previous_settings_json = json.dumps(asdict(existing_settings), default=str)
            await self._settings.save(existing_settings.updated(**overrides))
            settings_migrated = True

        if snapshot.account_secret is not None:
            try:
                self._token_store.save(self._token_store_key, snapshot.account_secret.token)
                account_token_migrated = True
            except Exception as exc:
                # OS credential store can fail in many ways; degrade, don't abort.
                warnings.append(f"could not migrate the Twitch session token: {exc}")
            else:
                expiration = snapshot.account_secret.expiration
                if expiration is not None and expiration < self._clock():
                    warnings.append(
                        "the migrated Twitch session token had already expired in the legacy "
                        "record — signing in again may be required"
                    )

        for entry in snapshot.download_history:
            channel_ref = (
                PlatformRef(platform=Platform.TWITCH, external_id=entry.channel_external_id)
                if entry.channel_external_id
                else None
            )
            download = legacy_transform.download_from_history_entry(entry, channel_ref=channel_ref)
            existing_download = await self._downloads.get(download.id)
            await self._downloads.save(download)
            if existing_download is None:
                created_download_ids.append(download.id)

        twitch_directory = (
            self._registry.channel_directories.get(Platform.TWITCH)
            if self._registry is not None
            else None
        )

        if twitch_directory is None:
            if snapshot.general.bookmarks or snapshot.scheduled_downloads.presets:
                warnings.append(
                    "no Twitch channel directory was available to this migration run — "
                    "bookmarks and scheduled downloads were left unresolved"
                )
            skipped_bookmarks.extend(snapshot.general.bookmarks)
            skipped_scheduled.extend(
                preset.channel_login for preset in snapshot.scheduled_downloads.presets
            )
        else:
            assert self._registry is not None  # twitch_directory came from self._registry above
            add_favorite = AddFavoriteUseCase(registry=self._registry, favorites=self._favorites)
            for login in snapshot.general.bookmarks:
                channel = await twitch_directory.find_channel(login)
                if channel is None:
                    skipped_bookmarks.append(login)
                    continue
                existing_favorite = await self._favorites.get_by_channel(channel.ref)
                favorite = await add_favorite.execute(channel.ref)
                if existing_favorite is None:
                    created_favorite_ids.append(favorite.id)

            existing_scheduled_ids = {
                s.id
                for s in await self._scheduled_downloads.list_all(limit=_MIGRATION_LIST_LIMIT)
            }
            for preset in snapshot.scheduled_downloads.presets:
                channel = await twitch_directory.find_channel(preset.channel_login)
                if channel is None:
                    skipped_scheduled.append(preset.channel_login)
                    continue
                scheduled = legacy_transform.scheduled_download_from_preset(
                    preset,
                    channel_ref=channel.ref,
                    master_enabled=snapshot.scheduled_downloads.enabled,
                )
                await self._scheduled_downloads.save(scheduled)
                if scheduled.id not in existing_scheduled_ids:
                    created_scheduled_ids.append(scheduled.id)

        has_warnings = bool(warnings) or bool(skipped_bookmarks) or bool(skipped_scheduled)
        status = (
            LegacyMigrationStatus.COMPLETED_WITH_WARNINGS
            if has_warnings
            else LegacyMigrationStatus.COMPLETED
        )
        return run.advanced(
            status,
            now=self._clock(),
            settings_migrated=settings_migrated,
            previous_settings_json=previous_settings_json,
            account_token_migrated=account_token_migrated,
            created_favorite_ids=tuple(created_favorite_ids),
            created_scheduled_download_ids=tuple(created_scheduled_ids),
            created_download_ids=tuple(created_download_ids),
            skipped_bookmark_logins=tuple(skipped_bookmarks),
            skipped_scheduled_download_logins=tuple(skipped_scheduled),
            warnings=tuple(warnings),
        )
