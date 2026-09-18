PROJECT_NAME: Twick Hub
MASTER_PLAN_VERSION: 3.0
CURRENT_PHASE: FASE 7 — Download Engine
PHASE_STATUS: PASS
LAST_COMPLETED_PHASE: FASE 7 — Download Engine
SOURCE_BASELINE: git commit 8760a14 ("Fase5") + FASE 6 changes (delivered separately) + FASE 7 changes delivered in this package — none of these are committed to git yet; the user's local git history should record them once applied
PROJECT_VERSION: 0.1.0 (pyproject.toml, unchanged this phase)
TEST_STATUS: 324/324 passed (257 pre-FASE-7 [239 baseline + 18 FASE 6] + 67 new in tests/infrastructure/downloads/)
STATIC_ANALYSIS_STATUS: ruff check src/twick_hub tests — all checks passed; pyright src/twick_hub tests — 0 errors, 0 warnings, 0 informations. (Both scoped to exclude src/twitchlink_next/, the stale package tracked as RISK-BUILD-01 — unrelated to this phase.)
RUNTIME_VALIDATION_STATUS: PARTIAL — AsyncioProcessRunner tested against real subprocesses (/usr/bin/true, /usr/bin/false, /usr/bin/sleep, a real Python one-liner for stderr capture), including a real timeout+kill and proof no shell is used. Everything else (HTTP segment fetching, real ffmpeg, real HLS manifests) tested against fakes only — no live Twitch/Kick network access or real ffmpeg binary available in this environment.
PACKAGING_STATUS: PENDING — out of scope (FASE 19).
KNOWN_BLOCKERS: none blocking FASE 7's own closure.
KNOWN_RISKS:
  - RISK-ARCH-02 (new) — EnqueueDownloadUseCase (FASE 3) still depends on a single global PlaybackResolver, not PlatformRegistry; low impact until Kick gets a PlaybackResolver.
  - RISK-ARCH-03 (new) — download engine not wired into bootstrap/container.py.
  - RISK-DATA-01 (new) — no locking/optimistic concurrency on Download record writes; racy pause-vs-transition writes possible in principle. Explicitly deferred to FASE 8 ("transactions").
  - RISK-RESUME-01 (new) — no crash-recovery for PAUSED downloads; a finished live stream cannot be resumed after an app restart (inherent to HLS live capture, not a defect).
  - RISK-UX-01 (new) — pausing a live capture doesn't stop polling its manifest (wasteful, not incorrect); deferred per "measure before optimizing" (§19).
  - Carried over from FASE 6: RISK-BUILD-01, RISK-ARCH-01, RISK-UI-02.
  - Carried over from FASE 0-5: RISK-TWITCH-01..04, RISK-SEC-01, RISK-KICK-01..03, RISK-UI-01, RISK-PKG-01, RISK-PROD-01..02.
IMPORTANT_DECISIONS: AD-32 (DownloadStatus retroactive correction: PENDING→QUEUED, +PREPARING, +PROCESSING), AD-33 (progress total deferred/unknown by design, segments_completed_of() fallback), AD-34 (cancellation double-checked after the poll loop, closing a real partial-completion bug found during this phase's own testing), AD-35 (pause/resume: DownloadService owns visible status independently of where the blocked worker sits), AD-36 (Container/DI wiring deferred, same pattern as AD-31).
FILES_CHANGED:
  - src/twick_hub/domain/enums.py (DownloadStatus: 6→8 states, PENDING renamed to QUEUED)
  - src/twick_hub/domain/downloads.py (default status updated to QUEUED)
  - tests/application/test_downloads.py (assertion updated to QUEUED)
  - src/twick_hub/infrastructure/downloads/__init__.py (new)
  - src/twick_hub/infrastructure/downloads/hls.py (new — media-playlist parser + live poller)
  - src/twick_hub/infrastructure/downloads/retry_policy.py (new)
  - src/twick_hub/infrastructure/downloads/progress_tracker.py (new)
  - src/twick_hub/infrastructure/downloads/segment_manager.py (new)
  - src/twick_hub/infrastructure/downloads/ffmpeg_processor.py (new — real subprocess runner + fake-friendly Protocol)
  - src/twick_hub/infrastructure/downloads/media_processor.py (new)
  - src/twick_hub/infrastructure/downloads/download_executor.py (new — drives one Download through the full pipeline)
  - src/twick_hub/infrastructure/downloads/download_queue.py (new)
  - src/twick_hub/infrastructure/downloads/download_coordinator.py (new — bounded worker pool)
  - src/twick_hub/infrastructure/downloads/download_service.py (new — concrete DownloadEngine + pause/resume)
  - tests/infrastructure/downloads/__init__.py (new)
  - tests/infrastructure/downloads/test_hls.py (new, 9 tests)
  - tests/infrastructure/downloads/test_retry_and_progress.py (new, 11 tests)
  - tests/infrastructure/downloads/test_segment_manager.py (new, 9 tests)
  - tests/infrastructure/downloads/test_ffmpeg_processor.py (new, 10 tests)
  - tests/infrastructure/downloads/test_download_queue.py (new, 3 tests)
  - tests/infrastructure/downloads/test_download_coordinator.py (new, 6 tests)
  - tests/infrastructure/downloads/test_download_service.py (new, 10 tests)
  - tests/infrastructure/downloads/test_download_executor.py (new, 9 tests, full pipeline integration)
  - docs/architecture-decisions.md (added AD-32 through AD-36)
  - docs/risk-register.md (added RISK-ARCH-02, RISK-ARCH-03, RISK-DATA-01, RISK-RESUME-01, RISK-UX-01)
  - docs/phase-state.md (this update)
NEXT_PHASE: FASE 8 — Persistence
NEXT_PHASE_PREREQUISITES: Per Master Plan §61's handoff index, FASE 8 needs "domain/download engine" as input — this phase (FASE 7) satisfies that. FASE 8's own text (§45) explicitly lists "transactions" among its deliverables, which is exactly where RISK-DATA-01 should be addressed. RISK-RESUME-01's "safe shutdown" angle is also FASE 8's own bullet list. No missing prerequisite blocks FASE 8 from starting.
DATE_UTC: 2026-09-17
