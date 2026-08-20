from __future__ import annotations

import sys
from typing import TextIO

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
)


class ProgressBar:
    """Progress bar for one linking phase, rendered by rich.progress."""

    def __init__(self, label: str, total: int, stream: TextIO | None = None) -> None:
        self.label = label
        self.total = total
        self._console = Console(file=stream or sys.stderr)
        self.enabled = total > 0 and self._console.is_terminal
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("{task.fields[item]}"),
            console=self._console,
            transient=True,
        )
        self._task: TaskID | None = None

    def start(self, item: str = "") -> None:
        if not self.enabled:
            return
        self._task = self._progress.add_task(self.label, total=self.total, item=item)
        self._progress.start()

    def update(self, current: int, item: str = "") -> None:
        if self._task is None:
            return
        self._progress.update(self._task, completed=current, item=item)

    def advance(self, item: str = "") -> None:
        if self._task is None:
            return
        self._progress.advance(self._task, item=item)

    def finish(self, message: str | None = None) -> None:
        if not self.enabled:
            return
        self._progress.stop()
        if message:
            self._console.print(message)
