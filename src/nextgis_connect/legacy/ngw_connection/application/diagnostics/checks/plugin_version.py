import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

from qgis.core import Qgis, QgsFeedback

from nextgis_connect.legacy.ngw_connection.application.diagnostics.parsers import (
    PluginVersionProvider,
    QgisPluginRepositoryParser,
)
from nextgis_connect.legacy.ngw_connection.domain.diagnostics import (
    ConnectionCheckId,
    ConnectionCheckResult,
    ConnectionDiagnosticContext,
    PluginVersionInfo,
)
from nextgis_connect.platform.qgis.compat import parse_version
from nextgis_connect.platform.qgis.errors import NgConnectError, NgwError

from .base import BaseConnectionCheck, UpdateReporter

if TYPE_CHECKING:
    from nextgis_connect.legacy.ngw.qgis.qgis_ngw_connection import (
        QgsNgwConnection,
    )

PLUGIN_REPOSITORY_URL = "https://plugins.qgis.org/plugins/plugins.xml"


class PluginVersionCheck(BaseConnectionCheck):
    check_id = ConnectionCheckId.PLUGIN_VERSION

    @property
    def title(self) -> str:
        return self.tr("Plugin version")

    @property
    def initial_description(self) -> str:
        return self.tr(
            "Fetching the latest plugin version from the QGIS plugin repository."
        )

    def run_check(
        self,
        context: ConnectionDiagnosticContext,
        ngw_connection: "QgsNgwConnection",
        feedback: QgsFeedback,
        report_update: UpdateReporter,
    ) -> ConnectionCheckResult:
        qgis_version = Qgis.versionInt()
        qgis_major = qgis_version // 10000
        qgis_minor = (qgis_version % 10000) // 100
        repository_url = (
            f"{PLUGIN_REPOSITORY_URL}?qgis={qgis_major}.{qgis_minor}"
        )
        try:
            response = ngw_connection.get(
                repository_url,
                feedback=feedback,
            )
        except NgwError as error:
            self._raise_if_canceled(feedback, error)
            return self._warning(
                self.tr("Unable to check the latest plugin version."),
                issue=self._network_issue(
                    error,
                    self.tr(
                        "Check the internet connection and try the diagnostics again."
                    ),
                ),
            )
        except NgConnectError as error:
            self._raise_if_canceled(feedback, error)
            return self._warning(
                self.tr("Unable to check the latest plugin version."),
                issue=self._network_issue(
                    error,
                    self.tr(
                        "Check the internet connection and try the diagnostics again."
                    ),
                ),
            )

        try:
            latest_version = QgisPluginRepositoryParser.latest_version(
                self._as_bytes(response)
            )
        except (ET.ParseError, ValueError) as error:
            return self._warning(
                self.tr("The plugin repository returned invalid XML."),
                issue=self._server_issue(
                    self.tr(
                        "The plugin repository response cannot be parsed."
                    ),
                    self.tr(
                        "Try the diagnostics later or check the repository availability."
                    ),
                    technical_details=str(error),
                ),
            )

        if latest_version is None:
            return self._warning(
                self.tr("The plugin repository does not contain this plugin."),
                issue=self._server_issue(
                    self.tr(
                        "The NextGIS Connect entry is missing in the repository response."
                    ),
                    self.tr(
                        "Try the diagnostics later or check the plugin repository configuration."
                    ),
                ),
            )

        installed_version = PluginVersionProvider.current_version()
        payload = PluginVersionInfo(installed_version, latest_version)
        parsed_installed_version = parse_version(installed_version)
        parsed_latest_version = parse_version(latest_version)
        if parsed_installed_version < parsed_latest_version:
            if self._is_patch_difference_only(
                parsed_installed_version,
                parsed_latest_version,
            ):
                return self._warning(
                    self.tr(
                        "Installed plugin version {installed} is outdated. Latest version is {available}."
                    ).format(
                        installed=installed_version,
                        available=latest_version,
                    ),
                    issue=self._client_issue(
                        self.tr("The installed plugin version is outdated."),
                        self.tr(
                            "Update the plugin when convenient and continue diagnostics."
                        ),
                    ),
                    payload=payload,
                )

            return self._failure(
                self.tr(
                    "Installed version {installed} is older than repository version {available}."
                ).format(
                    installed=installed_version,
                    available=latest_version,
                ),
                issue=self._client_issue(
                    self.tr("The installed plugin version is outdated."),
                    self.tr(
                        "Update the plugin from the QGIS Plugin Repository and rerun the diagnostics."
                    ),
                ),
                payload=payload,
            )

        return self._success(
            self.tr("Installed version {installed} is up to date.").format(
                installed=installed_version
            ),
            payload=payload,
        )

    def _is_patch_difference_only(
        self, installed_version, latest_version
    ) -> bool:
        installed_release = getattr(installed_version, "release", tuple())
        latest_release = getattr(latest_version, "release", tuple())
        if len(installed_release) < 3 or len(latest_release) < 3:
            return False

        return (
            installed_release[:2] == latest_release[:2]
            and installed_release[2] != latest_release[2]
            and not getattr(installed_version, "is_prerelease", False)
            and not getattr(latest_version, "is_prerelease", False)
        )
