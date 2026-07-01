from html.parser import HTMLParser
from typing import List, Optional, Tuple
from urllib.parse import urlparse


class NgwServerTitleParser(HTMLParser):
    _capture_depth: Optional[int]
    _captured_header_text: List[str]
    _captured_title_text: List[str]
    _div_depth: int
    _header_depth: Optional[int]
    _in_title: bool
    _site_name: Optional[str]
    _title: Optional[str]

    def __init__(self) -> None:
        super().__init__()
        self._capture_depth = None
        self._captured_header_text = []
        self._captured_title_text = []
        self._div_depth = 0
        self._header_depth = None
        self._in_title = False
        self._site_name = None
        self._title = None

    @property
    def title(self) -> Optional[str]:
        if self._site_name:
            return self._site_name

        if self._title:
            return self._title

        return self._header_title()

    @classmethod
    def extract_title(cls, html: str) -> Optional[str]:
        parser = cls()
        parser.feed(html)
        parser.close()
        return parser.title

    def handle_starttag(
        self, tag: str, attrs: List[Tuple[str, Optional[str]]]
    ) -> None:
        attribute_map = {name.lower(): value or "" for name, value in attrs}
        if tag == "meta":
            self._handle_meta_tag(attribute_map)
            return

        if tag == "title":
            self._in_title = True
            return

        if tag != "div":
            return

        self._div_depth += 1
        classes = set(attribute_map.get("class", "").split())
        if (
            self._header_depth is None
            and "ngw-pyramid-layout-header" in classes
        ):
            self._header_depth = self._div_depth
            return

        if (
            self._header_depth is not None
            and self._capture_depth is None
            and "text" in classes
        ):
            self._capture_depth = self._div_depth

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
            if self._title is None:
                self._title = self._normalize_title(
                    "".join(self._captured_title_text)
                )
            self._captured_title_text = []
            return

        if tag != "div" or self._div_depth <= 0:
            return

        if self._capture_depth == self._div_depth:
            self._capture_depth = None

        if self._header_depth == self._div_depth:
            self._header_depth = None

        self._div_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._captured_title_text.append(data)

        if self._capture_depth is not None:
            self._captured_header_text.append(data)

    def _handle_meta_tag(self, attribute_map: dict) -> None:
        property_name = attribute_map.get("property", "").lower()
        if property_name != "og:site_name":
            return

        content = attribute_map.get("content", "")
        site_name = content.strip()
        if len(site_name) > 0:
            self._site_name = site_name

    def _header_title(self) -> Optional[str]:
        return self._normalize_title(" ".join(self._captured_header_text))

    def _normalize_title(self, value: str) -> Optional[str]:
        title = " ".join(value.split()).strip()
        if len(title) == 0:
            return None

        title_parts = [
            part.strip() for part in title.split("|") if part.strip()
        ]
        if len(title_parts) > 1:
            return title_parts[-1]

        return title


def suggested_connection_name(url: str) -> str:
    normalized_url = url.strip()
    if len(normalized_url) == 0:
        return normalized_url

    if "://" not in normalized_url:
        normalized_url = f"https://{normalized_url}"

    parse_result = urlparse(normalized_url)
    connection_name = parse_result.netloc
    if len(connection_name) == 0:
        return normalized_url

    if connection_name.endswith(".nextgis.com"):
        return connection_name.split(".")[0]

    return connection_name
