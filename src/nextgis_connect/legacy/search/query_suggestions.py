import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class ResourceTypeSuggestionContext:
    base_text: str
    closing_quote: str
    value_prefix: str


@dataclass(frozen=True)
class OwnerSuggestionContext:
    base_text: str
    closing_quote: str
    value_prefix: str


class TextSearchSuggestionBuilder:
    OWNER_ALIASES: Tuple[str, ...] = ("me",)

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
    _OWNER_PATTERN = re.compile(
        r"^@owner(?P<before_equals>\s*)=(?P<after_equals>\s*)"
        r"(?P<quote>['\"]?)(?P<value>[^'\"]*)$",
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

    def owner_context(
        self,
        search_string: str,
    ) -> Optional[OwnerSuggestionContext]:
        fragment = self._last_tag_fragment(search_string)
        if fragment is None:
            return None

        prefix, tag_text = fragment
        match = self._OWNER_PATTERN.match(tag_text)
        if match is None:
            return None

        quote = match.group("quote")
        base_text = f"{prefix}@owner = {quote}"
        return OwnerSuggestionContext(
            base_text=base_text,
            closing_quote=quote,
            value_prefix=match.group("value").lower(),
        )

    def owner_suggestions(
        self,
        search_string: str,
        owners: Iterable[str],
    ) -> Optional[List[str]]:
        context = self.owner_context(search_string)
        if context is None:
            return None

        suggestions = []
        added_owners = set()
        for owner in self._owner_suggestion_values(owners):
            if not owner.lower().startswith(context.value_prefix):
                continue

            owner_key = owner.casefold()
            if owner_key in added_owners:
                continue

            if not self._can_use_quoted_value(owner, context.closing_quote):
                continue

            suggestions.append(
                f"{context.base_text}{owner}{context.closing_quote}"
            )
            added_owners.add(owner_key)

        return suggestions

    def _owner_suggestion_values(
        self,
        owners: Iterable[str],
    ) -> Iterable[str]:
        yield from self.OWNER_ALIASES
        yield from owners

    def _can_use_quoted_value(self, value: str, quote: str) -> bool:
        if quote != "":
            return quote not in value

        return '"' not in value and "'" not in value

    def _last_tag_fragment(
        self,
        search_string: str,
    ) -> Optional[Tuple[str, str]]:
        tag_start = search_string.rfind("@")
        if tag_start == -1:
            return None

        return search_string[:tag_start], search_string[tag_start:]
