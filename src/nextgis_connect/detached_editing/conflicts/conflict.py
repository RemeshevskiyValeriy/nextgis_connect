from dataclasses import dataclass, field
from typing import List

from nextgis_connect.detached_editing.actions import (
    DataChangeAction,
    FeatureAction,
    FeatureId,
)
from nextgis_connect.resources.ngw_field import FieldId


@dataclass
class VersioningConflict:
    local_action: FeatureAction
    remote_action: FeatureAction

    conflicting_fields: List[FieldId] = field(init=False)
    has_geometry_conflict: bool = field(init=False)

    def __post_init__(self) -> None:
        conflicting_fields = []
        has_geometry_conflict = False

        if (
            isinstance(self.local_action, DataChangeAction)
            and isinstance(self.remote_action, DataChangeAction)
            and self.local_action.fields
            and self.remote_action.fields
        ):
            local_fields = set(field[0] for field in self.local_action.fields)
            remote_fields = set(
                field[0] for field in self.remote_action.fields
            )
            conflicting_fields = list(local_fields.intersection(remote_fields))

            has_geometry_conflict = (
                self.local_action.geom is not None
                and self.remote_action.geom is not None
            )

        super().__setattr__("conflicting_fields", conflicting_fields)
        super().__setattr__("has_geometry_conflict", has_geometry_conflict)

    @property
    def fid(self) -> FeatureId:
        return self.local_action.fid
