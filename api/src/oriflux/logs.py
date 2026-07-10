"""Application logging setup (issue #15).

Under uvicorn only the uvicorn.* loggers get handlers, so INFO records
from oriflux.* loggers vanish — a monthly job whose success is silent is
unobservable in prod. Each entrypoint's create_app() calls setup_logging();
it is idempotent so repeated app factories (tests) never duplicate lines.
"""

import logging
import sys
from typing import Any

_FORMAT = "%(levelname)s:     %(name)s - %(message)s"


class _StderrHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Resolves sys.stderr at emit time (survives stream replacement)."""

    @property
    def stream(self) -> Any:
        return sys.stderr

    @stream.setter
    def stream(self, value: Any) -> None:  # StreamHandler.__init__ assigns it
        pass


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if not any(isinstance(h, _StderrHandler) for h in root.handlers):
        handler = _StderrHandler()
        handler.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(handler)
    if root.level > level or root.level == logging.NOTSET:
        root.setLevel(level)
