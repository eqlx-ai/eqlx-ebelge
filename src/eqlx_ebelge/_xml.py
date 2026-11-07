"""Safe XML helpers.

Every parse goes through defusedxml with DTDs forbidden: GİB documents never carry a DOCTYPE, and refusing it
blocks entity-expansion ("billion laughs") and external-entity (XXE) attacks.
Nothing here touches the network.
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterator
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import IO
from xml.etree.ElementTree import Element

import defusedxml.ElementTree as safe_et  # noqa: N813
from defusedxml import DefusedXmlException

from .errors import EbelgeError

_DECIMAL = re.compile(r"^-?\d+(\.\d+)?$")


def parse(data: bytes, source: str) -> Element:
    try:
        return safe_et.fromstring(data, forbid_dtd=True)
    except DefusedXmlException as exc:
        raise EbelgeError("unsafe_xml", source, "DTDs and entities are not allowed") from exc
    except safe_et.ParseError as exc:
        raise EbelgeError("bad_xml", source, str(exc)) from exc


def iterparse(stream: IO[bytes], source: str) -> Iterator[tuple[str, Element]]:
    try:
        yield from safe_et.iterparse(stream, events=("start", "end"), forbid_dtd=True)
    except DefusedXmlException as exc:
        raise EbelgeError("unsafe_xml", source, "DTDs and entities are not allowed") from exc
    except safe_et.ParseError as exc:
        raise EbelgeError("bad_xml", source, str(exc)) from exc


def root_tag(data: bytes, source: str) -> str:
    """Qualified tag of the root element, read without parsing the whole document."""
    for event, el in iterparse(io.BytesIO(data), source):
        if event == "start":
            return el.tag
    raise EbelgeError("bad_xml", source, "no root element")


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def text(el: Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    t = el.text.strip()
    return t or None


def parse_decimal(value: str | None, source: str, where: str) -> Decimal | None:
    if value is None:
        return None
    v = value.strip()
    if not _DECIMAL.match(v):
        raise EbelgeError("bad_amount", source, f"{where}: {value!r} is not a plain decimal number")
    try:
        return Decimal(v)
    except InvalidOperation as exc:  # pragma: no cover - the regex already rules this out
        raise EbelgeError("bad_amount", source, where) from exc


def parse_date(value: str | None, source: str, where: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError as exc:
        raise EbelgeError("bad_date", source, f"{where}: {value!r}") from exc
