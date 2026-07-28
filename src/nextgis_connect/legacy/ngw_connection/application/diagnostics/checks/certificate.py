from dataclasses import replace
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from qgis.core import QgsApplication, QgsFeedback
from qgis.PyQt.QtNetwork import QSslSocket

from nextgis_connect.legacy.ngw_connection.domain.diagnostics import (
    ConnectionCheckId,
    ConnectionCheckResult,
    ConnectionDiagnosticContext,
)
from nextgis_connect.ngw.qgis.qgis_ngw_connection import QgsNgwConnection
from nextgis_connect.platform.logging import logger
from nextgis_connect.platform.qgis.errors import NgConnectError, NgwError

from .base import BaseConnectionCheck, UpdateReporter

if TYPE_CHECKING:
    from nextgis_connect.ngw.qgis.qgis_ngw_connection import (
        QgsNgwConnection,
    )


class CertificateCheck(BaseConnectionCheck):
    check_id = ConnectionCheckId.CERTIFICATE
    is_blocking = True

    @property
    def title(self) -> str:
        return self.tr("Certificate")

    @property
    def initial_description(self) -> str:
        return self.tr("Checking the server certificate.")

    def run_check(
        self,
        context: ConnectionDiagnosticContext,
        ngw_connection: "QgsNgwConnection",
        feedback: QgsFeedback,
        report_update: UpdateReporter,
    ) -> ConnectionCheckResult:
        host_port = self._host_port()
        certificate_connection = QgsNgwConnection(
            replace(self._connection, auth_config_id=None)
        )
        try:
            certificate_connection.get(self._connection.url, feedback=feedback)
        except NgwError as error:
            self._raise_if_canceled(feedback, error)
            if self._is_ssl_error(error):
                return self._failure(
                    self.tr(
                        "The Web GIS certificate was not accepted by QGIS."
                    ),
                    issue=self._server_issue(
                        self.tr(
                            "The SSL/TLS certificate validation failed before the Web GIS could be reached."
                        ),
                        self.tr(
                            "Check the server certificate chain and accept or trust the certificate in QGIS if it is expected."
                        ),
                        technical_details=error.detail,
                    ),
                )

            if self._is_network_error(error):
                return self._failure(
                    self.tr("Unable to verify the server certificate."),
                    issue=self._network_issue(
                        error,
                        self.tr(
                            "Check the network path to the Web GIS and retry the checks."
                        ),
                    ),
                )

            return self._failure(
                self.tr("The certificate check could not reach the Web GIS."),
                issue=self._server_issue(
                    self.tr(
                        "The Web GIS did not respond while the certificate check was running."
                    ),
                    self.tr(
                        "Check the Web GIS availability and retry the checks."
                    ),
                    technical_details=error.detail,
                ),
            )
        except NgConnectError as error:
            self._raise_if_canceled(feedback, error)
            return self._failure(
                self.tr("Unable to verify the server certificate."),
                issue=self._network_issue(
                    error,
                    self.tr(
                        "Check the network path to the Web GIS and retry the checks."
                    ),
                ),
            )

        ssl_config = QgsApplication.authManager().sslCertCustomConfigByHost(
            host_port
        )
        ignored_errors = ssl_config.sslIgnoredErrorEnums()
        peer_verify_mode = ssl_config.sslPeerVerifyMode()

        logger_message = self.tr(
            "SSL configuration for {host}: config_exists={exists}, ignored_errors={ignored_errors}, peer_verify_mode={peer_verify_mode}"
        ).format(
            host=host_port,
            exists=not ssl_config.isNull(),
            ignored_errors=len(ignored_errors),
            peer_verify_mode=self._peer_verify_mode_label(peer_verify_mode),
        )
        logger.debug(logger_message)

        if not ssl_config.isNull() and (
            len(ignored_errors) > 0
            or peer_verify_mode != QSslSocket.PeerVerifyMode.VerifyPeer
        ):
            return self._warning(
                self.tr(
                    "The Web GIS certificate is accepted by QGIS with custom SSL exceptions."
                ),
                issue=self._client_issue(
                    self.tr(
                        "The Web GIS is reachable, but QGIS stores SSL exceptions for this host."
                    ),
                    self.tr(
                        "Review the accepted certificate and ignored SSL errors in the QGIS network settings."
                    ),
                ),
            )

        return self._success(
            self.tr(
                "The Web GIS certificate was accepted without custom SSL exceptions."
            )
        )

    def _host_port(self) -> str:
        parsed_url = urlparse(self._connection.url)
        host = parsed_url.hostname or ""
        port = parsed_url.port
        if port is not None:
            return f"{host}:{port}"

        if parsed_url.scheme == "https":
            return f"{host}:443"

        return f"{host}:80"

    def _peer_verify_mode_label(self, peer_verify_mode) -> str:
        name = getattr(peer_verify_mode, "name", None)
        value = getattr(peer_verify_mode, "value", None)
        if name is not None and value is not None:
            return f"{name} ({value})"

        return str(peer_verify_mode)
