from __future__ import annotations

import pytest

from emap.store import Store, open_store


@pytest.fixture
def store() -> Store:
    s = open_store(":memory:")
    yield s
    s.close()
