"""Wraps ffmpeg as a subprocess to remux downloaded segments into one
final file. Master Plan §18: "Conservar el buen diseño del original" —
separate process, arguments as a list, never ``shell=True``, timeout,
cancellation, stderr capture, exit codes, cleanup. All preserved here.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ProcessResult:
    returncode: int
    stderr: str


@runtime_checkable
class ProcessRunner(Protocol):
    async def run(self, argv: list[str], *, timeout_seconds: float | None) -> ProcessResult: ...


class FFmpegError(Exception):
    """ffmpeg ran and exited non-zero."""

    def __init__(self, argv: list[str], result: ProcessResult) -> None:
        super().__init__(f"ffmpeg exited {result.returncode}: {result.stderr[:500]}")
        self.argv = argv
        self.result = result


class FFmpegTimeoutError(Exception):
    """ffmpeg didn't finish within ``timeout_seconds`` and was killed."""

    def __init__(self, argv: list[str], timeout_seconds: float | None) -> None:
        super().__init__(f"ffmpeg timed out after {timeout_seconds}s")
        self.argv = argv
        self.timeout_seconds = timeout_seconds


class AsyncioProcessRunner:
    """Real ``ProcessRunner`` — ``asyncio.create_subprocess_exec`` with the
    argv list passed straight through (never a shell string), a timeout
    that kills the process on expiry, and stderr captured for
    ``FFmpegError``."""

    async def run(self, argv: list[str], *, timeout_seconds: float | None = None) -> ProcessResult:
        process = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        try:
            _stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise FFmpegTimeoutError(argv, timeout_seconds) from None
        return ProcessResult(
            returncode=process.returncode or 0, stderr=stderr.decode("utf-8", errors="replace")
        )


@dataclass
class FFmpegProcessor:
    runner: ProcessRunner
    ffmpeg_path: str = "ffmpeg"
    timeout_seconds: float | None = 300.0

    async def remux_concat(self, segment_paths: list[Path], output_path: Path) -> None:
        """Concatenates already-downloaded segments into one file via
        ffmpeg's concat demuxer with ``-c copy`` — no re-encoding, same
        approach as the legacy app. Cleans up its temp concat-list file
        regardless of outcome; does NOT delete the segments themselves —
        that's ``DownloadExecutor``'s call, since it owns the working
        directory and needs them to still be there if a later phase adds
        resume-after-crash for the processing step, not just the
        download step."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        concat_list_path = output_path.with_name(output_path.name + ".concat.txt")
        concat_list_path.write_text(
            "\n".join(f"file '{path.resolve()}'" for path in segment_paths), encoding="utf-8"
        )
        argv = [
            self.ffmpeg_path,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list_path),
            "-c",
            "copy",
            str(output_path),
        ]
        try:
            result = await self.runner.run(argv, timeout_seconds=self.timeout_seconds)
        finally:
            concat_list_path.unlink(missing_ok=True)

        if result.returncode != 0:
            output_path.unlink(missing_ok=True)
            raise FFmpegError(argv, result)
