from datetime import datetime, timedelta
from typing import ClassVar, Optional


class LayerUpdatePollingPolicy:
    """Compute polling intervals for detached layer updates."""

    _MIN_INTERVAL: ClassVar[timedelta] = timedelta(seconds=30)
    _MAX_INTERVAL: ClassVar[timedelta] = timedelta(minutes=90)
    _AGE_INTERVAL_RATIO: ClassVar[float] = 0.1

    _NETWORK_ERROR_BASE_INTERVAL: ClassVar[timedelta] = timedelta(seconds=30)
    _NETWORK_ERROR_MAX_INTERVAL: ClassVar[timedelta] = timedelta(minutes=15)

    def next_interval(
        self,
        *,
        last_change_date: Optional[datetime],
        current_date: Optional[datetime] = None,
    ) -> timedelta:
        """Return the next polling interval."""
        if current_date is None:
            current_date = datetime.now()

        if last_change_date is None:
            return self._MIN_INTERVAL

        age_seconds = self._elapsed_seconds(
            start_date=last_change_date,
            end_date=current_date,
        )
        interval = timedelta(seconds=age_seconds * self._AGE_INTERVAL_RATIO)

        return self._clamped_interval(interval)

    def should_poll(
        self,
        *,
        last_check_date: Optional[datetime],
        last_change_date: Optional[datetime],
        current_date: Optional[datetime] = None,
    ) -> bool:
        """Return True when a detached layer should be polled now."""
        if last_check_date is None:
            return True

        if current_date is None:
            current_date = datetime.now()

        interval = self.next_interval(
            last_change_date=last_change_date,
            current_date=last_check_date,
        )
        elapsed_seconds = self._elapsed_seconds(
            start_date=last_check_date,
            end_date=current_date,
        )

        return elapsed_seconds >= interval.total_seconds()

    def network_error_interval(
        self,
        *,
        consecutive_error_count: int,
    ) -> timedelta:
        """Return retry interval after consecutive network errors."""
        retry_index = max(consecutive_error_count - 1, 0)
        interval = self._NETWORK_ERROR_BASE_INTERVAL * (2**retry_index)

        if interval > self._NETWORK_ERROR_MAX_INTERVAL:
            return self._NETWORK_ERROR_MAX_INTERVAL

        return interval

    def should_retry_after_network_error(
        self,
        *,
        last_attempt_date: Optional[datetime],
        consecutive_error_count: int,
        current_date: Optional[datetime] = None,
    ) -> bool:
        """Return True when a network retry should be attempted now."""
        if last_attempt_date is None:
            return True

        if current_date is None:
            current_date = datetime.now()

        interval = self.network_error_interval(
            consecutive_error_count=consecutive_error_count,
        )
        elapsed_seconds = self._elapsed_seconds(
            start_date=last_attempt_date,
            end_date=current_date,
        )

        return elapsed_seconds >= interval.total_seconds()

    def _clamped_interval(self, interval: timedelta) -> timedelta:
        if interval < self._MIN_INTERVAL:
            return self._MIN_INTERVAL

        if interval > self._MAX_INTERVAL:
            return self._MAX_INTERVAL

        return interval

    def _elapsed_seconds(
        self,
        *,
        start_date: datetime,
        end_date: datetime,
    ) -> float:
        elapsed_seconds = end_date.timestamp() - start_date.timestamp()
        return max(elapsed_seconds, 0.0)
