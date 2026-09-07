from sqlalchemy import text

from twitchlink_next.bootstrap.container import Container


def test_engine_connects_and_executes(container: Container):
    with container.engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar_one()
    assert result == 1


def test_session_factory_produces_working_sessions(container: Container):
    session = container.session_factory()
    try:
        assert session.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        session.close()
