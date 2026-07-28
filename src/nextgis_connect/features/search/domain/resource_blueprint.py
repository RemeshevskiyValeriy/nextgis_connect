import re
from typing import Any, ClassVar, Dict, List, Set


class ResourceBlueprintTypeParser:
    _VALUE_KEYS = (
        "cls",
        "identity",
        "id",
        "key",
        "name",
        "value",
    )
    _COLLECTION_KEYS = (
        "blueprint",
        "choices",
        "children",
        "enum",
        "items",
        "resource",
        "resources",
        "types",
    )
    _IGNORED_CANDIDATES: ClassVar[Set[str]] = {
        "children",
        "cls",
        "description",
        "display_name",
        "id",
        "interfaces",
        "keyname",
        "label",
        "metadata",
        "name",
        "owner_user",
        "parent",
        "permissions",
        "resource",
        "scopes",
        "value",
    }
    _TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

    def parse(self, blueprint: Any) -> List[str]:
        resource_types: Set[str] = set()
        self._collect(blueprint, resource_types)
        return sorted(resource_types)

    def _collect(self, value: Any, resource_types: Set[str]) -> None:
        if isinstance(value, str):
            self._add_candidate(value, resource_types)
            return

        if isinstance(value, list):
            self._collect_from_list(value, resource_types)
            return

        if isinstance(value, dict):
            self._collect_from_dict(value, resource_types)

    def _collect_from_list(
        self,
        values: List[Any],
        resource_types: Set[str],
    ) -> None:
        for value in values:
            if isinstance(value, list) and len(value) > 0:
                self._collect(value[0], resource_types)
                continue

            self._collect(value, resource_types)

    def _collect_from_dict(
        self,
        values: Dict[str, Any],
        resource_types: Set[str],
    ) -> None:
        for key in self._VALUE_KEYS:
            value = values.get(key)
            if isinstance(value, str):
                self._add_candidate(value, resource_types)
            elif key == "cls" and value is not None:
                self._collect(value, resource_types)

        for key in self._COLLECTION_KEYS:
            value = values.get(key)
            if value is not None:
                self._collect(value, resource_types)

        if not resource_types:
            self._collect_type_like_keys(values, resource_types)

    def _collect_type_like_keys(
        self,
        values: Dict[str, Any],
        resource_types: Set[str],
    ) -> None:
        for key, value in values.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue

            self._add_candidate(key, resource_types)

    def _add_candidate(
        self,
        value: str,
        resource_types: Set[str],
    ) -> None:
        normalized_value = value.strip()
        if normalized_value in self._IGNORED_CANDIDATES:
            return

        if self._TYPE_PATTERN.match(normalized_value) is None:
            return

        resource_types.add(normalized_value)
