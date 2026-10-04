from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from xml.etree import ElementTree

from faultweaver.assessments.urls import InvalidCrawlUrl, canonicalize_url, resolve_url


@dataclass(frozen=True, slots=True)
class DiscoveredLink:
    url: str
    kind: str


@dataclass(frozen=True, slots=True)
class FormField:
    name: str
    input_type: str
    has_value: bool


@dataclass(slots=True)
class FormMetadata:
    action_url: str
    method: str
    enctype: str
    fields: list[FormField] = field(default_factory=list)


@dataclass(slots=True)
class DiscoveryResult:
    links: list[DiscoveredLink] = field(default_factory=list)
    forms: list[FormMetadata] = field(default_factory=list)


class _DiscoveryParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.result = DiscoveryResult()
        self._form: FormMetadata | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "base" and values.get("href"):
            self.base_url = self._resolved(values["href"]) or self.base_url
            return
        targets = {
            "a": ("href", "navigation"),
            "link": ("href", "stylesheet"),
            "script": ("src", "script"),
            "img": ("src", "image"),
            "iframe": ("src", "iframe"),
            "source": ("src", "media"),
        }
        if tag in targets:
            attribute, kind = targets[tag]
            if value := values.get(attribute):
                self._append(value, kind)
        if tag == "form":
            action = self._resolved(values.get("action") or self.base_url)
            if action:
                self._form = FormMetadata(
                    action_url=action,
                    method=(values.get("method") or "GET").upper(),
                    enctype=values.get("enctype") or "application/x-www-form-urlencoded",
                )
                self.result.forms.append(self._form)
                self.result.links.append(DiscoveredLink(action, "form"))
        elif tag in {"input", "button", "select", "textarea"} and self._form is not None:
            name = values.get("name")
            if name:
                self._form.fields.append(
                    FormField(
                        name=name,
                        input_type=(values.get("type") or tag).lower(),
                        has_value=values.get("value") is not None,
                    )
                )

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self._form = None

    def _append(self, value: str, kind: str) -> None:
        if resolved := self._resolved(value):
            self.result.links.append(DiscoveredLink(resolved, kind))

    def _resolved(self, value: str) -> str | None:
        try:
            return resolve_url(self.base_url, value)
        except InvalidCrawlUrl:
            return None


def discover_html(body: str, base_url: str) -> DiscoveryResult:
    parser = _DiscoveryParser(canonicalize_url(base_url))
    parser.feed(body)
    return parser.result


def discover_sitemap(body: str, *, limit: int) -> list[str]:
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return []
    results: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "loc" or not element.text:
            continue
        try:
            results.append(canonicalize_url(element.text.strip()))
        except InvalidCrawlUrl:
            continue
        if len(results) >= limit:
            break
    return results
