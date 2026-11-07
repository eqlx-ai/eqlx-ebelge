"""Finding documents in files, folders and ZIP archives, with limits against oversized or hostile archives."""

from __future__ import annotations

import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ._xml import local, root_tag
from .errors import EbelgeError

Kind = Literal["invoice", "ledger", "other", "unreadable"]

_UBL_INVOICE = "{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}Invoice"
_EDEFTER = "{http://www.edefter.gov.tr}defter"
_ENVELOPE = "StandardBusinessDocument"

MB = 1024 * 1024


@dataclass(frozen=True)
class Limits:
    """Ceilings for one run. A ZIP member is refused if it expands more than ``max_ratio`` times."""

    max_file_mb: int = 250
    max_total_mb: int = 4096
    max_ratio: int = 200
    max_files: int = 100_000


@dataclass(frozen=True)
class Document:
    name: str
    kind: Kind
    root: str  # local name of the root element; for "unreadable", the reason
    data: bytes


def classify(data: bytes, name: str) -> tuple[Kind, str]:
    tag = root_tag(data, name)
    if tag == _UBL_INVOICE or local(tag) == _ENVELOPE:
        return "invoice", local(tag)
    if tag == _EDEFTER:
        return "ledger", local(tag)
    return "other", local(tag)


class _Budget:
    def __init__(self, limits: Limits) -> None:
        self.limits = limits
        self.total = 0
        self.files = 0

    def take(self, size: int, name: str) -> None:
        lim = self.limits
        if size > lim.max_file_mb * MB:
            raise EbelgeError("too_large", name, f"over {lim.max_file_mb} MB")
        self.total += size
        self.files += 1
        if self.total > lim.max_total_mb * MB:
            raise EbelgeError("too_large", name, f"run total over {lim.max_total_mb} MB")
        if self.files > lim.max_files:
            raise EbelgeError("too_many_files", name, f"over {lim.max_files} files")


def _from_zip(path: Path, budget: _Budget) -> Iterator[tuple[str, bytes | EbelgeError]]:
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        yield str(path), EbelgeError("bad_zip", str(path), str(exc))
        return
    with zf:
        for info in zf.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".xml"):
                continue
            name = f"{path}!{info.filename}"
            try:
                if info.compress_size and info.file_size / info.compress_size > budget.limits.max_ratio:
                    raise EbelgeError("zip_ratio", name, "compression ratio too high")
                budget.take(info.file_size, name)
                with zf.open(info) as fh:
                    data = fh.read(budget.limits.max_file_mb * MB + 1)
                if len(data) != info.file_size:
                    raise EbelgeError("zip_size", name, "member size does not match its header")
            except EbelgeError as exc:
                yield name, exc
                continue
            yield name, data


def _files(paths: Iterable[str | Path]) -> Iterator[Path]:
    for p in map(Path, paths):
        if p.is_dir():
            yield from sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in (".xml", ".zip"))
        elif p.is_file():
            yield p
        else:
            raise EbelgeError("not_found", str(p))


def iter_documents(paths: Iterable[str | Path], limits: Limits | None = None) -> Iterator[Document]:
    """Every XML document under ``paths`` (files, folders searched recursively, and ``.zip`` archives),
    with its kind. A document that cannot be opened safely comes back with kind ``"unreadable"`` and the
    reason in ``root``, so one bad file never stops the rest."""
    budget = _Budget(limits or Limits())
    for f in _files(paths):
        items: Iterable[tuple[str, bytes | EbelgeError]]
        if f.suffix.lower() == ".zip":
            items = _from_zip(f, budget)
        else:
            try:
                budget.take(f.stat().st_size, str(f))
                items = [(str(f), f.read_bytes())]
            except EbelgeError as exc:
                items = [(str(f), exc)]
        for name, data in items:
            if isinstance(data, EbelgeError):
                yield Document(name, "unreadable", _reason(data), b"")
                continue
            try:
                kind, root = classify(data, name)
            except EbelgeError as exc:
                yield Document(name, "unreadable", _reason(exc), b"")
                continue
            yield Document(name=name, kind=kind, root=root, data=data)


def _reason(exc: EbelgeError) -> str:
    return exc.code + (f": {exc.detail}" if exc.detail else "")
