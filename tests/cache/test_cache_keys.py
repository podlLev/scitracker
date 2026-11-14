import datetime as dt

from scitracker.services.cache import make_key


def test_key_has_namespace_prefix() -> None:
    assert make_key("stats:by-topic", user_id=1).startswith("stats:by-topic:")


def test_users_get_different_keys() -> None:
    assert make_key("s", user_id=1, months=12) != make_key("s", user_id=2, months=12)


def test_guest_differs_from_user() -> None:
    assert make_key("s", user_id=None) != make_key("s", user_id=1)


def test_parameter_order_does_not_matter() -> None:
    assert make_key("s", user_id=1, a=1, b=2) == make_key("s", user_id=1, b=2, a=1)


def test_different_parameters_give_different_keys() -> None:
    assert make_key("s", user_id=1, months=6) != make_key("s", user_id=1, months=12)


def test_dates_are_supported() -> None:
    key = make_key("s", user_id=1, since=dt.date(2026, 1, 1))
    assert key == make_key("s", user_id=1, since=dt.date(2026, 1, 1))


def test_key_does_not_expose_parameters() -> None:
    assert "secret-topic" not in make_key("s", user_id=1, topic="secret-topic")
