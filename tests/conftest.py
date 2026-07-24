"""Shared test fixtures.

`_reset_cli_overrides` clears the process-global --notebook/--actor pins
(set by the `flip` group callback) around every test, so a CLI test that
passes --actor/--notebook can never leak its override into a later
library-level test that expects plain env/CWD behavior.
"""

from __future__ import annotations

import pytest

from flip import util


@pytest.fixture(autouse=True)
def _reset_cli_overrides():
    util.set_cli_overrides(None, None)
    yield
    util.set_cli_overrides(None, None)
