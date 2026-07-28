import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class ResourceTypeSuggestionContext:
    base_text: str
    closing_quote: str
    value_prefix: str


class TextSearchSuggestionBuilder:
    KEYWORDS: Tuple[str, ...] = (
        "id",
        "parent",
        "root",
        "owner",
        "type",
        "name",
        "keyname",
        "metadata",
    )

    _KEYWORD_PATTERN = re.compile(r"^@(?P<prefix>[a-z_]*)$", re.IGNORECASE)
    _TYPE_PATTERN = re.compile(
        r"^@type(?P<before_equals>\s*)=(?P<after_equals>\s*)"
        r"(?P<quote>['\"]?)(?P<value>[a-z0-9_]*)$",
        re.IGNORECASE,
    )

    def keyword_suggestions(self, search_string: str) -> Optional[List[str]]:
        fragment = self._last_tag_fragment(search_string)
        if fragment is None:
            return None

        prefix, tag_text = fragment
        match = self._KEYWORD_PATTERN.match(tag_text)
        if match is None:
            return None

        keyword_prefix = match.group("prefix").lower()
        suggestions = [
            f"{prefix}@{keyword}"
            for keyword in self.KEYWORDS
            if keyword.startswith(keyword_prefix)
        ]
        return suggestions

    def resource_type_context(
        self,
        search_string: str,
    ) -> Optional[ResourceTypeSuggestionContext]:
        fragment = self._last_tag_fragment(search_string)
        if fragment is None:
            return None

        prefix, tag_text = fragment
        match = self._TYPE_PATTERN.match(tag_text)
        if match is None:
            return None

        quote = match.group("quote")
        base_text = (
            f"{prefix}@type"
            f"{match.group('before_equals')}="
            f"{match.group('after_equals')}"
            f"{quote}"
        )
        return ResourceTypeSuggestionContext(
            base_text=base_text,
            closing_quote=quote,
            value_prefix=match.group("value").lower(),
        )

    def resource_type_suggestions(
        self,
        search_string: str,
        resource_types: Iterable[str],
    ) -> Optional[List[str]]:
        context = self.resource_type_context(search_string)
        if context is None:
            return None

        suggestions = []
        for resource_type in resource_types:
            if not resource_type.lower().startswith(context.value_prefix):
                continue

            suggestions.append(
                f"{context.base_text}{resource_type}{context.closing_quote}"
            )

        return suggestions

    def _last_tag_fragment(
        self,
        search_string: str,
    ) -> Optional[Tuple[str, str]]:
        tag_start = search_string.rfind("@")
        if tag_start == -1:
            return None

        return search_string[:tag_start], search_string[tag_start:]
