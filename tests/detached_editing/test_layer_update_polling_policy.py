from datetime import datetime, timedelta, timezone

from nextgis_connect.legacy.detached_editing.container.layer_update_polling_policy import (
    LayerUpdatePollingPolicy,
)


def test_next_interval_uses_minimum_for_unknown_change_date() -> None:
    policy = LayerUpdatePollingPolicy()

    interval = policy.next_interval(last_change_date=None)

    assert interval == timedelta(seconds=30)


def test_next_interval_grows_from_last_change_age() -> None:
    policy = LayerUpdatePollingPolicy()
    current_date = datetime(2026, 7, 28, 12, 0, 0)
    last_change_date = current_date - timedelta(hours=1)

    interval = policy.next_interval(
        last_change_date=last_change_date,
        current_date=current_date,
    )

    assert interval == timedelta(minutes=6)


def test_next_interval_is_limited_by_maximum() -> None:
    policy = LayerUpdatePollingPolicy()
    current_date = datetime(2026, 7, 28, 12, 0, 0)
    last_change_date = current_date - timedelta(days=3)

    interval = policy.next_interval(
        last_change_date=last_change_date,
        current_date=current_date,
    )

    assert interval == timedelta(minutes=90)


def test_should_poll_uses_delay_from_last_check_date() -> None:
    policy = LayerUpdatePollingPolicy()
    last_check_date = datetime(2026, 7, 28, 12, 0, 0)
    last_change_date = last_check_date - timedelta(hours=1)

    should_poll = policy.should_poll(
        last_check_date=last_check_date,
        last_change_date=last_change_date,
        current_date=last_check_date + timedelta(minutes=5, seconds=59),
    )

    assert should_poll is False

    should_poll = policy.should_poll(
        last_check_date=last_check_date,
        last_change_date=last_change_date,
        current_date=last_check_date + timedelta(minutes=6),
    )

    assert should_poll is True


def test_should_poll_accepts_mixed_timezone_dates() -> None:
    policy = LayerUpdatePollingPolicy()
    last_check_date = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)
    last_change_date = datetime(2026, 7, 25, 12, 0, 0)

    should_poll = policy.should_poll(
        last_check_date=last_check_date,
        last_change_date=last_change_date,
        current_date=last_check_date + timedelta(minutes=90),
    )

    assert should_poll is True


def test_network_error_interval_uses_exponential_backoff() -> None:
    policy = LayerUpdatePollingPolicy()

    intervals = [
        policy.network_error_interval(consecutive_error_count=i)
        for i in range(1, 7)
    ]

    assert intervals == [
        timedelta(seconds=30),
        timedelta(minutes=1),
        timedelta(minutes=2),
        timedelta(minutes=4),
        timedelta(minutes=8),
        timedelta(minutes=15),
    ]


def test_network_error_interval_is_limited_by_maximum() -> None:
    policy = LayerUpdatePollingPolicy()

    interval = policy.network_error_interval(consecutive_error_count=10)

    assert interval == timedelta(minutes=15)


def test_should_retry_after_network_error_uses_backoff_interval() -> None:
    policy = LayerUpdatePollingPolicy()
    last_attempt_date = datetime(2026, 7, 28, 12, 0, 0)

    should_retry = policy.should_retry_after_network_error(
        last_attempt_date=last_attempt_date,
        consecutive_error_count=3,
        current_date=last_attempt_date + timedelta(minutes=1, seconds=59),
    )

    assert should_retry is False

    should_retry = policy.should_retry_after_network_error(
        last_attempt_date=last_attempt_date,
        consecutive_error_count=3,
        current_date=last_attempt_date + timedelta(minutes=2),
    )

    assert should_retry is True
