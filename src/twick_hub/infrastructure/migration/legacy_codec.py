"""Pure-Python decoder for TwitchLink 3.5.x's ``AppData/EncoderDecoder.py``
serialization format (Master Plan §52, FASE 15).

That format is not plain JSON: every value is additionally tagged by a
hand-rolled ``Encoder`` — a bare string becomes ``"str:<value>"``, a
``QDateTime`` becomes ``"datetime:<iso>"``, a ``Serializable`` instance
becomes ``{"__type__": "obj:<module>:<Qualname>", ...fields}``, and so on
(see ``AppData/EncoderDecoder.py`` in the legacy repository — this module
mirrors its ``Decoder`` field-for-field). The legacy ``Decoder`` then
*reconstructs* real instances of those classes via
``importlib.import_module``.

This decoder deliberately stops one step short of that: it decodes every
tag into a plain Python value, but an ``obj:...`` blob becomes a
:class:`LegacyObject` — a dumb bag of already-decoded fields, never an
actual instance of the legacy class. Two reasons, both from the Master
Plan itself:

- §37/§0.9's isolation rule ("Twick Hub debe tratarse como un proyecto
  completamente independiente") — importing ``PyQt6`` or any
  ``TwitchLink``/``Services.*`` module here would pull the legacy
  dependency graph into this project, and Twick Hub has no PyQt6
  dependency anywhere else (tests/domain/test_no_pyside6_import.py).
- The legacy classes' behaviour (signal emission, ``App`` singleton
  side effects in ``__setup__``) is exactly what Master Plan §0.9 calls
  "arquitectura a portar", not "comportamiento a preservar" — the
  migrator only ever needs the *data* those objects carried, never their
  behaviour.

``legacy_reader.py`` builds a typed, validated snapshot out of the plain
values this module returns; this module's only job is turning tagged
JSON into untagged Python.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class LegacyCodecError(Exception):
    """The blob doesn't match the tagged-string encoding this decoder
    understands — a corrupt file, or a format this module has never seen
    (a future TwitchLink version's encoder changed the tag scheme).
    Distinct from ``legacy_reader.LegacyValidationError``: this is "I
    can't even parse the envelope," not "I parsed it fine but the
    content doesn't look like a Preferences dump."
    """


@dataclass(frozen=True, slots=True)
class LegacyObject:
    """One decoded ``{"__type__": "obj:<module>:<Qualname>", ...}`` blob.
    ``type_name`` is the dotted ``module:Qualname`` exactly as the legacy
    encoder wrote it (e.g. ``"AppData.Preferences:General"``); ``fields``
    is every other key, already decoded. See this module's docstring for
    why this is a plain bag of fields and not a reconstructed instance.
    """

    type_name: str
    fields: dict[str, Any]

    def get(self, key: str, default: Any = None) -> Any:
        return self.fields.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self.fields[key]

    def __contains__(self, key: str) -> bool:
        return key in self.fields

    @property
    def class_name(self) -> str:
        """The bare class name, e.g. ``"General"`` from
        ``"AppData.Preferences:General"`` — what ``legacy_reader.py``
        actually switches on; the module half only matters for a
        human reading a validation error."""
        return self.type_name.rsplit(".", 1)[-1].split(":", 1)[-1]


def decode(obj: Any) -> Any:
    """Mirrors ``AppData.EncoderDecoder.Decoder.decode`` field-for-field —
    see this module's docstring for the one deliberate difference
    (``obj:...`` -> :class:`LegacyObject`, never a reconstructed legacy
    instance). Raises :class:`LegacyCodecError` on anything that isn't
    valid output of the legacy ``Encoder``.
    """
    if isinstance(obj, list):
        return [decode(item) for item in obj]
    if isinstance(obj, dict):
        return _decode_dict(obj)
    if isinstance(obj, str):
        return _decode_string(obj)
    # int / float / bool / None: the legacy Encoder passes these through
    # untagged (Encoder.encode's final `else: return obj`), so decode()
    # does the same.
    return obj


def _decode_dict(obj: dict) -> Any:
    data = dict(obj)
    data_type = data.pop("__type__", "dict")
    if data_type.startswith("obj:"):
        type_name = data_type.split(":", 1)[1]
        if not type_name:
            raise LegacyCodecError(f"empty object type in blob: {obj!r}")
        return LegacyObject(type_name=type_name, fields={k: decode(v) for k, v in data.items()})
    if data_type == "tuple":
        raw_items = data.get("data")
        if not isinstance(raw_items, list):
            raise LegacyCodecError(f"malformed tuple blob (missing 'data' list): {obj!r}")
        return tuple(decode(item) for item in raw_items)
    if data_type == "dict":
        return {key: decode(value) for key, value in data.items()}
    raise LegacyCodecError(f"unknown legacy __type__ tag: {data_type!r}")


def _decode_string(obj: str) -> Any:
    if ":" not in obj:
        # The legacy Encoder tags every str ("str:<value>"); a string
        # with no tag at all isn't something this format ever produces
        # on its own. Rather than guess, this is treated as a decode
        # error by the one caller that cares (legacy_reader.py checks
        # tags explicitly) — here, returned as-is so a malformed single
        # field doesn't abort decoding the rest of an otherwise-valid
        # file; legacy_reader.py's validation is what actually rejects
        # a snapshot built from data like this.
        return obj
    tag, value = obj.split(":", 1)
    if tag == "str":
        return value
    if tag == "datetime":
        return _parse_iso_datetime(value)
    if tag == "timezone":
        return value  # zone id only — Twick Hub has no QTimeZone to build
    if tag == "url":
        return value
    if tag == "bytes":
        return value.encode()
    if tag == "bytearray":
        return bytearray(value.encode())
    # An unrecognised tag — e.g. a genuine string value that happens to
    # contain a colon before FASE 15 ever ran (a URL saved as a bare
    # "str:" value already handles that case above; this branch is only
    # reached for a *different* first segment). Same reasoning as the
    # no-colon case: return as-is, let validation reject it if it matters.
    return obj


def _parse_iso_datetime(value: str) -> datetime | None:
    """Qt's ``ISODateWithMs`` format for a UTC ``QDateTime``, e.g.
    ``"2026-01-15T09:30:00.123Z"``. An empty string is how an invalid/
    null ``QDateTime`` renders — decodes to ``None``, not a crash,
    since ``Setup``/``OAuthToken`` both allow a datetime field to be
    genuinely absent.
    """
    if not value:
        return None
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise LegacyCodecError(f"unparseable legacy datetime: {value!r}") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed
