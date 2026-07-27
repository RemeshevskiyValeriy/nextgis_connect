from typing import List

from nextgis_connect.ngw_connection.domain.connection import NgwConnection

from .base import BaseConnectionCheck


def build_connection_checks(
    connection: NgwConnection,
) -> List[BaseConnectionCheck]:
    from .certificate import CertificateCheck
    from .current_user import CurrentUserCheck
    from .download import DownloadCheck
    from .plugin_version import PluginVersionCheck
    from .root_resource import RootResourceAccessCheck
    from .server_version import ServerVersionCheck
    from .upload import UploadCheck

    return [
        PluginVersionCheck(connection),
        ServerVersionCheck(connection),
        CertificateCheck(connection),
        RootResourceAccessCheck(connection),
        CurrentUserCheck(connection),
        DownloadCheck(connection),
        UploadCheck(connection),
    ]
