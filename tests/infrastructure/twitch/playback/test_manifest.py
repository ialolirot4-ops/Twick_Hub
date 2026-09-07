from twitchlink_next.infrastructure.twitch.playback.manifest import parse_variant_playlist

_SAMPLE_PLAYLIST = """
#EXTM3U
#EXT-X-TWITCH-INFO:...
#EXT-X-MEDIA:TYPE=VIDEO,GROUP-ID="chunked",NAME="1080p60 (Source)",AUTOSELECT=YES,DEFAULT=YES
1080p60/index-muted.m3u8
#EXT-X-MEDIA:TYPE=VIDEO,GROUP-ID="720p60",NAME="720p60",AUTOSELECT=YES,DEFAULT=YES
720p60/index-muted.m3u8
#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio_only",NAME="Audio Only",AUTOSELECT=YES,DEFAULT=YES
audio_only/index-muted.m3u8
""".strip()


def test_parses_every_variant():
    variants = parse_variant_playlist(_SAMPLE_PLAYLIST, base_url="https://usher.ttvnw.net/api/x/")
    assert {v.group_id for v in variants} == {"chunked", "720p60", "audio_only"}


def test_resolves_relative_urls_against_the_base_url():
    base_url = "https://usher.ttvnw.net/api/x/master.m3u8"
    variants = parse_variant_playlist(_SAMPLE_PLAYLIST, base_url=base_url)
    chunked = next(v for v in variants if v.group_id == "chunked")
    assert chunked.url == "https://usher.ttvnw.net/api/x/1080p60/index-muted.m3u8"


def test_source_quality_always_sorts_first_regardless_of_numeric_resolution():
    variants = parse_variant_playlist(_SAMPLE_PLAYLIST, base_url="https://example.invalid/")
    assert variants[0].group_id == "chunked"
    assert variants[0].is_source is True


def test_higher_resolution_sorts_above_lower_resolution():
    variants = parse_variant_playlist(_SAMPLE_PLAYLIST, base_url="https://example.invalid/")
    non_source = [v for v in variants if not v.is_source]
    assert non_source[0].group_id == "720p60"
    assert non_source[-1].group_id == "audio_only"


def test_display_name_uses_parsed_quality_and_frame_rate():
    variants = parse_variant_playlist(_SAMPLE_PLAYLIST, base_url="https://example.invalid/")
    chunked = next(v for v in variants if v.group_id == "chunked")
    assert chunked.quality == 1080
    assert chunked.frame_rate == 60
    assert chunked.display_name == "1080p60"


def test_audio_only_is_flagged():
    variants = parse_variant_playlist(_SAMPLE_PLAYLIST, base_url="https://example.invalid/")
    audio = next(v for v in variants if v.group_id == "audio_only")
    assert audio.is_audio_only is True


def test_empty_playlist_returns_no_variants():
    assert parse_variant_playlist("#EXTM3U\n", base_url="https://example.invalid/") == []
