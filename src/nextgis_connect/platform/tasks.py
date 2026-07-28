from copy import deepcopy
from typing import Optional, Union

from qgis.core import QgsTask, QgsTaskManager

from nextgis_connect.legacy.settings import NgConnectSettings
from nextgis_connect.platform.logging import logger
from nextgis_connect.platform.qgis.errors import (
    NgConnectError,
)


class NgConnectTask(QgsTask):
    """Run a QGIS task with plugin error capture.

    Store task failures as ``NgConnectError`` instances and prepare
    worker threads for debugging when developer mode is enabled.
    """

    __error: Optional[NgConnectError]

    def __init__(
        self, flags: Union[QgsTask.Flags, QgsTask.Flag, None] = None
    ) -> None:
        """Initialize the task.

        :param flags: QGIS task flags.
        """
        if flags is None:
            flags = QgsTask.Flags()
        super().__init__(flags=flags)
        self.__error = None

    @property
    def error(self) -> Optional[NgConnectError]:
        """Return the captured plugin error.

        :return: Captured error or ``None``.
        """
        return self._error

    @property
    def _error(self) -> Optional[NgConnectError]:
        return self.__error

    @_error.setter
    def _error(self, error: Exception) -> None:
        if isinstance(error, NgConnectError):
            self.__error = deepcopy(error)
        else:
            self.__error = NgConnectError()
            self.__error.__cause__ = deepcopy(error)

    def run(self) -> bool:
        """Run the task preflight logic.

        :return: ``True`` when the task can continue.
        """
        if NgConnectSettings().is_developer_mode:
            try:
                import debugpy  # noqa: T100
            except ImportError:
                logger.warning(
                    "To support threads debugging you need to install debugpy"
                )
            else:
                if debugpy.is_client_connected():
                    debugpy.debug_this_thread()

        if self._error is not None:
            return False

        return True


class NgConnectTaskManager(QgsTaskManager):
    """Provide the plugin task manager type.

    Use the QGIS task manager behavior while giving the plugin a stable
    type for dependency wiring.
    """
