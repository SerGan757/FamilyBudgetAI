import os
from unittest.mock import AsyncMock

import pytest

from app.utils import temporary_screens


@pytest.fixture(autouse=True)
def isolate_persistent_temporary_message_queue(monkeypatch):
    """Keep ordinary unit tests DB-free; opt-in suites test PostgreSQL directly."""
    if os.getenv("RUN_POSTGRES_DOCUMENTS_INTEGRATION") == "1":
        yield
        return
    monkeypatch.setattr(
        temporary_screens,
        "schedule_temporary_message_delete",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        temporary_screens,
        "cancel_temporary_message_delete",
        AsyncMock(),
    )
    yield
