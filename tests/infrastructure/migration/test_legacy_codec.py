from __future__ import annotations

from datetime import datetime

import pytest

from twick_hub.infrastructure.migration.legacy_codec import LegacyCodecError, LegacyObject, decode

# --- primitives -------------------------------------------------


@pytest.mark.parametrize("value", [1, 1.5, True, False, None])
def test_primitives_pass_through_unchanged(value):
    assert decode(value) is value


def test_tagged_string_decodes_to_the_bare_value():
    assert decode("str:hello world") == "hello world"


def test_tagged_string_preserves_an_embedded_colon():
    assert decode("str:https://example.com/x") == "https://example.com/x"


def test_untagged_string_is_returned_as_is():
    assert decode("no-colon-here") == "no-colon-here"


def test_string_with_an_unrecognized_tag_is_returned_as_is():
    """Distinct from the no-colon case above: this has a colon and looks
    tagged, but the segment before it isn't any tag this codec knows
    about — same reasoning applies (return as-is; legacy_reader.py's own
    validation is what actually rejects a snapshot built from this)."""
    assert decode("weird-tag:something") == "weird-tag:something"


def test_url_tag_decodes_to_the_bare_url():
    assert decode("url:https://example.com/x") == "https://example.com/x"


def test_bytes_tag_decodes_to_bytes():
    assert decode("bytes:hello") == b"hello"


def test_bytearray_tag_decodes_to_bytearray():
    assert decode("bytearray:hello") == bytearray(b"hello")


def test_timezone_tag_decodes_to_the_bare_zone_id():
    assert decode("timezone:UTC") == "UTC"


# --- datetime -------------------------------------------------


def test_datetime_with_z_suffix_decodes_to_naive_utc():
    assert decode("datetime:2026-01-15T09:30:00.123Z") == datetime(2026, 1, 15, 9, 30, 0, 123000)


def test_datetime_empty_string_decodes_to_none():
    assert decode("datetime:") is None


def test_datetime_with_explicit_offset_is_normalized_to_utc():
    # +01:00 -> one hour earlier in UTC
    assert decode("datetime:2026-01-15T10:30:00.000+01:00") == datetime(2026, 1, 15, 9, 30, 0)


def test_unparseable_datetime_raises_codec_error():
    with pytest.raises(LegacyCodecError):
        decode("datetime:not-a-date")


# --- lists / tuples / dicts -------------------------------------------------


def test_list_decodes_recursively():
    assert decode(["str:a", "str:b", 1]) == ["a", "b", 1]


def test_tuple_blob_decodes_to_a_python_tuple():
    blob = {"__type__": "tuple", "data": ["str:a", "str:b"]}
    assert decode(blob) == ("a", "b")


def test_tuple_blob_missing_data_key_raises_codec_error():
    with pytest.raises(LegacyCodecError):
        decode({"__type__": "tuple"})


def test_dict_blob_decodes_to_a_plain_dict_without_the_type_tag():
    blob = {"__type__": "dict", "StreamHistory": {"__type__": "obj:pkg:Cls", "x": "str:y"}}
    result = decode(blob)
    assert isinstance(result, dict)
    assert "__type__" not in result
    assert isinstance(result["StreamHistory"], LegacyObject)


def test_untagged_dict_defaults_to_the_dict_branch():
    # A dict with no "__type__" key at all is treated as data:"dict" — the
    # legacy encoder never actually omits the tag, but decoding shouldn't
    # crash on a hand-edited file that does.
    assert decode({"a": "str:b"}) == {"a": "b"}


def test_unknown_type_tag_raises_codec_error():
    with pytest.raises(LegacyCodecError):
        decode({"__type__": "something-else"})


# --- LegacyObject -------------------------------------------------


def test_obj_blob_decodes_to_a_legacy_object_with_every_field_decoded():
    blob = {
        "__type__": "obj:AppData.Preferences:General",
        "_notify": True,
        "_bookmarks": ["str:shroud"],
    }

    result = decode(blob)

    assert isinstance(result, LegacyObject)
    assert result.type_name == "AppData.Preferences:General"
    assert result.get("_notify") is True
    assert result["_bookmarks"] == ["shroud"]
    assert "_notify" in result
    assert "_missing" not in result
    assert result.get("_missing", "default") == "default"


def test_obj_blob_class_name_strips_module_and_colon():
    result = decode({"__type__": "obj:Services.Twitch.GQL.TwitchGQLModels:Stream"})
    assert result.class_name == "Stream"


def test_obj_blob_with_empty_type_name_raises_codec_error():
    with pytest.raises(LegacyCodecError):
        decode({"__type__": "obj:"})


def test_nested_obj_blobs_decode_recursively():
    blob = {
        "__type__": "obj:pkg:Outer",
        "inner": {"__type__": "obj:pkg:Inner", "value": "str:x"},
    }

    result = decode(blob)

    assert isinstance(result.get("inner"), LegacyObject)
    assert result.get("inner").get("value") == "x"
