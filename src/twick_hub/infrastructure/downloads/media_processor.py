"""Master Plan §18's ``MediaProcessor └── FFmpegProcessor`` tree.
``MediaProcessor`` is the extension point ``DownloadExecutor`` actually
depends on — a future processing step (audio-only extraction, cropping —
docs/functional-baseline.md's legacy-compat requirements) is added here
without ``DownloadExecutor`` needing to know ffmpeg exists at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from twick_hub.infrastructure.downloads.ffmpeg_processor import FFmpegProcessor


@dataclass
class MediaProcessor:
    ffmpeg: FFmpegProcessor

    async def finalize(self, segment_paths: list[Path], output_path: Path) -> None:
        """Turns downloaded segments into the final deliverable file."""
        await self.ffmpeg.remux_concat(segment_paths, output_path)
