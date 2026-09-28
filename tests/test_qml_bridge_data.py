"""FASE 21b: the Favorites/Downloads/History bridges against the real
``Container`` (real SQLite, real ``PlatformRegistry``, real
``DownloadService``), plus the real QML pages rendering what they expose.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QCoreApplication, QMetaObject, QObject, QUrl
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuick import QQuickItem

from tests.application.fakes import FakeLiveStreamProvider
from twick_hub.application.platform_registry import PlatformAdapters, PlatformRegistry
from twick_hub.bootstrap.container import Container
from twick_hub.bootstrap.migrations import ensure_schema_migrated
from twick_hub.domain.collections import Favorite
from twick_hub.domain.content import Stream
from twick_hub.domain.downloads import Download
from twick_hub.domain.enums import DownloadStatus, MediaKind, Platform
from twick_hub.domain.value_objects import Media, PlatformRef
from twick_hub.presentation.qml_bridge.context import install_bridges
from twick_hub.presentation.qml_bridge.downloads_model import DownloadsModel
from twick_hub.presentation.qml_bridge.favorites_model import FavoritesModel
from twick_hub.presentation.qml_bridge.history_model import HistoryModel, format_size
from twick_hub.presentation.qml_bridge.tasks import TaskRunner

_QML_PAGES = Path(__file__).resolve().parents[1] / "src/twick_hub/presentation/qml/pages"


def _ref(platform: Platform, external_id: str) -> PlatformRef:
    return PlatformRef(platform=platform, external_id=external_id)


def _media(title: str, *, kind: MediaKind = MediaKind.VIDEO, platform=Platform.TWITCH) -> Media:
    return Media(kind=kind, ref=_ref(platform, f"m-{title}"), title=title)


def _download(title: str, status: DownloadStatus, **kwargs) -> Download:
    media_kwargs = {k: kwargs.pop(k) for k in ("kind", "platform") if k in kwargs}
    return Download(
        media=_media(title, **media_kwargs),
        destination_path=kwargs.pop("destination_path", f"/tmp/{title}.mp4"),
        quality_label="720p",
        status=status,
        **kwargs,
    )


def _inert_runner() -> TaskRunner:
    return TaskRunner(lambda coro: coro.close())


@pytest.fixture
def migrated(container: Container) -> Container:
    ensure_schema_migrated(container.engine)
    return container


def _titles(model) -> list[str]:
    return [row.get("title", row.get("channelName")) for row in model.rows()]


# --- Favorites ------------------------------------------------------------


async def test_favorites_empty_is_loaded_and_empty(migrated: Container, qapp):
    model = FavoritesModel(migrated.favorites, migrated.platform_registry, _inert_runner())
    assert model.loaded is False

    await model.reload()

    assert model.loaded is True
    assert model.count == 0


async def test_favorites_list_in_position_order_with_unknown_live_state(migrated: Container, qapp):
    await migrated.favorites.save(Favorite(_ref(Platform.KICK, "adin"), position=1))
    await migrated.favorites.save(Favorite(_ref(Platform.TWITCH, "111"), position=0))
    model = FavoritesModel(migrated.favorites, migrated.platform_registry, _inert_runner())

    await model.reload()

    rows = model.rows()
    assert [(r["channelName"], r["platform"], r["liveState"]) for r in rows] == [
        ("111", "twitch", "unknown"),
        ("adin", "kick", "unknown"),
    ]


async def test_favorites_live_state_uses_registry_where_a_platform_can_check(
    migrated: Container, qapp
):
    live_ref = _ref(Platform.TWITCH, "111")
    stream = Stream(
        ref=_ref(Platform.TWITCH, "s1"),
        channel_ref=live_ref,
        title="t",
        category=None,
        started_at=datetime.now(),
        viewer_count=1,
    )
    registry = PlatformRegistry(
        {
            Platform.TWITCH: PlatformAdapters(
                live_stream_provider=FakeLiveStreamProvider(streams={"111": stream})
            ),
            Platform.KICK: PlatformAdapters(),
        }
    )
    for position, ref in enumerate(
        [live_ref, _ref(Platform.TWITCH, "222"), _ref(Platform.KICK, "adin")]
    ):
        await migrated.favorites.save(Favorite(ref, position=position))
    model = FavoritesModel(migrated.favorites, registry, _inert_runner())

    await model.reload()

    assert [r["liveState"] for r in model.rows()] == ["live", "offline", "unknown"]


async def test_favorites_live_check_failure_keeps_rows_unknown(migrated: Container, qapp):
    class _Broken:
        async def get_live_stream(self, channel_ref: PlatformRef):
            raise ConnectionError("network down")

    registry = PlatformRegistry(
        {
            Platform.TWITCH: PlatformAdapters(live_stream_provider=_Broken()),
            Platform.KICK: PlatformAdapters(),
        }
    )
    await migrated.favorites.save(Favorite(_ref(Platform.TWITCH, "111")))
    model = FavoritesModel(migrated.favorites, registry, _inert_runner())

    await model.reload()

    assert [r["liveState"] for r in model.rows()] == ["unknown"]


# --- Downloads ----------------------------------------------------------


@dataclass
class _StubEngine:
    percent: dict[str, float] = field(default_factory=dict)
    cancelled: list[str] = field(default_factory=list)

    async def enqueue(self, job) -> None: ...

    async def cancel(self, job_id: str) -> None:
        self.cancelled.append(job_id)

    async def progress_of(self, job_id: str) -> float:
        return self.percent.get(job_id, 0.0)


async def test_downloads_lists_only_active_oldest_first_with_live_progress(
    migrated: Container, qapp
):
    now = datetime.now()
    older = _download("older", DownloadStatus.DOWNLOADING, created_at=now - timedelta(hours=1))
    newer = _download("newer", DownloadStatus.QUEUED, created_at=now)
    done = _download("done", DownloadStatus.COMPLETED)
    for d in (newer, done, older):
        await migrated.downloads.save(d)
    engine = _StubEngine(percent={older.id: 62.0})
    model = DownloadsModel(migrated.downloads, engine, _inert_runner())

    await model.reload()

    rows = model.rows()
    assert [r["title"] for r in rows] == ["older", "newer"]
    assert rows[0]["progress"] == pytest.approx(0.62)
    assert rows[0]["statusLabel"] == "Downloading"
    assert rows[1]["statusLabel"] == "Queued"
    assert model.hasActive is True


async def test_downloads_progress_tick_updates_rows_in_place(migrated: Container, qapp):
    download = _download("vod", DownloadStatus.DOWNLOADING)
    await migrated.downloads.save(download)
    engine = _StubEngine(percent={download.id: 10.0})
    model = DownloadsModel(migrated.downloads, engine, _inert_runner())
    await model.reload()
    resets: list[bool] = []
    changed: list[int] = []
    model.modelReset.connect(lambda: resets.append(True))
    model.dataChanged.connect(lambda top_left, *_: changed.append(top_left.row()))

    engine.percent[download.id] = 40.0
    await model.reload()

    assert model.rows()[0]["progress"] == pytest.approx(0.40)
    assert changed == [0]
    assert resets == []  # no delegate rebuild on a plain progress tick


async def test_downloads_live_capture_has_no_known_progress(migrated: Container, qapp):
    await migrated.downloads.save(
        _download("live", DownloadStatus.DOWNLOADING, kind=MediaKind.STREAM)
    )
    model = DownloadsModel(migrated.downloads, _StubEngine(), _inert_runner())

    await model.reload()

    assert model.rows()[0]["progressKnown"] is False


async def test_downloads_has_active_signal_follows_the_queue(migrated: Container, qapp):
    download = _download("vod", DownloadStatus.DOWNLOADING)
    await migrated.downloads.save(download)
    model = DownloadsModel(migrated.downloads, _StubEngine(), _inert_runner())
    emitted: list[bool] = []
    model.hasActiveChanged.connect(lambda: emitted.append(bool(model.hasActive)))

    await model.reload()
    await migrated.downloads.save(replace(download, status=DownloadStatus.COMPLETED))
    await model.reload()

    assert emitted == [True, False]


async def test_downloads_cancel_goes_through_the_real_engine_and_drops_the_row(
    migrated: Container, qapp
):
    download = _download("vod", DownloadStatus.DOWNLOADING)
    await migrated.downloads.save(download)
    model = DownloadsModel(migrated.downloads, migrated.download_service, _inert_runner())
    await model.reload()

    await model._cancel_then_reload(download.id)

    stored = await migrated.downloads.get(download.id)
    assert stored is not None
    assert stored.status is DownloadStatus.CANCELLED
    assert model.count == 0


# --- History ------------------------------------------------------------------


def test_format_size():
    assert format_size(None) == "—"
    assert format_size(512) == "512 B"
    assert format_size(84 * 1024**2) == "84.0 MB"
    assert format_size(int(2.1 * 1024**3)) == "2.1 GB"


async def test_history_lists_finished_newest_first_with_outcomes(migrated: Container, qapp):
    now = datetime(2026, 9, 3, 12, 0)
    ok = _download("ok", DownloadStatus.COMPLETED, completed_at=now, file_size_bytes=84 * 1024**2)
    failed = _download(
        "failed",
        DownloadStatus.FAILED,
        completed_at=now - timedelta(days=1),
        error_message="boom",
    )
    cancelled = _download("cancelled", DownloadStatus.CANCELLED, created_at=now - timedelta(days=2))
    running = _download("running", DownloadStatus.DOWNLOADING)
    for d in (cancelled, running, ok, failed):
        await migrated.downloads.save(d)
    model = HistoryModel(migrated.downloads, _inert_runner())

    await model.reload()

    rows = model.rows()
    assert [r["title"] for r in rows] == ["ok", "failed", "cancelled"]
    assert (rows[0]["date"], rows[0]["size"], rows[0]["outcome"]) == ("Sep 3, 2026", "84.0 MB", "")
    assert (rows[1]["outcome"], rows[1]["errorMessage"]) == ("Failed", "boom")
    assert rows[2]["outcome"] == "Cancelled"


async def test_history_open_folder_uses_the_download_directory(
    migrated: Container, qapp, tmp_path: Path
):
    download = _download("ok", DownloadStatus.COMPLETED, destination_path=str(tmp_path / "ok.mp4"))
    await migrated.downloads.save(download)
    opened: list[Path] = []
    model = HistoryModel(
        migrated.downloads, _inert_runner(), opener=lambda folder: opened.append(folder) or True
    )
    await model.reload()

    assert model.openFolder(download.id) is True
    assert opened == [tmp_path]
    assert model.openFolder("no-such-id") is False


async def test_history_open_folder_fails_when_the_directory_is_gone(
    migrated: Container, qapp, tmp_path: Path
):
    download = _download(
        "ok", DownloadStatus.COMPLETED, destination_path=str(tmp_path / "gone" / "ok.mp4")
    )
    await migrated.downloads.save(download)
    opened: list[Path] = []
    model = HistoryModel(
        migrated.downloads, _inert_runner(), opener=lambda folder: opened.append(folder) or True
    )
    await model.reload()

    assert model.openFolder(download.id) is False
    assert opened == []


# --- the real QML pages, over the real bridges --------------------------------


def _walk(item: QQuickItem):
    yield item
    for child in item.childItems():
        yield from _walk(child)


def _of_type(root: QQuickItem, qml_type: str) -> list[QQuickItem]:
    return [i for i in _walk(root) if i.metaObject().className().startswith(qml_type + "_QMLTYPE")]


def _texts_of(item: QQuickItem) -> list[str]:
    """Built-in ``Text`` items aren't compiled QML types, so ``_of_type``
    (which matches on the ``_QMLTYPE`` suffix Qt gives user-defined
    components) can't find them — match the plain ``QQuickText`` class
    name instead."""
    return [i.property("text") for i in _walk(item) if i.metaObject().className() == "QQuickText"]


async def _load_page(container: Container, page: str, warnings: list[str]):
    loop = asyncio.get_running_loop()
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda ws: warnings.extend(str(w.toString()) for w in ws))
    bridges = install_bridges(engine, container, TaskRunner(loop.create_task))
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(_QML_PAGES / page)))
    obj = component.create()
    assert component.errors() == [], [e.toString() for e in component.errors()]
    assert isinstance(obj, QQuickItem)
    for _ in range(10):  # let the page's refresh() run and the Repeaters instantiate
        await asyncio.sleep(0.05)
        QCoreApplication.processEvents()
    return engine, bridges, obj, component


async def test_favorites_page_renders_real_rows_and_hides_the_empty_state(
    migrated: Container, qapp
):
    await migrated.favorites.save(Favorite(_ref(Platform.TWITCH, "111"), position=0))
    await migrated.favorites.save(Favorite(_ref(Platform.KICK, "adin"), position=1))
    warnings: list[str] = []

    engine, bridges, page, component = await _load_page(migrated, "FavoritesPage.qml", warnings)

    assert warnings == []
    assert len(_of_type(page, "PlatformBadge")) == 2
    assert [e.isVisible() for e in _of_type(page, "EmptyState")] == [False]
    del engine, bridges, component


async def test_favorites_page_shows_the_empty_state_when_there_are_none(migrated: Container, qapp):
    warnings: list[str] = []

    engine, bridges, page, component = await _load_page(migrated, "FavoritesPage.qml", warnings)

    assert warnings == []
    assert _of_type(page, "PlatformBadge") == []
    assert [e.isVisible() for e in _of_type(page, "EmptyState")] == [True]
    del engine, bridges, component


async def test_downloads_page_ticks_only_while_something_is_active(migrated: Container, qapp):
    warnings: list[str] = []
    engine, bridges, page, component = await _load_page(migrated, "DownloadsPage.qml", warnings)
    timer = next(o for o in page.findChildren(QObject) if o.metaObject().className() == "QQmlTimer")
    assert timer.property("running") is False  # nothing in flight: no polling at idle

    await migrated.downloads.save(_download("vod", DownloadStatus.DOWNLOADING))
    bridges.downloads.refresh()
    for _ in range(10):
        await asyncio.sleep(0.05)
        QCoreApplication.processEvents()

    assert timer.property("running") is True
    assert len(_of_type(page, "PlatformBadge")) == 1
    assert warnings == []
    del engine, component


async def test_history_page_renders_finished_downloads(migrated: Container, qapp):
    await migrated.downloads.save(
        _download("ok", DownloadStatus.COMPLETED, completed_at=datetime.now())
    )
    await migrated.downloads.save(_download("running", DownloadStatus.DOWNLOADING))
    warnings: list[str] = []

    engine, bridges, page, component = await _load_page(migrated, "HistoryPage.qml", warnings)

    assert warnings == []
    assert len(_of_type(page, "PlatformBadge")) == 1
    del engine, bridges, component


async def test_home_page_shows_real_favorites_and_downloads_counts(migrated: Container, qapp):
    """RISK-UI-04 fix: Home's Favorites/Downloads stat cards reuse
    favoritesModel/downloadsModel (FASE 21b) instead of the old literals.
    "Live now" is untouched — still mock, out of scope until 21c/21d."""
    await migrated.favorites.save(Favorite(_ref(Platform.TWITCH, "111"), position=0))
    await migrated.favorites.save(Favorite(_ref(Platform.KICK, "adin"), position=1))
    await migrated.downloads.save(_download("vod", DownloadStatus.DOWNLOADING))
    warnings: list[str] = []

    engine, bridges, page, component = await _load_page(migrated, "HomePage.qml", warnings)

    stat_cards = _of_type(page, "SectionCard")[:3]
    by_label = {}
    for card in stat_cards:
        value, label = _texts_of(card)
        by_label[label] = value

    assert warnings == []
    assert by_label["Favorites"] == "2"
    assert by_label["Downloads in progress"] == "1"
    assert by_label["Live now"] == "2"  # unchanged: still the FASE 2 mock value
    del engine, bridges, component


async def test_home_refresh_button_rereads_the_real_counters_and_claims_nothing(
    migrated: Container, qapp
):
    """FASE 22.1: the button used to run a 900 ms timer and announce
    "Everything is up to date" without checking anything. It now re-runs the
    same two real queries the page runs on load, and says nothing it did not
    verify."""
    await migrated.favorites.save(Favorite(_ref(Platform.TWITCH, "111"), position=0))
    warnings: list[str] = []
    engine, bridges, page, component = await _load_page(migrated, "HomePage.qml", warnings)
    toasts: list[tuple[str, str]] = []
    toast_controller: Any = engine.singletonInstance("TwickHub", "ToastController")
    toast_controller.toastRequested.connect(lambda message, kind: toasts.append((message, kind)))

    def favorites_card() -> str:
        for card in _of_type(page, "SectionCard")[:3]:
            value, label = _texts_of(card)
            if label == "Favorites":
                return value
        raise AssertionError("no Favorites stat card")

    assert favorites_card() == "1"
    await migrated.favorites.save(Favorite(_ref(Platform.KICK, "adin"), position=1))
    refresh = next(b for b in _of_type(page, "AppButton") if b.property("text") == "Refresh")

    QMetaObject.invokeMethod(refresh, "click")
    for _ in range(25):  # longer than the old fake 900 ms timer would have needed
        await asyncio.sleep(0.05)
        QCoreApplication.processEvents()

    assert favorites_card() == "2"
    assert toasts == []
    assert warnings == []
    del engine, bridges, component
