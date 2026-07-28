import itertools
import re
from dataclasses import dataclass
from typing import List, Optional, Protocol, Tuple, Union
from urllib.parse import quote_plus


@dataclass(frozen=True)
class SearchTag:
    """Store a searchable NGW query tag definition.

    Describe how user-facing search tags map to NGW API query fields
    and which value forms are accepted by the parser.

    :ivar name: User-facing tag name without the leading ``@``.
    :ivar query_name: NGW API query field name.
    :ivar in_supported: Whether multiple values can use ``__in``.
    :ivar unquoted_value_pattern: Regular expression for unquoted values.
    """

    name: str
    query_name: str
    in_supported: bool = True
    unquoted_value_pattern: str = ""


@dataclass(frozen=True)
class SearchPredicate:
    """Store a parsed structured search predicate.

    Bind a known search tag to a query operator and one or more
    parsed values ready for NGW query generation.

    :ivar tag: Parsed search tag metadata.
    :ivar operator: Internal NGW query operator suffix.
    :ivar values: Parsed predicate values.
    """

    tag: SearchTag
    operator: str
    values: Tuple[object, ...]


@dataclass(frozen=True)
class MetadataPredicate:
    """Store a parsed metadata equality predicate.

    Keep the metadata key and textual value extracted from
    ``@metadata["key"] = value`` search expressions.

    :ivar key: Metadata key selected by the expression.
    :ivar value: Metadata value selected by the expression.
    """

    key: str
    value: str


SearchExpression = Union[SearchPredicate, MetadataPredicate]


@dataclass(frozen=True)
class DefaultSearch:
    """Store fallback text search data.

    Represent the plain-text search branch used when the input cannot
    be parsed as a structured tag expression.

    :ivar value: User-provided display name fragment.
    :ivar exact: Whether the fallback search must match exactly.
    """

    value: str
    exact: bool


@dataclass(frozen=True)
class ParsedSearch:
    """Store a parsed search expression.

    Hold either structured predicate groups or a fallback display-name
    search when parsing cannot produce structured predicates.

    :ivar groups: OR groups containing AND predicate expressions.
    :ivar fallback: Fallback display-name search data, if applicable.
    """

    groups: Tuple[Tuple[SearchExpression, ...], ...]
    fallback: Optional[DefaultSearch] = None

    @property
    def is_fallback(self) -> bool:
        """Return whether parsing fell back to display-name search.

        :return: ``True`` when fallback search data is present.
        """
        return self.fallback is not None


class OwnerResolver(Protocol):
    """Resolve owner names used by search predicates.

    Implement this protocol to translate owner text entered by the
    caller into numeric owner identifiers accepted by NGW queries.
    """

    def resolve_equal(self, values: List[str]) -> List[int]:
        """Resolve exact owner names.

        :param values: Owner names from equality or ``IN`` predicates.
        :return: Matching owner identifiers.
        """
        ...

    def resolve_like(self, operator: str, value: str) -> List[int]:
        """Resolve owner names matched by a text operator.

        :param operator: Parsed text search operator.
        :param value: Owner name fragment from the predicate.
        :return: Matching owner identifiers.
        """
        ...


class SearchSyntax:
    """Expose supported search tags.

    Provide lookup helpers for integer and string search tags used by
    the parser and suggestion builder.
    """

    INT_TAGS: Tuple[SearchTag, ...] = (
        SearchTag("id", "id"),
        SearchTag("parent", "parent"),
        SearchTag("root", "root", in_supported=False),
        SearchTag("owner", "owner_user"),
    )
    STR_TAGS: Tuple[SearchTag, ...] = (
        SearchTag("type", "cls", unquoted_value_pattern=r"[a-zA-Z0-9_]+"),
        SearchTag("name", "display_name"),
        SearchTag("keyname", "keyname"),
        SearchTag("owner", "owner", unquoted_value_pattern=r"[^'\"]+"),
    )
    TAGS: Tuple[SearchTag, ...] = (*INT_TAGS, *STR_TAGS)

    def known_tag_names(self) -> List[str]:
        """Return supported user-facing search tag names.

        :return: Tag names accepted in structured search input.
        """
        return [tag.name for tag in self.TAGS] + ["metadata"]

    def int_tag(self, tag_name: str) -> Optional[SearchTag]:
        """Return an integer-valued tag by name.

        :param tag_name: User-facing tag name without the leading ``@``.
        :return: Matching tag definition or ``None``.
        """
        return self._tag_by_name(tag_name, self.INT_TAGS)

    def str_tag(self, tag_name: str) -> Optional[SearchTag]:
        """Return a string-valued tag by name.

        :param tag_name: User-facing tag name without the leading ``@``.
        :return: Matching tag definition or ``None``.
        """
        return self._tag_by_name(tag_name, self.STR_TAGS)

    def _tag_by_name(
        self,
        tag_name: str,
        tags: Tuple[SearchTag, ...],
    ) -> Optional[SearchTag]:
        for tag in tags:
            if tag.name == tag_name:
                return tag

        return None


class SearchQueryParser:
    """Parse user search text.

    Convert structured ``@tag`` expressions into predicate groups and
    preserve plain text as a fallback display-name search.
    """

    def __init__(self, syntax: Optional[SearchSyntax] = None) -> None:
        """Initialize the parser.

        :param syntax: Search syntax definition to use.
        """
        self._syntax = syntax or SearchSyntax()

    def parse(self, search_string: str) -> ParsedSearch:
        """Parse search text.

        :param search_string: Raw search text entered by the caller.
        :return: Structured predicates or fallback search data.
        """
        stripped_search_string = search_string.strip()
        if not stripped_search_string.startswith("@"):
            return self._default_search(stripped_search_string)

        lower_search_string = stripped_search_string.lower()
        and_operator_count = lower_search_string.count(" and ")
        or_operator_count = lower_search_string.count(" or ")

        if and_operator_count + or_operator_count not in (
            and_operator_count,
            or_operator_count,
        ):
            return self._default_search(stripped_search_string)

        groups = []
        or_parts = re.split(r"(?i)\sor\s", stripped_search_string)
        for or_part in or_parts:
            predicates = []
            and_parts = re.split(r"(?i)\sand\s", or_part)
            for and_part in and_parts:
                predicate = self._parse_predicate(and_part)
                if predicate is None:
                    return self._default_search(stripped_search_string)

                predicates.append(predicate)

            groups.append(tuple(predicates))

        if len(groups) == 0:
            return self._default_search(stripped_search_string)

        return ParsedSearch(groups=tuple(groups))

    def _default_search(self, search_string: str) -> ParsedSearch:
        exact = search_string.startswith('"') and search_string.endswith('"')
        value = search_string[1:-1] if exact else search_string
        return ParsedSearch(
            groups=(),
            fallback=DefaultSearch(value=value, exact=exact),
        )

    def _parse_predicate(
        self, search_string: str
    ) -> Optional[SearchExpression]:
        stripped_search_string = search_string.strip()

        predicate = self._parse_int_predicate(stripped_search_string)
        if predicate is not None:
            return predicate

        predicate = self._parse_str_predicate(stripped_search_string)
        if predicate is not None:
            return predicate

        return self._parse_metadata_predicate(stripped_search_string)

    def _parse_int_predicate(
        self,
        search_string: str,
    ) -> Optional[SearchPredicate]:
        tag_match = re.match(r"^@(?P<tag>[a-z_]+)", search_string)
        if tag_match is None:
            return None

        tag = self._syntax.int_tag(tag_match.group("tag").lower())
        if tag is None:
            return None

        tag_name = re.escape(tag.name)
        eq_match = re.match(
            rf"^@{tag_name}\s*=\s*(?P<value>\d+)$",
            search_string,
            flags=re.IGNORECASE,
        )
        if eq_match is not None:
            return SearchPredicate(
                tag=tag,
                operator="__eq",
                values=(int(eq_match.group("value")),),
            )

        in_match = re.match(
            rf"^@{tag_name}\s+IN\s*\((?P<values>[\d,\s]+)\)$",
            search_string,
            flags=re.IGNORECASE,
        )
        if in_match is None:
            return None

        values = [
            int(value.strip())
            for value in in_match.group("values").split(",")
            if value.strip() != ""
        ]
        if len(values) == 0:
            return None

        return SearchPredicate(
            tag=tag,
            operator="__eq",
            values=tuple(values),
        )

    def _parse_str_predicate(
        self,
        search_string: str,
    ) -> Optional[SearchPredicate]:
        tag_match = re.match(r"^@(?P<tag>[a-z_]+)", search_string)
        if tag_match is None:
            return None

        tag = self._syntax.str_tag(tag_match.group("tag").lower())
        if tag is None:
            return None

        tag_name = re.escape(tag.name)
        quoted_eq_match = re.match(
            rf"^@{tag_name}\s*=\s*(?P<quote>['\"])(?P<value>.*?)"
            rf"(?P=quote)$",
            search_string,
            flags=re.IGNORECASE,
        )
        if quoted_eq_match is not None:
            return SearchPredicate(
                tag=tag,
                operator="__eq",
                values=(quoted_eq_match.group("value"),),
            )

        quoted_like_match = re.match(
            rf"^@{tag_name}\s+(?P<operation>ILIKE|LIKE)\s+"
            rf"(?P<quote>['\"])(?P<value>.*?)(?P=quote)$",
            search_string,
            flags=re.IGNORECASE,
        )
        if quoted_like_match is not None:
            operation = quoted_like_match.group("operation").lower()
            return SearchPredicate(
                tag=tag,
                operator=f"__{operation}",
                values=(quoted_like_match.group("value"),),
            )

        in_match = re.match(
            rf"^@{tag_name}\s+IN\s*\((?P<values>.*?)\)$",
            search_string,
            flags=re.IGNORECASE,
        )
        if in_match is not None:
            matches = re.findall(
                r"\"(.*?)\"|'(.*?)'", in_match.group("values")
            )
            values = tuple(
                match for pair in matches for match in pair if match
            )
            if len(values) == 0:
                return None

            return SearchPredicate(tag=tag, operator="__eq", values=values)

        if tag.unquoted_value_pattern == "":
            return None

        unquoted_eq_match = re.match(
            rf"^@{tag_name}\s*=\s*"
            rf"(?P<value>{tag.unquoted_value_pattern})$",
            search_string,
            flags=re.IGNORECASE,
        )
        if unquoted_eq_match is not None:
            return SearchPredicate(
                tag=tag,
                operator="__eq",
                values=(unquoted_eq_match.group("value").strip(),),
            )

        unquoted_like_match = re.match(
            rf"^@{tag_name}\s+(?P<operation>ILIKE|LIKE)\s+"
            rf"(?P<value>{tag.unquoted_value_pattern})$",
            search_string,
            flags=re.IGNORECASE,
        )
        if unquoted_like_match is None:
            return None

        operation = unquoted_like_match.group("operation").lower()
        return SearchPredicate(
            tag=tag,
            operator=f"__{operation}",
            values=(unquoted_like_match.group("value").strip(),),
        )

    def _parse_metadata_predicate(
        self,
        search_string: str,
    ) -> Optional[MetadataPredicate]:
        pattern = r'@metadata\["([^"]+)"\]\s*=\s*(?:"([^"]+)"|([^"]\S*))'
        match = re.match(pattern, search_string)
        if match is None:
            return None

        value = (
            match.group(2) if match.group(2) is not None else match.group(3)
        )
        return MetadataPredicate(key=match.group(1), value=value)


class NgwSearchQueryBuilder:
    """Build NGW query strings from parsed search data.

    Convert parsed predicates into one or more query strings suitable
    for NGW resource search requests.
    """

    def __init__(self, owner_resolver: OwnerResolver) -> None:
        """Initialize the query builder.

        :param owner_resolver: Resolver for owner-name predicates.
        """
        self._owner_resolver = owner_resolver

    def build(self, parsed_search: ParsedSearch) -> List[str]:
        """Build NGW query strings.

        :param parsed_search: Parsed search expression to convert.
        :return: Query strings accepted by NGW resource search.
        """
        if parsed_search.fallback is not None:
            return [self._default_query(parsed_search.fallback)]

        queries = []
        for predicates in parsed_search.groups:
            groups = [
                self._predicate_queries(predicate) for predicate in predicates
            ]
            queries.extend(
                "&".join(combo) for combo in itertools.product(*groups)
            )

        return queries

    def _predicate_queries(self, predicate: SearchExpression) -> List[str]:
        if isinstance(predicate, SearchPredicate):
            return self._search_predicate_queries(predicate)

        if isinstance(predicate, MetadataPredicate):
            return self._metadata_queries(predicate)

        return []

    def _default_query(self, default_search: DefaultSearch) -> str:
        if default_search.exact:
            search_value = quote_plus(default_search.value)
            return f"display_name={search_value}"

        search_value = quote_plus(f"%{default_search.value}%")
        return f"display_name__ilike={search_value}"

    def _search_predicate_queries(
        self,
        predicate: SearchPredicate,
    ) -> List[str]:
        values = list(predicate.values)
        operator = predicate.operator

        values_count = len(values)
        if values_count == 0:
            return []

        if predicate.tag.name == "owner" and isinstance(values[0], str):
            if operator == "__eq":
                values = self._owner_resolver.resolve_equal(
                    [str(value) for value in values]
                )
            else:
                values = self._owner_resolver.resolve_like(
                    operator,
                    str(values[0]),
                )
            operator = "__eq"

        values_count = len(values)
        if values_count == 0:
            return []

        if values_count == 1:
            return [
                self._equal_query(
                    predicate.tag.query_name, operator, values[0]
                )
            ]

        if predicate.tag.in_supported:
            return [self._in_query(predicate.tag.query_name, values)]

        return [
            self._equal_query(predicate.tag.query_name, operator, value)
            for value in values
        ]

    def _equal_query(
        self,
        query_name: str,
        operator: str,
        value: object,
    ) -> str:
        query_operator = "" if operator == "__eq" else operator
        return f"{query_name}{query_operator}={quote_plus(str(value))}"

    def _in_query(self, query_name: str, values: List[object]) -> str:
        joined_values = ",".join(quote_plus(str(value)) for value in values)
        return f"{query_name}__in={joined_values}"

    def _metadata_queries(self, predicate: MetadataPredicate) -> List[str]:
        key = quote_plus(predicate.key)
        value = predicate.value
        ilike_value = quote_plus(f"%{value}%")

        queries = [f"resmeta__ilike[{key}]={ilike_value}"]
        if value.isnumeric():
            queries.append(f"resmeta__json[{key}]={value}")
        elif value.lower() in ("true", "false"):
            queries.append(f"resmeta__json[{key}]={value.lower()}")
        else:
            try:
                float_value = float(value)
                queries.append(f"resmeta__json[{key}]={float_value}")
            except ValueError:
                pass

        return queries
