from typing import Any, ClassVar, Dict, Mapping

from qgis.core import QgsProviderRegistry


class QgisWmsUriFactory:
    """Build WMS provider URIs with the same defaults as QGIS UI."""

    DEFAULT_PARAMETERS: ClassVar[Dict[str, str]] = {
        "contextualWMSLegend": "0",
        "dpiMode": "7",
        "featureCount": "10",
        "tilePixelRatio": "0",
    }

    @classmethod
    def create(cls, uri_params: Mapping[str, Any]) -> str:
        provider_metadata = QgsProviderRegistry.instance().providerMetadata(
            "wms"
        )
        if provider_metadata is None:
            raise RuntimeError("QGIS WMS provider is unavailable")

        qgis_uri_params: Dict[str, Any] = dict(cls.DEFAULT_PARAMETERS)
        qgis_uri_params.update(uri_params)

        encoded_uri = provider_metadata.encodeUri(qgis_uri_params)
        return cls._normalize_empty_styles(encoded_uri, qgis_uri_params)

    @classmethod
    def _normalize_empty_styles(
        cls,
        encoded_uri: str,
        uri_params: Mapping[str, Any],
    ) -> str:
        if uri_params.get("styles") != "":
            return encoded_uri

        if encoded_uri == "styles=":
            return "styles"

        normalized_uri = encoded_uri.replace("&styles=&", "&styles&")
        if normalized_uri.startswith("styles=&"):
            normalized_uri = "styles&" + normalized_uri[len("styles=&") :]

        if normalized_uri.endswith("&styles="):
            normalized_uri = normalized_uri[:-1]

        return normalized_uri
