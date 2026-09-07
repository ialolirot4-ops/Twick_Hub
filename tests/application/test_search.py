from tests.application.fakes import FakeChannelDirectory, make_channel
from twitchlink_next.application.search import SearchContentUseCase
from twitchlink_next.domain.enums import Platform


def _use_case() -> SearchContentUseCase:
    twitch = FakeChannelDirectory()
    twitch.add(make_channel("t1", "northernlion", Platform.TWITCH))
    kick = FakeChannelDirectory()
    # same query string, different platform
    kick.add(make_channel("t1", "northernlion", Platform.KICK))
    return SearchContentUseCase(directories={Platform.TWITCH: twitch, Platform.KICK: kick})


async def test_search_with_no_platform_filter_searches_every_platform():
    results = await _use_case().execute("t1")
    assert {channel.ref.platform for channel in results} == {Platform.TWITCH, Platform.KICK}


async def test_search_filtered_to_one_platform_only_queries_that_one():
    results = await _use_case().execute("t1", platform=Platform.KICK)
    assert len(results) == 1
    assert results[0].ref.platform == Platform.KICK


async def test_search_for_a_platform_with_no_directory_returns_empty():
    use_case = SearchContentUseCase(directories={})
    results = await use_case.execute("anything", platform=Platform.TWITCH)
    assert results == []


async def test_search_with_no_matches_returns_empty_not_none():
    results = await _use_case().execute("does-not-exist")
    assert results == []
