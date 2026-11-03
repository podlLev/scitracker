import os

_DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://scitracker:scitracker@127.0.0.1:5433/scitracker_test?connect_timeout=5"
)


def get_test_database_url() -> str:
    """Return the URL of the test database (TEST_DATABASE_URL or the local Docker default)."""
    return os.environ.get("TEST_DATABASE_URL", _DEFAULT_TEST_DATABASE_URL)
