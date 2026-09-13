import os
import uuid
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://x:x@localhost/x")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "sEVSClEYCZEks0yU3h9XcBCIdC9_ngUi0KZ5Na0HRpU=")


@pytest.fixture
def mock_db():
    """A MagicMock standing in for a SQLAlchemy Session. add/commit/refresh/
    flush are no-ops; tests assert on client-call behavior, not persistence,
    since there's no live Postgres in this environment."""
    db = MagicMock()
    return db


@pytest.fixture
def new_uuid():
    return uuid.uuid4
