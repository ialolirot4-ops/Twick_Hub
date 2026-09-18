from __future__ import annotations

from pathlib import Path

import pytest

from twick_hub.infrastructure.downloads.ffmpeg_processor import (
    AsyncioProcessRunner,
    FFmpegError,
    FFmpegProcessor,
    FFmpegTimeoutError,
    ProcessResult,
)
from twick_hub.infrastructure.downloads.media_processor import MediaProcessor


class FakeProcessRunner:
    def __init__(self, result: ProcessResult) -> None:
        self.result = result
        self.calls: list[list[str]] = []

    async def run(self, argv: list[str], *, timeout_seconds: float | None) -> ProcessResult:
        self.calls.append(argv)
        return self.result


def _segments(tmp_path: Path, n: int) -> list[Path]:
    paths = []
    for i in range(n):
        p = tmp_path / f"{i:06d}.ts"
        p.write_bytes(f"seg{i}".encode())
        paths.append(p)
    return paths


async def test_remux_concat_builds_argv_as_a_list_no_shell(tmp_path: Path):
    runner = FakeProcessRunner(ProcessResult(returncode=0, stderr=""))
    processor = FFmpegProcessor(runner=runner, ffmpeg_path="ffmpeg")
    segments = _segments(tmp_path, 2)
    output = tmp_path / "final.mp4"

    await processor.remux_concat(segments, output)

    assert len(runner.calls) == 1
    argv = runner.calls[0]
    assert argv[0] == "ffmpeg"
    assert "-f" in argv and argv[argv.index("-f") + 1] == "concat"
    assert "-c" in argv and argv[argv.index("-c") + 1] == "copy"
    assert str(output) == argv[-1]
    assert all(isinstance(part, str) for part in argv)  # a real token list, never a shell string


async def test_remux_concat_writes_and_cleans_up_concat_list(tmp_path: Path):
    runner = FakeProcessRunner(ProcessResult(returncode=0, stderr=""))
    processor = FFmpegProcessor(runner=runner)
    segments = _segments(tmp_path, 2)
    output = tmp_path / "final.mp4"

    await processor.remux_concat(segments, output)

    assert not (tmp_path / "final.mp4.concat.txt").exists()


async def test_remux_concat_raises_ffmpeg_error_on_nonzero_exit(tmp_path: Path):
    runner = FakeProcessRunner(ProcessResult(returncode=1, stderr="invalid data"))
    processor = FFmpegProcessor(runner=runner)
    segments = _segments(tmp_path, 1)
    output = tmp_path / "final.mp4"

    with pytest.raises(FFmpegError) as exc_info:
        await processor.remux_concat(segments, output)

    assert exc_info.value.result.returncode == 1
    assert "invalid data" in str(exc_info.value)
    assert not (tmp_path / "final.mp4.concat.txt").exists()  # still cleaned up despite the failure


async def test_remux_concat_removes_partial_output_on_failure(tmp_path: Path):
    output = tmp_path / "final.mp4"
    output.write_bytes(b"partial garbage")
    runner = FakeProcessRunner(ProcessResult(returncode=1, stderr="corrupt"))
    processor = FFmpegProcessor(runner=runner)

    with pytest.raises(FFmpegError):
        await processor.remux_concat(_segments(tmp_path, 1), output)

    assert not output.exists()


async def test_media_processor_delegates_to_ffmpeg(tmp_path: Path):
    runner = FakeProcessRunner(ProcessResult(returncode=0, stderr=""))
    media = MediaProcessor(ffmpeg=FFmpegProcessor(runner=runner))
    segments = _segments(tmp_path, 1)

    await media.finalize(segments, tmp_path / "out.mp4")

    assert len(runner.calls) == 1


# --- AsyncioProcessRunner: real subprocess, no shell=True -----------------


async def test_asyncio_process_runner_success_exit_code():
    result = await AsyncioProcessRunner().run(["/usr/bin/true"], timeout_seconds=5.0)
    assert result.returncode == 0


async def test_asyncio_process_runner_nonzero_exit_code():
    result = await AsyncioProcessRunner().run(["/usr/bin/false"], timeout_seconds=5.0)
    assert result.returncode == 1


async def test_asyncio_process_runner_captures_stderr():
    argv = ["/usr/bin/env", "python3", "-c", "import sys; sys.stderr.write('boom')"]
    result = await AsyncioProcessRunner().run(argv, timeout_seconds=5.0)
    assert "boom" in result.stderr


async def test_asyncio_process_runner_kills_on_timeout():
    with pytest.raises(FFmpegTimeoutError):
        await AsyncioProcessRunner().run(["/usr/bin/sleep", "5"], timeout_seconds=0.05)


async def test_asyncio_process_runner_never_uses_a_shell_string():
    """A real shell would happily execute 'echo pwned > /tmp/x; true' as
    one string. Passed as argv to a real binary that isn't a shell, this
    must fail with a non-zero exit (the whole string is one bogus
    filename argument) — proof create_subprocess_exec, not shell, is
    what's actually running."""
    result = await AsyncioProcessRunner().run(
        ["/usr/bin/false", "; touch /tmp/should-not-exist ;"], timeout_seconds=5.0
    )
    assert result.returncode != 0
    assert not Path("/tmp/should-not-exist").exists()
