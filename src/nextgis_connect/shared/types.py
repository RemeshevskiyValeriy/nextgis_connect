from typing import TypeVar, Union

from nextgis_connect.platform.qgis.compat import QgsFeatureId

FeatureId = QgsFeatureId
FieldId = int
AttachmentId = int

NgwFeatureId = int
NgwFieldId = int
NgwAttachmentId = int

VersionId = int

FileObjectId = int

WktString = str
Wkb64String = str


class UnsetType:
    """Represent an unset value.

    Distinguish an explicitly unset value from ``None`` in typed data
    structures.
    """

    def __repr__(self) -> str:
        """Return the debug representation.

        :return: Debug representation.
        """
        return "<UNSET>"

    def __bool__(self):
        """Return the boolean value.

        :return: Always ``False``.
        """
        return False


Unset = UnsetType()

T = TypeVar("T")
Unsettable = Union[T, UnsetType]
