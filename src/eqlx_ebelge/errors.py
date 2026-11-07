"""Errors and findings."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

Severity = Literal["error", "warning", "info"]


class EbelgeError(Exception):
    """A document that cannot be read at all (unsafe, malformed, or not the expected format)."""

    def __init__(self, code: str, source: str, detail: str = "") -> None:
        self.code = code
        self.source = source
        self.detail = detail
        super().__init__(f"{source}: {code}" + (f" ({detail})" if detail else ""))


@dataclass(frozen=True)
class Finding:
    """One result of a consistency check.

    ``error``: the document contradicts itself (totals do not add up, an identifier fails its check digit).
    ``warning``: worth a look, may be legitimate (a possible duplicate, a rounding gap on one line).
    ``info``: context, not a problem by itself.
    """

    code: str
    severity: Severity
    message: str
    source: str
    where: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
