from typing import TYPE_CHECKING

from qgis.core import QgsFeedback

from nextgis_connect.ngw_connection.domain.diagnostics import (
    ConnectionCheckId,
    ConnectionCheckResult,
    ConnectionDiagnosticContext,
)
from nextgis_connect.platform.qgis.errors import NgConnectError, NgwError

from .base import BaseConnectionCheck, UpdateReporter

if TYPE_CHECKING:
    from nextgis_connect.ngw.qgis.qgis_ngw_connection import (
        QgsNgwConnection,
    )

PYRAMID_SETTINGS_SUB_URL = "/api/component/pyramid/settings?component=pyramid"


class DownloadCheck(BaseConnectionCheck):
    check_id = ConnectionCheckId.DOWNLOAD

    @property
    def title(self) -> str:
        return self.tr("Download")

    @property
    def initial_description(self) -> str:
        return self.tr("Reading the server download settings.")

    def run_check(
        self,
        context: ConnectionDiagnosticContext,
        ngw_connection: "QgsNgwConnection",
        feedback: QgsFeedback,
        report_update: UpdateReporter,
    ) -> ConnectionCheckResult:
        resolution = self.tr(
            "Ask the administrator to inspect the server download settings response."
        )
        try:
            response = ngw_connection.get(
                PYRAMID_SETTINGS_SUB_URL,
                feedback=feedback,
            )
        except NgwError as error:
            self._raise_if_canceled(feedback, error)
            if self._is_network_error(error):
                return self._failure(
                    self.tr("Unable to read the server download settings."),
                    issue=self._network_issue(
                        error,
                        self.tr(
                            "Check the network settings and retry the checks."
                        ),
                    ),
                )

            return self._failure(
                self.tr(
                    "The server download settings endpoint returned an error."
                ),
                issue=self._server_issue(
                    self.tr(
                        "The server did not return the expected download settings."
                    ),
                    resolution,
                    technical_details=error.detail,
                ),
            )
        except NgConnectError as error:
            self._raise_if_canceled(feedback, error)
            return self._failure(
                self.tr("Unable to read the server download settings."),
                issue=self._network_issue(
                    error,
                    self.tr(
                        "Check the network settings and retry the checks."
                    ),
                ),
            )

        response_json = self._response_to_json(response, resolution)
        if isinstance(response_json, ConnectionCheckResult):
            return response_json

        if not isinstance(response_json, dict):
            return self._failure(
                self.tr(
                    "The server download settings response has an unexpected format."
                ),
                issue=self._server_issue(
                    self.tr(
                        "The server download settings payload is not an object."
                    ),
                    resolution,
                ),
            )

        enabled_value = response_json.get("lunkwill.enabled")
        if enabled_value is None:
            lunkwill_section = response_json.get("lunkwill")
            if isinstance(lunkwill_section, dict):
                enabled_value = lunkwill_section.get("enabled")

        if enabled_value is True:
            return self._success(
                self.tr("Server-side download support is enabled."),
            )

        return self._warning(
            self.tr("Server-side download support is disabled or missing."),
            issue=self._server_issue(
                self.tr(
                    "Long-running downloads may work slower without server-side download support."
                ),
                self.tr(
                    "Ask the administrator to enable server-side download support if long-running downloads are expected."
                ),
            ),
        )
