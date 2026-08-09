"""Shared test fixtures.

`_reset_cli_overrides` clears the process-global --notebook/--actor pins
(set by the `flip` group callback) around every test, so a CLI test that
passes --actor/--notebook can never leak its override into a later
library-level test that expects plain env/CWD behavior.

`_isolate_flip_home` points `$FLIP_HOME` at an empty tmp directory for every
test that doesn't set its own. Most already did; the ones that didn't were
reading the developer's real `~/.flip`, which was harmless only for as long as
nothing in flip consulted the config outside an explicit resolve. `flip doctor`
now does — `missing-derivative` fires only where an `[extractors]` lane exists
— so a suite whose result depends on the machine it runs on is no longer a
theoretical problem.
"""

from __future__ import annotations

import pytest

from flip import util


@pytest.fixture(autouse=True)
def _reset_cli_overrides():
    util.set_cli_overrides(None, None)
    yield
    util.set_cli_overrides(None, None)


@pytest.fixture(autouse=True)
def _isolate_flip_home(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("FLIP_HOME", str(tmp_path_factory.mktemp("fliphome-empty")))
