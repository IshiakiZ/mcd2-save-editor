"""Encoding of Minecraft Dungeons II save blobs.

Blobs are compact JSON in one of two flavours:

* Settings (``GlobalSaveDataDefault``): every byte is stored minus one, so
  ``{"blobs"`` is written to disk as ``z!aknar!``. Numbers are printed like C's
  ``%.17g`` (0.35 becomes ``0.34999999999999998``) and the top-level key has a
  space before its colon (``{"blobs" :[...``).
* Heroes (``Character<id>``): plain JSON with numbers in their shortest form
  (``0.218016``, ``845.5``, whole numbers without ``.0``).

``decode_blob`` detects the flavour and ``dumps`` reproduces it exactly, so
re-saving an unedited blob gives back the original bytes.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, replace
from typing import Any

_DECODE_TABLE = bytes((i + 1) & 0xFF for i in range(256))
_ENCODE_TABLE = bytes((i - 1) & 0xFF for i in range(256))

_TOP_LEVEL_COLON = re.compile(r'\s*\{\s*"(?:[^"\\]|\\.)*"(\s*:\s*)')
_FLOAT_LITERAL = re.compile(r"(?<=[:,\[])-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?(?=[,\]}])")

NUMBER_FORMATS = ("g17", "shortest")


class _Literal(float):
    """A decimal number that remembers the text it was read from.

    The game doesn't print every number the same way (one hero save has ``4100.0001169648413`` where the shortest
    form is ``4100.000116964841``). Both are the same number, but writing a number back exactly as it was read
    keeps an unedited save byte for byte identical. Any number the editor sets is a plain float and is written
    in the style's usual form.
    """

    literal: str | None

    def __new__(cls, value: float, literal: str | None = None):
        number = super().__new__(cls, value)
        number.literal = literal
        return number

    def __reduce__(self):  # copy.deepcopy and pickle
        return (_Literal, (float(self), self.literal))


class NotASaveDocument(ValueError):
    """The blob is not JSON, shifted or plain (it may be encrypted or binary)."""


@dataclass(frozen=True)
class JsonStyle:
    top_level_colon: str = ":"
    ensure_ascii: bool = True
    shifted: bool = True  # bytes stored minus one
    numbers: str = "g17"  # "g17" or "shortest"


@dataclass
class DecodedBlob:
    document: Any
    style: JsonStyle
    exact: bool  # dumps(document, style) reproduces the stored text byte for byte


def decode_bytes(raw: bytes) -> bytes:
    return raw.translate(_DECODE_TABLE)


def encode_bytes(plain: bytes) -> bytes:
    return plain.translate(_ENCODE_TABLE)


def format_number(value: float, numbers: str = "g17") -> str:
    if not math.isfinite(value):
        raise ValueError("saves cannot store NaN or infinity")
    if numbers == "shortest":
        return str(int(value)) if value.is_integer() and abs(value) < 1e16 else repr(value)
    return "%.17g" % value


def dumps(value: Any, style: JsonStyle = JsonStyle()) -> str:
    parts: list[str] = []
    _dump(value, parts, style, style.top_level_colon)
    return "".join(parts)


def _dump(value: Any, parts: list[str], style: JsonStyle, colon: str) -> None:
    if value is None:
        parts.append("null")
    elif value is True:
        parts.append("true")
    elif value is False:
        parts.append("false")
    elif isinstance(value, int):
        parts.append(str(value))
    elif isinstance(value, float):
        literal = getattr(value, "literal", None)
        parts.append(literal if literal is not None else format_number(value, style.numbers))
    elif isinstance(value, str):
        parts.append(json.dumps(value, ensure_ascii=style.ensure_ascii))
    elif isinstance(value, list):
        parts.append("[")
        for position, item in enumerate(value):
            if position:
                parts.append(",")
            _dump(item, parts, style, ":")
        parts.append("]")
    elif isinstance(value, dict):
        parts.append("{")
        for position, (key, item) in enumerate(value.items()):
            if position:
                parts.append(",")
            parts.append(json.dumps(str(key), ensure_ascii=style.ensure_ascii))
            parts.append(colon)
            _dump(item, parts, style, ":")
        parts.append("}")
    else:
        raise TypeError(f"cannot store a {type(value).__name__} in a save")


def detect_style(text: str, document: Any = None, shifted: bool = True) -> JsonStyle:
    """Work out how ``text`` was written so ``dumps`` can write it the same way."""
    match = _TOP_LEVEL_COLON.match(text)
    style = JsonStyle(top_level_colon=match.group(1) if match else ":", ensure_ascii=text.isascii(), shifted=shifted)
    if document is None:
        return style
    # Settings files use %.17g and hero files the shortest form; try the usual one first.
    candidates = NUMBER_FORMATS if shifted else tuple(reversed(NUMBER_FORMATS))
    for numbers in candidates:
        if _dumps_or_none(document, replace(style, numbers=numbers)) == text:
            return replace(style, numbers=numbers)
    # Not an exact match anyway, so follow whichever form most number literals use.
    literals = [literal for literal in _FLOAT_LITERAL.findall(text) if not literal.lstrip("-").isdigit()]
    votes = {numbers: sum(format_number(float(literal), numbers) == literal for literal in literals) for numbers in candidates}
    return replace(style, numbers=max(candidates, key=lambda numbers: votes[numbers]))


def _dumps_or_none(document: Any, style: JsonStyle) -> str | None:
    try:
        return dumps(document, style)
    except ValueError:
        return None


def decode_blob(raw: bytes) -> DecodedBlob:
    for shifted in (True, False):
        try:
            text = (decode_bytes(raw) if shifted else raw).decode("utf-8")
        except UnicodeDecodeError:
            continue
        if not text.lstrip().startswith(("{", "[")):
            continue
        try:
            document = json.loads(text, parse_float=lambda literal: _Literal(float(literal), literal))
        except json.JSONDecodeError:
            continue
        style = detect_style(text, document, shifted)
        return DecodedBlob(document=document, style=style, exact=_dumps_or_none(document, style) == text)
    raise NotASaveDocument("not JSON, shifted or plain")


def encode_blob(document: Any, style: JsonStyle) -> bytes:
    text = dumps(document, style).encode("utf-8")
    return encode_bytes(text) if style.shifted else text
