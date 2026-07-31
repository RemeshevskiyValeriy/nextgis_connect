import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import quote, urlparse

from qgis.core import (
    QgsApplication,
    QgsAuthMethodConfig,
    QgsNetworkRequestParameters,
)
from qgis.PyQt.QtNetwork import QNetworkRequest

from nextgis_connect.platform.logging import logger
from nextgis_connect.plugin.plugin_interface import NgConnectInterface
from nextgis_connect.shared.constants import PLUGIN_NAME


def _plugin_version() -> str:
    return NgConnectInterface.instance().version


def update_user_agent_suffix(request: QNetworkRequest) -> None:
    request_attributes = getattr(
        QgsNetworkRequestParameters, "RequestAttributes", None
    )
    if request_attributes is None:
        return

    user_agent_suffix_flag = getattr(
        request_attributes,
        "AttributeUserAgentSuffix",
        None,
    )
    if user_agent_suffix_flag is None:
        return

    user_agent_suffix_attribute = QNetworkRequest.Attribute(
        user_agent_suffix_flag
    )

    version = _plugin_version()
    if version == "":
        return

    request.setAttribute(
        user_agent_suffix_attribute, f"{PLUGIN_NAME}/{version}"
    )


@dataclass(frozen=True)
class NgwConnection:
    NEXTGIS_DOMAIN = ".nextgis.com"

    id: str
    name: str
    url: str
    auth_config_id: Optional[str]
    old_connection_ids: Tuple[str, ...] = ()

    @property
    def method(self) -> str:
        if self.auth_config_id is None:
            return ""

        return QgsApplication.authManager().configAuthMethodKey(
            self.auth_config_id
        )

    @property
    def domain_uuid(self) -> str:
        return self.domain_uuid_for_url(self.url)

    def update_network_request(self, request: QNetworkRequest) -> bool:
        request_host = urlparse(request.url().toString()).netloc
        connection_host = urlparse(self.normalize_url(self.url)).netloc
        if request_host != connection_host:
            return False

        update_user_agent_suffix(request)
        logger.debug(
            "Updating network request for connection %s (%s)",
            self.name,
            self.id,
        )

        if self.auth_config_id is None:
            return False

        auth_manager = QgsApplication.authManager()
        is_succeeded, _ = auth_manager.updateNetworkRequest(
            request, self.auth_config_id
        )

        return is_succeeded

    def update_uri_config(
        self, params: Dict[str, Any], *, workaround_for_email: bool = False
    ) -> bool:
        if self.auth_config_id is None or (
            self.url not in params.get("url", params.get("path", ""))
        ):
            return False

        if not workaround_for_email or self.method != "Basic":
            params["authcfg"] = self.auth_config_id
            return True

        is_loaded, config = (
            QgsApplication.authManager().loadAuthenticationConfig(
                self.auth_config_id,
                QgsAuthMethodConfig(),
                full=True,
            )
        )

        if not is_loaded:
            return False

        username = config.config("username")
        password = config.config("password")
        quoted_username = quote(username)
        quoted_password = quote(password)

        if username == quoted_username and password == quoted_password:
            params["authcfg"] = self.auth_config_id
            return True

        key = "path" if "path" in params else "url"
        params[key] = params[key].replace(
            "://", f"://{quoted_username}:{quoted_password}@"
        )

        return True

    @classmethod
    def normalize_url(cls, url: str) -> str:
        parse_result = urlparse(url)
        if parse_result.scheme == "":
            parse_result = urlparse("https://" + url)

        scheme = parse_result.scheme
        base_url = parse_result.netloc

        # Force https regardless of what user has selected, but only for cloud
        # connections.
        if base_url.endswith(cls.NEXTGIS_DOMAIN) and scheme != "https":
            scheme = "https"

        if not scheme or not base_url:
            return url

        return f"{scheme}://{base_url}"

    @classmethod
    def domain_uuid_for_url(cls, url: str) -> str:
        domain = urlparse(cls.normalize_url(url)).netloc
        return str(uuid.uuid3(uuid.NAMESPACE_DNS, domain))

    def matches_id(self, connection_id: str) -> bool:
        return (
            connection_id == self.id
            or connection_id in self.old_connection_ids
        )

    @classmethod
    def suggested_id_for_url(
        cls,
        url: str,
        existing_connection_ids: Iterable[str],
        *,
        fallback_id: Optional[str] = None,
    ) -> str:
        existing_ids = set(existing_connection_ids)
        connection_id = cls.domain_uuid_for_url(url)
        if connection_id not in existing_ids:
            return connection_id

        if fallback_id is not None and fallback_id not in existing_ids:
            return fallback_id

        while True:
            connection_id = str(uuid.uuid4())
            if connection_id not in existing_ids:
                return connection_id
