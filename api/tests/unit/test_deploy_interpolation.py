"""Seam: the deploy files' ${VAR:-default} interpolation.

Compose/Swarm end a ${...} at the FIRST "}", so a default containing a brace
(e.g. a JSON object) leaks its tail onto the value: with the var set in
Portainer, ORIFLUX_SPT_CHAT_EXTRA became '{…false}}}}' and every AI call
failed on json.loads (prod, 2026-09-23). Defaults must stay brace-free.
"""

import re
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[3] / "deploy"
FILES = ["docker-stack.yml", "docker-compose.yml", "self-host/docker-compose.yml"]


@pytest.mark.parametrize("name", FILES)
def test_no_interpolation_default_contains_a_brace(name: str) -> None:
    path = DEPLOY / name
    if not path.exists():
        pytest.skip(f"{name} absent")
    offenders = [
        f"{name}:{n}: {line.strip()}"
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if not line.lstrip().startswith("#")
        and re.search(r"\$\{[A-Z0-9_]+:?-[^}]*\{", line)
    ]
    assert offenders == [], "brace inside an interpolation default:\n" + "\n".join(offenders)
