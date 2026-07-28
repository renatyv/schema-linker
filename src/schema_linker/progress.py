from __future__ import annotations

import shutil
import sys
from typing import TextIO


class ProgressBar:
    def __init__(self, label: str, total: int, stream: TextIO | None = None) -> None:
        self.label = label
        self.total = total
        self.stream = stream or sys.stderr
        self.current = 0
        self.item = ""
        self.enabled = total > 0 and self.stream.isatty()
        self._last_width = 0

    def start(self, item: str = "") -> None:
        self.current = 0
        self.item = item
        self.render()

    def update(self, current: int, item: str = "") -> None:
        self.current = min(max(current, 0), self.total)
        self.item = item
        self.render()

    def advance(self, item: str = "") -> None:
        self.update(self.current + 1, item)

    def finish(self, message: str | None = None) -> None:
        if not self.enabled:
            return
        if message:
            self._write_line(message)
            self.stream.write("\n")
            self.stream.flush()
            self._last_width = 0
        else:
            self._clear_line()

    def render(self) -> None:
        if not self.enabled:
            return
        columns = shutil.get_terminal_size(fallback=(80, 24)).columns
        bar_width = 24
        completed = round(bar_width * self.current / self.total)
        bar = "#" * completed + "-" * (bar_width - completed)
        line = f"{self.label} [{bar}] {self.current}/{self.total}"
        if self.item:
            line += f" {self.item}"
        if len(line) >= columns:
            line = line[: max(columns - 1, 0)]
        self._write_line(line)

    def _write_line(self, line: str) -> None:
        padding = " " * max(self._last_width - len(line), 0)
        self.stream.write(f"\r{line}{padding}")
        self.stream.flush()
        self._last_width = len(line)

    def _clear_line(self) -> None:
        self.stream.write("\r" + " " * self._last_width + "\r")
        self.stream.flush()
        self._last_width = 0
