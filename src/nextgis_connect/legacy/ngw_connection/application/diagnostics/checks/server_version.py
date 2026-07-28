from typing import TYPE_CHECKING

from qgis.core import QgsFeedback

from nextgis_connect.legacy.ngw.qgis.qgis_ngw_connection import GET_VERSION_URL
from nextgis_connect.legacy.ngw_connection.domain.diagnostics import (
    ConnectionCheckId,
    ConnectionCheckResult,
    ConnectionDiagnosticContext,
    ServerVersionInfo,
)
from nextgis_connect.platform.qgis.errors import NgConnectError, NgwError
from nextgis_connect.platform.qgis.utils import (
    SupportStatus,
    is_version_supported,
)

from .base import BaseConnectionCheck, UpdateReporter

if TYPE_CHECKING:
    from nextgis_connect.legacy.ngw.qgis.qgis_ngw_connection import (
        QgsNgwConnection,
    )


class ServerVersionCheck(BaseConnectionCheck):
    check_id = ConnectionCheckId.SERVER_VERSION

    @property
    def title(self) -> str:
        return self.tr("Server version")

    @property
    def initial_description(self) -> str:
        return self.tr("Reading the server version.")

    def run_check(
        self,
        context: ConnectionDiagnosticContext,
        ngw_connection: "QgsNgwConnection",
        feedback: QgsFeedback,
        report_update: UpdateReporter,
    ) -> ConnectionCheckResult:
        resolution = self.tr(
            "Check the server availability or ask the administrator to inspect the server logs."
        )
        try:
            response = ngw_connection.get(GET_VERSION_URL, feedback=feedback)
        except NgwError as error:
            self._raise_if_canceled(feedback, error)
            if self._is_network_error(error):
                return self._failure(
                    self.tr("Unable to read the server version."),
                    issue=self._network_issue(error, resolution),
                )

            return self._failure(
                self.tr("The server version endpoint returned an error."),
                issue=self._server_issue(
                    self.tr(
                        "The server did not return a valid version response."
                    ),
                    resolution,
                    technical_details=error.detail,
                ),
            )
        except NgConnectError as error:
            self._raise_if_canceled(feedback, error)
            return self._failure(
                self.tr("Unable to read the server version."),
                issue=self._network_issue(error, resolution),
            )

        response_json = self._response_to_json(response, resolution)
        if isinstance(response_json, ConnectionCheckResult):
            return response_json

        if not isinstance(response_json, dict):
            return self._failure(
                self.tr(
                    "The server version response has an unexpected format."
                ),
                issue=self._server_issue(
                    self.tr("The server version payload is not an object."),
                    resolution,
                ),
            )

        version = response_json.get("nextgisweb")
        if not isinstance(version, str):
            return self._failure(
                self.tr("The server version field is missing."),
                issue=self._server_issue(
                    self.tr(
                        "The response does not contain the nextgisweb version."
                    ),
                    resolution,
                ),
            )

        support_status = is_version_supported(version)
        payload = ServerVersionInfo(version, support_status)
        if support_status == SupportStatus.SUPPORTED:
            return self._success(
                self.tr("Server version {version} is supported.").format(
                    version=version
                ),
                payload=payload,
            )

        if support_status == SupportStatus.OLD_NGW:
            return self._failure(
                self.tr(
                    "Server version {version} is older than the supported range."
                ).format(version=version),
                issue=self._server_issue(
                    self.tr("The connected server is outdated."),
                    self.tr(
                        "Ask the administrator to update NextGIS Web to a supported version."
                    ),
                ),
                payload=payload,
            )

        return self._failure(
            self.tr(
                "Server version {version} is newer than supported by this plugin."
            ).format(version=version),
            issue=self._client_issue(
                self.tr(
                    "This plugin version does not support the connected server."
                ),
                self.tr(
                    "Update NextGIS Connect to a newer version and rerun the diagnostics."
                ),
            ),
            payload=payload,
        )
