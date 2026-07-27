import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING

from qgis.core import QgsFeedback

from nextgis_connect.ngw_connection.domain.diagnostics import (
    ConnectionCheckId,
    ConnectionCheckResult,
    ConnectionCheckState,
    ConnectionDiagnosticContext,
    ConnectionIssue,
    ConnectionIssueSource,
    UploadDiagnosticInfo,
)
from nextgis_connect.platform.qgis.errors import NgConnectError, NgwError

from .base import BaseConnectionCheck, UpdateReporter

if TYPE_CHECKING:
    from nextgis_connect.ngw.qgis.qgis_ngw_connection import (
        QgsNgwConnection,
    )

MIN_UPLOAD_SPEED_MBIT_PER_SECOND = 2.0
DIAGNOSTIC_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024


class UploadCheck(BaseConnectionCheck):
    check_id = ConnectionCheckId.UPLOAD
    dependencies = (
        ConnectionCheckId.CURRENT_USER,
        ConnectionCheckId.ROOT_RESOURCE,
    )

    @property
    def title(self) -> str:
        return self.tr("Upload")

    @property
    def initial_description(self) -> str:
        return self.tr("Preparing the upload test.")

    def run_check(
        self,
        context: ConnectionDiagnosticContext,
        ngw_connection: "QgsNgwConnection",
        feedback: QgsFeedback,
        report_update: UpdateReporter,
    ) -> ConnectionCheckResult:
        temp_file_path = self._create_temporary_upload_file()
        self._report_update(
            ConnectionCheckState.STARTED,
            self.tr("Uploading a temporary file to the server."),
            report_update,
        )
        try:
            start_time = time.monotonic()
            server_response = ngw_connection.tus_upload_file(
                str(temp_file_path),
                lambda *args: None,
                feedback=feedback,
            )
            duration = max(time.monotonic() - start_time, 0.0)
        except NgwError as error:
            self._raise_if_canceled(feedback, error)
            if self._is_network_error(error):
                return self._failure(
                    self.tr("The temporary upload test failed."),
                    issue=self._network_issue(
                        error,
                        self.tr(
                            "Check the network path to the server and retry the checks."
                        ),
                    ),
                )

            return self._failure(
                self.tr("The temporary upload test failed."),
                issue=self._server_issue(
                    self.tr("The server rejected the temporary upload."),
                    self.tr(
                        "Ask the administrator to inspect the file upload component on the server."
                    ),
                    technical_details=error.detail,
                ),
            )
        except NgConnectError as error:
            self._raise_if_canceled(feedback, error)
            return self._failure(
                self.tr("The temporary upload test failed."),
                issue=self._network_issue(
                    error,
                    self.tr(
                        "Check the network path to the server and retry the checks."
                    ),
                ),
            )
        finally:
            if temp_file_path.exists():
                temp_file_path.unlink()

        payload = UploadDiagnosticInfo(
            bytes_uploaded=DIAGNOSTIC_UPLOAD_SIZE_BYTES,
            duration_seconds=duration,
            server_response=server_response,
        )
        speed = payload.speed_mbit_per_second
        if speed < MIN_UPLOAD_SPEED_MBIT_PER_SECOND:
            issue = ConnectionIssue(
                source=ConnectionIssueSource.NETWORK,
                details=self.tr(
                    "The upload succeeded, but the connection speed is lower than the recommended threshold."
                ),
                resolution=self.tr(
                    "Check the network path to the server or ask the administrator to inspect the server performance."
                ),
            )
            return self._warning(
                self.tr(
                    "The temporary upload succeeded, but the speed is only {speed:.2f} Mbit/s."
                ).format(speed=speed),
                issue=issue,
                payload=payload,
            )

        return self._success(
            self.tr("Upload succeeded at {speed:.2f} Mbit/s.").format(
                speed=speed
            ),
            payload=payload,
        )

    def _create_temporary_upload_file(self) -> Path:
        with NamedTemporaryFile(delete=False, suffix=".bin") as file_obj:
            file_obj.write(b"\0" * DIAGNOSTIC_UPLOAD_SIZE_BYTES)
            return Path(file_obj.name)
