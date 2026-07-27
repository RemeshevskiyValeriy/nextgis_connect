from enum import IntEnum
from typing import Tuple

from nextgis_connect.platform.qgis.compat import QgsFeatureId

LayerId = str
FeatureKey = Tuple[LayerId, QgsFeatureId]


class IdentificationTab(IntEnum):
    """Identification tabs for the feature identification results widget."""

    ATTRIBUTES = 0
    ATTACHMENTS = 1
    DESCRIPTION = 2


class AttachmentsSortMode(IntEnum):
    """Sorting modes for attachments."""

    BY_NAME = 0
    BY_TYPE = 1
    BY_SIZE = 2
