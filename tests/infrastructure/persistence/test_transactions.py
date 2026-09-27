"""Every repository in this package follows the same pattern: ``with
self._session_factory() as session: ...; session.commit()``. Rather than
repeat a transaction test per repository, this proves the shared pattern
itself — uncommitted work is invisible to other sessions, and exiting the
``with`` block without an explicit ``commit()`` leaves nothing behind
(``Session.close()`` rolls back any still-open transaction, which is
exactly what happens whenever a repository method raises before reaching
its own ``session.commit()`` call).
"""

from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from twick_hub.domain.enums import Platform
from twick_hub.domain.identity import Channel, User
from twick_hub.domain.value_objects import PlatformRef
from twick_hub.infrastructure.persistence.channel_repository import SqlChannelRepository
from twick_hub.infrastructure.persistence.models import ChannelRow


async def test_uncommitted_work_is_invisible_to_another_session(session_factory: sessionmaker):
    with session_factory() as session:
        session.add(
            ChannelRow(
                platform="twitch",
                external_id="mid-tx",
                username="x",
                display_name="X",
                is_live=False,
            )
        )
        # deliberately no commit() here

        with session_factory() as other_session:
            assert other_session.get(ChannelRow, ("twitch", "mid-tx")) is None


async def test_closing_without_commit_rolls_back(session_factory: sessionmaker):
    with session_factory() as session:
        session.add(
            ChannelRow(
                platform="twitch", external_id="never-committed", username="x", display_name="X"
            )
        )
        # `with` exits here with no session.commit() — Session.close() rolls back.

    with session_factory() as verify_session:
        assert verify_session.get(ChannelRow, ("twitch", "never-committed")) is None


async def test_a_repository_save_is_durably_committed(session_factory: sessionmaker):
    ref = PlatformRef(platform=Platform.TWITCH, external_id="durable")
    channel = Channel(ref=ref, user=User(ref=ref, username="x", display_name="X"))
    repo = SqlChannelRepository(session_factory)

    await repo.save(channel)

    with session_factory() as verify_session:
        assert verify_session.get(ChannelRow, ("twitch", "durable")) is not None
