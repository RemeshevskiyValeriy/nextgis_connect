import re
from typing import Any, ClassVar, Dict, List, Optional, Set


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
        normalized_value = self._normalized_resource_type(value)
        if normalized_value is None:
            return

        resource_types.add(normalized_value)

    def _normalized_resource_type(self, value: str) -> Optional[str]:
        normalized_value = value.strip()
        if normalized_value in self._IGNORED_CANDIDATES:
            return None

        if self._TYPE_PATTERN.match(normalized_value) is None:
            return None

        return normalized_value


class ResourceBlueprintLabelParser(ResourceBlueprintTypeParser):
    _LABEL_KEYS = (
        "label",
        "display_name",
        "title",
    )

    def parse(self, blueprint: Any) -> Dict[str, str]:
        resource_labels: Dict[str, str] = {}
        self._collect_labels(blueprint, resource_labels)
        return dict(sorted(resource_labels.items()))

    def _collect_labels(
        self,
        value: Any,
        resource_labels: Dict[str, str],
    ) -> None:
        if isinstance(value, list):
            self._collect_labels_from_list(value, resource_labels)
            return

        if isinstance(value, dict):
            self._collect_labels_from_dict(value, resource_labels)

    def _collect_labels_from_list(
        self,
        values: List[Any],
        resource_labels: Dict[str, str],
    ) -> None:
        if len(values) >= 2 and isinstance(values[1], str):
            self._add_label(values[0], values[1], resource_labels)

        for value in values:
            self._collect_labels(value, resource_labels)

    def _collect_labels_from_dict(
        self,
        values: Dict[str, Any],
        resource_labels: Dict[str, str],
    ) -> None:
        resource_type = self._resource_type_from_dict(values)
        if resource_type is not None:
            label = self._label_from_dict(values)
            if label is not None:
                resource_labels.setdefault(resource_type, label)

        for key, value in values.items():
            if isinstance(value, dict):
                label = self._label_from_dict(value)
                if label is not None:
                    self._add_label(key, label, resource_labels)

            self._collect_labels(value, resource_labels)

    def _resource_type_from_dict(
        self,
        values: Dict[str, Any],
    ) -> Optional[str]:
        for key in self._VALUE_KEYS:
            value = values.get(key)
            if not isinstance(value, str):
                continue

            resource_type = self._normalized_resource_type(value)
            if resource_type is not None:
                return resource_type

        return None

    def _label_from_dict(self, values: Dict[str, Any]) -> Optional[str]:
        for key in self._LABEL_KEYS:
            value = values.get(key)
            if isinstance(value, str) and value.strip() != "":
                return value.strip()

        return None

    def _add_label(
        self,
        resource_type_value: Any,
        label: str,
        resource_labels: Dict[str, str],
    ) -> None:
        if not isinstance(resource_type_value, str):
            return

        resource_type = self._normalized_resource_type(resource_type_value)
        if resource_type is None:
            return

        normalized_label = label.strip()
        if normalized_label == "":
            return

        resource_labels.setdefault(resource_type, normalized_label)
