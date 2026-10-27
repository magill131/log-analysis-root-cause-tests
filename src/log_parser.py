"""Parse application log lines.

Line format (one event per line):

    2026-03-02T14:05:11Z ERROR payment-service request_id=req-00042 error_type=TimeoutError msg="upstream timed out"

That is: an ISO timestamp ending in Z, a level (DEBUG, INFO, WARN or ERROR), a
service name, then key=value fields. Values with spaces are in double quotes.
A malformed line never stops a run: it is skipped and reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")

_TIMESTAMP = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z$")
_LINE = re.compile(r"^(?P<ts>\S+)\s+(?P<level>\S+)\s+(?P<service>\S+)(?P<rest>.*)$")
_FIELD = re.compile(r'\s*(?P<key>\w+)=(?P<value>"(?:[^"\\]|\\.)*"|[^\s"]+)')


class ParseError(ValueError):
    """The line is not a valid log event."""


@dataclass(frozen=True)
class LogEvent:
    timestamp: datetime
    level: str
    service: str
    message: str = ""
    request_id: str | None = None
    error_type: str | None = None
    release: str | None = None
    fields: dict = field(default_factory=dict, compare=False)

    @property
    def is_error(self) -> bool:
        return self.level == "ERROR"


@dataclass(frozen=True)
class Malformed:
    line_number: int
    line: str
    reason: str


@dataclass
class ParseResult:
    events: list[LogEvent]
    malformed: list[Malformed]


def _unquote(value: str) -> str:
    if value.startswith('"'):
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return value


def parse_line(line: str) -> LogEvent:
    text = line.strip()
    if not text:
        raise ParseError("empty line")

    match = _LINE.match(text)
    if not match:
        raise ParseError("expected: timestamp level service [key=value ...]")

    stamp = _TIMESTAMP.match(match["ts"])
    if not stamp:
        raise ParseError(f"bad timestamp '{match['ts']}'")
    try:
        timestamp = datetime(*map(int, stamp.groups()), tzinfo=timezone.utc)
    except ValueError:
        raise ParseError(f"bad timestamp '{match['ts']}'") from None

    level = match["level"]
    if level not in LEVELS:
        raise ParseError(f"unknown level '{level}'")

    fields: dict[str, str] = {}
    rest = match["rest"]
    position = 0
    while True:
        pair = _FIELD.match(rest, position)
        if not pair:
            break
        key = pair["key"]
        if key in fields:
            raise ParseError(f"duplicate field '{key}'")
        fields[key] = _unquote(pair["value"])
        position = pair.end()
    leftover = rest[position:].strip()
    if leftover:
        raise ParseError(f"bad field near '{leftover[:30]}'")

    return LogEvent(
        timestamp=timestamp,
        level=level,
        service=match["service"],
        message=fields.get("msg", ""),
        request_id=fields.get("request_id"),
        error_type=fields.get("error_type"),
        release=fields.get("release"),
        fields=fields,
    )


def parse_lines(lines: Iterable[str]) -> ParseResult:
    """Parse many lines. Blank lines are ignored; bad lines are collected, not fatal."""
    events: list[LogEvent] = []
    malformed: list[Malformed] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            events.append(parse_line(line))
        except ParseError as exc:
            malformed.append(Malformed(number, line.rstrip("\n"), str(exc)))
    return ParseResult(events, malformed)
