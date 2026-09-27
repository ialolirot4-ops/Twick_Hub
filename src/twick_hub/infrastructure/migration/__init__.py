"""Legacy (TwitchLink 3.5.x) data migration — Master Plan §52, FASE 15.

See ``legacy_codec.py`` (format decoding), ``legacy_locator.py``
(detect/backup), ``legacy_reader.py`` (read/validate) and
``legacy_transform.py`` (pure domain mapping). The orchestrator that
ties these into the full detect-backup-read-validate-transform-write-
verify flow is ``application.migration.LegacyMigrationService`` — kept
out of this package because it needs real repositories/a token store/a
channel directory, none of which belong in ``infrastructure.migration``
itself (this package has no database or keyring dependency anywhere).
"""
