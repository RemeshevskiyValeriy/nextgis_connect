from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, Optional, Tuple

from qgis.core import QgsSettings

from nextgis_connect.ngw_connection.domain.connection import NgwConnection
from nextgis_connect.utils import SupportStatus


class ConnectionIssueSource(Enum):
    SERVER = auto()
    NETWORK = auto()
    CLIENT = auto()


class ConnectionCheckState(Enum):
    NOT_STARTED = auto()
    PENDING = auto()
    STARTED = auto()
    SUCCESS = auto()
    WARNING = auto()
    FAILURE = auto()


class ConnectionCheckId(Enum):
    PLUGIN_VERSION = "plugin_version"
    SERVER_VERSION = "server_version"
    CERTIFICATE = "certificate"
    ROOT_RESOURCE = "root_resource"
    CURRENT_USER = "current_user"
    DOWNLOAD = "download"
    UPLOAD = "upload"


@dataclass(frozen=True)
class ProxySettings:
    enabled: bool
    host: str
    port: str
    proxy_type: str
    user: str
    auth_config_id: str
    no_proxy_urls: str
    has_password: bool

    @classmethod
    def from_settings(cls) -> "ProxySettings":
        settings = QgsSettings()
        return cls(
            enabled=settings.value("proxy/proxyEnabled", False, type=bool),
            host=settings.value("proxy/proxyHost", "", type=str),
            port=settings.value("proxy/proxyPort", "", type=str),
            proxy_type=settings.value("proxy/proxyType", "", type=str),
            user=settings.value("proxy/proxyUser", "", type=str),
            auth_config_id=settings.value("proxy/authcfg", "", type=str),
            no_proxy_urls=settings.value("proxy/noProxyUrls", "", type=str),
            has_password=bool(
                settings.value("proxy/proxyPassword", "", type=str)
            ),
        )

    def to_debug_message(self) -> str:
        parts = (
            f"enabled={self.enabled}",
            f"type={self.proxy_type or '-'}",
            f"host={self.host or '-'}",
            f"port={self.port or '-'}",
            f"user={self.user or '-'}",
            f"authcfg={self.auth_config_id or '-'}",
            f"password_set={self.has_password}",
            f"no_proxy={self.no_proxy_urls or '-'}",
        )
        return "QGIS proxy: " + " ".join(parts)


@dataclass(frozen=True)
class ConnectionIssue:
    source: ConnectionIssueSource
    details: str
    resolution: str
    technical_details: Optional[str] = None


@dataclass(frozen=True)
class ConnectionCheckUpdate:
    check_id: ConnectionCheckId
    title: str
    state: ConnectionCheckState
    description: str
    issue: Optional[ConnectionIssue] = None


@dataclass(frozen=True)
class ConnectionCheckResult:
    check_id: ConnectionCheckId
    title: str
    state: ConnectionCheckState
    description: str
    issue: Optional[ConnectionIssue]
    is_blocking: bool
    payload: Optional[Any] = None


@dataclass(frozen=True)
class CurrentUserInfo:
    keyname: str
    display_name: str
    expected_keyname: Optional[str]
    expects_guest: bool


@dataclass(frozen=True)
class PluginVersionInfo:
    installed_version: str
    repository_version: str


@dataclass(frozen=True)
class ServerVersionInfo:
    version: str
    support_status: SupportStatus


@dataclass(frozen=True)
class UploadDiagnosticInfo:
    bytes_uploaded: int
    duration_seconds: float
    server_response: Any

    @property
    def speed_mbit_per_second(self) -> float:
        if self.duration_seconds <= 0:
            return 0.0

        bits_per_second = (self.bytes_uploaded * 8) / self.duration_seconds
        return bits_per_second / 1_000_000


@dataclass(frozen=True)
class ConnectionVerificationResult:
    resolved_name: str
    current_user: CurrentUserInfo


@dataclass
class ConnectionDiagnosticContext:
    connection: NgwConnection
    proxy_settings: ProxySettings = field(
        default_factory=ProxySettings.from_settings
    )
    results: Dict[ConnectionCheckId, ConnectionCheckResult] = field(
        default_factory=dict
    )

    def store_result(self, result: ConnectionCheckResult) -> None:
        self.results[result.check_id] = result

    def result(
        self, check_id: ConnectionCheckId
    ) -> Optional[ConnectionCheckResult]:
        return self.results.get(check_id)


@dataclass(frozen=True)
class ConnectionDiagnosticsSummary:
    results: Tuple[ConnectionCheckResult, ...]

    @property
    def state(self) -> ConnectionCheckState:
        if any(
            result.state == ConnectionCheckState.FAILURE
            for result in self.results
        ):
            return ConnectionCheckState.FAILURE

        if any(
            result.state == ConnectionCheckState.WARNING
            for result in self.results
        ):
            return ConnectionCheckState.WARNING

        return ConnectionCheckState.SUCCESS

    @property
    def has_blocking_failures(self) -> bool:
        return any(
            result.is_blocking and result.state == ConnectionCheckState.FAILURE
            for result in self.results
        )

    @property
    def first_issue(self) -> Optional[ConnectionIssue]:
        for result in self.results:
            if result.issue is not None:
                return result.issue

        return None

    @property
    def first_blocking_issue(self) -> Optional[ConnectionIssue]:
        for result in self.results:
            if result.is_blocking and result.issue is not None:
                return result.issue

        return None


@dataclass(frozen=True)
class ConnectionDiagnosticsReport:
    summary: ConnectionDiagnosticsSummary
    logs: str
    error: Optional[ConnectionIssue] = None
    is_canceled: bool = False
