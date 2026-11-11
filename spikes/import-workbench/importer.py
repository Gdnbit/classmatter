"""Bounded synthetic CSV/XLSX -> mapped preview; no database or commit API."""
from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO, StringIO
import posixpath
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile

MAX_BYTES, MAX_ROWS, MAX_COLS = 2_000_000, 2000, 30


@dataclass(frozen=True)
class Cell:
    text: str
    error: str | None = None


@dataclass(frozen=True)
class Table:
    fingerprint: str
    sheet: str
    rows: tuple[tuple[int, tuple[Cell, ...]], ...]


def xml(payload: bytes):
    if len(payload) > MAX_BYTES or b"\x00" in payload:
        raise ValueError("unsafe or oversized XML")
    try:
        text = payload.decode("utf-8-sig")
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            raise ValueError("XML declarations are refused")
        return ET.fromstring(text)
    except (ET.ParseError, UnicodeError) as error:
        raise ValueError("malformed workbook XML") from error


def local(tag):
    return tag.rsplit("}", 1)[-1]


def bounded(rows):
    if len(rows) > MAX_ROWS or any(len(cells) > MAX_COLS for _, cells in rows):
        raise ValueError("table exceeds 2000 rows / 30 columns")
    if any(len(cell.text) > 4000 for _, cells in rows for cell in cells):
        raise ValueError("cell exceeds 4000 characters")
    return tuple(rows)


def load(payload: bytes, kind: str, *, sheet: str | None = None, encoding="utf-8-sig") -> Table:
    if type(payload) is not bytes or not payload or len(payload) > MAX_BYTES:
        raise ValueError("empty or oversized input")
    fingerprint = sha256(payload).hexdigest()
    if kind == "csv":
        if sheet is not None or encoding not in ("utf-8-sig", "gb18030"):
            raise ValueError("unsupported CSV sheet/encoding")
        try:
            text = payload.decode(encoding)
            if "\x00" in text:
                raise ValueError("NUL in CSV")
            reader = csv.reader(StringIO(text, newline=""), strict=True)
            rows, previous = [], 0
            for values in reader:
                rows.append((previous + 1, tuple(Cell(value) for value in values)))
                previous = reader.line_num
                if len(rows) > MAX_ROWS:
                    raise ValueError("too many rows")
        except (UnicodeError, csv.Error) as error:
            raise ValueError("invalid CSV encoding or syntax") from error
        return Table(fingerprint, "CSV", bounded(rows))
    if kind != "xlsx":
        raise ValueError("only CSV and XLSX are supported")
    try:
        archive = ZipFile(BytesIO(payload))
    except BadZipFile as error:
        raise ValueError("invalid XLSX archive") from error
    with archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if (len(entries) > 100 or len(names) != len(set(names))
                or sum(entry.file_size for entry in entries) > 8_000_000):
            raise ValueError("archive limits or duplicate entries")
        for entry in entries:
            if (entry.filename.startswith("/") or "\\" in entry.filename
                    or ".." in entry.filename.split("/") or entry.flag_bits & 1
                    or entry.file_size > MAX_BYTES
                    or entry.file_size > max(entry.compress_size, 1) * 200
                    or "vba" in entry.filename.casefold() or "externallinks" in entry.filename.casefold()):
                raise ValueError("unsafe workbook entry")
        try:
            for name in names:
                if name.endswith(".rels"):
                    if any(node.get("TargetMode") == "External" for node in xml(archive.read(name))):
                        raise ValueError("external relationships are refused")
            workbook = xml(archive.read("xl/workbook.xml"))
            rels = xml(archive.read("xl/_rels/workbook.xml.rels"))
            sheets = [node for node in workbook.iter() if local(node.tag) == "sheet"]
            if not sheets or len({node.get("name") for node in sheets}) != len(sheets):
                raise ValueError("missing or duplicate worksheet names")
            selected = [node for node in sheets if node.get("name") == sheet] if sheet else sheets
            if len(selected) != 1:
                raise ValueError("select one worksheet explicitly")
            selected = selected[0]
            rel_id = selected.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            targets = [node.get("Target", "") for node in rels
                       if node.get("Id") == rel_id and node.get("Type", "").endswith("/worksheet")]
            if len(targets) != 1:
                raise ValueError("invalid worksheet relationship")
            target = targets[0]
            path = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            if not path.startswith("xl/worksheets/") or path not in names:
                raise ValueError("unsafe worksheet target")
            strings = []
            if "xl/sharedStrings.xml" in names:
                strings = ["".join(part.text or "" for part in node.iter() if local(part.tag) == "t")
                           for node in xml(archive.read("xl/sharedStrings.xml"))]
            rows = []
            last_row = 0
            for row in xml(archive.read(path)).iter():
                if local(row.tag) != "row":
                    continue
                number = int(row.get("r", "0"))
                if not last_row < number <= MAX_ROWS:
                    raise ValueError("invalid or excessive row position")
                last_row, cells, last_col = number, [], 0
                for cell in row:
                    if local(cell.tag) != "c":
                        continue
                    coordinate = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", cell.get("r", ""))
                    if coordinate is None or int(coordinate[2]) != number:
                        raise ValueError("invalid cell coordinate")
                    column = 0
                    for char in coordinate[1]:
                        column = column * 26 + ord(char) - 64
                    if not last_col < column <= MAX_COLS:
                        raise ValueError("duplicate or excessive column position")
                    cells.extend(Cell("") for _ in range(column - last_col - 1))
                    last_col = column
                    value = next((node.text or "" for node in cell if local(node.tag) == "v"), "")
                    kind = cell.get("t", "n")
                    error = None
                    if any(local(node.tag) == "f" for node in cell):
                        error = "formula_refused"
                    elif kind == "s":
                        index = int(value)
                        if not 0 <= index < len(strings):
                            raise ValueError("invalid shared string reference")
                        value = strings[index]
                    elif kind == "inlineStr":
                        value = "".join(node.text or "" for node in cell.iter() if local(node.tag) == "t")
                    elif kind not in ("n", "str"):
                        error = "unsupported_cell_type"
                    cells.append(Cell(value, error))
                rows.append((number, tuple(cells)))
            return Table(fingerprint, selected.get("name"), bounded(rows))
        except (KeyError, BadZipFile, RuntimeError, OverflowError, NotImplementedError) as error:
            raise ValueError("incomplete or corrupt workbook") from error


@dataclass(frozen=True)
class SourceRow:
    fingerprint: str
    sheet: str
    row: int
    mapping: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class RosterCandidate:
    student_id: str
    name: str
    source: SourceRow


@dataclass(frozen=True)
class GradeCandidate:
    student_id: str
    exam: str
    subject: str
    state: str
    score: Decimal | None
    source: SourceRow


@dataclass(frozen=True)
class PreviewRow:
    row: int
    action: str
    errors: tuple[str, ...]
    candidate: RosterCandidate | GradeCandidate | None


@dataclass(frozen=True)
class Preview:
    headers: tuple[str, ...]
    rows: tuple[PreviewRow, ...]
    counts: tuple[tuple[str, int], ...]


ALIASES = {"student_id": ("学号", "student_id"), "name": ("姓名", "name"),
           "exam": ("考试", "exam"), "subject": ("科目", "subject"),
           "score": ("成绩", "score")}


def suggest(headers: tuple[str, ...]) -> dict[str, int]:
    normalized = [header.strip().casefold() for header in headers]
    return {field: matches[0] for field, aliases in ALIASES.items()
            if len(matches := [index for index, value in enumerate(normalized) if value in aliases]) == 1}


def preview(table: Table, profile: str, mapping: dict[str, int], *, header_row=1,
            roster: dict[str, str] | None = None,
            grades: dict[tuple[str, str, str], tuple[str, Decimal | None]] | None = None,
            maximum=Decimal("100")) -> Preview:
    roster, grades = dict(roster or {}), dict(grades or {})
    required = {"student_id", "name"} if profile == "roster" else {"student_id", "exam", "subject", "score"}
    if profile not in ("roster", "grades") or set(mapping) != required:
        raise ValueError("mapping must contain exactly the required profile fields")
    header = next((cells for number, cells in table.rows if number == header_row), None)
    if header is None or not any(cell.text.strip() for cell in header) or any(cell.error for cell in header):
        raise ValueError("missing or invalid header")
    if (any(type(index) is not int or not 0 <= index < len(header) for index in mapping.values())
            or len(set(mapping.values())) != len(mapping)):
        raise ValueError("mapping columns must be distinct and in range")
    if type(maximum) is not Decimal or not maximum.is_finite() or maximum <= 0:
        raise ValueError("positive finite maximum required")
    prepared, keys = [], []
    for number, cells in table.rows:
        if number <= header_row:
            continue
        fields = {field: cells[index] if index < len(cells) else Cell("") for field, index in mapping.items()}
        values = {field: cell.text.strip() for field, cell in fields.items()}
        if not any(cell.text.strip() or cell.error for cell in cells):
            prepared.append((number, None, (), "skipped", None))
            continue
        errors = [f"{field}:{cell.error}" for field, cell in fields.items() if cell.error]
        for field, value in values.items():
            if value.startswith(("=", "+", "@")):
                errors.append(f"{field}:formula_refused")
            if not value and field != "score":
                errors.append(f"{field}:required")
        student = values["student_id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", student):
            errors.append("student_id:invalid")
        source = SourceRow(table.fingerprint, table.sheet, number, tuple(sorted(mapping.items())))
        action, candidate = "add", None
        if profile == "roster":
            key = (student,)
            if len(values["name"]) > 80:
                errors.append("name:too_long")
            if not errors:
                candidate = RosterCandidate(student, values["name"], source)
                if student in roster:
                    action = "unchanged" if roster[student] == values["name"] else "update"
        else:
            key = student, values["exam"], values["subject"]
            if student not in roster:
                errors.append("student_id:unmatched")
            if any(len(values[field]) > 80 for field in ("exam", "subject")):
                errors.append("exam_or_subject:too_long")
            raw, score = values["score"], None
            state = {"": "not_entered", "缺考": "absent", "免考": "excused"}.get(raw, "valid")
            if state == "valid":
                try:
                    score = Decimal(raw)
                    if not score.is_finite() or not 0 <= score <= maximum:
                        raise InvalidOperation
                except InvalidOperation:
                    errors.append("score:invalid")
            if not errors:
                candidate = GradeCandidate(student, values["exam"], values["subject"], state, score, source)
                if key in grades:
                    action = "unchanged" if grades[key] == (state, score) else "update"
        if errors:
            action, candidate = "invalid", None
        prepared.append((number, key, tuple(errors), action, candidate))
        keys.append(key)
    duplicate = {key for key, count in Counter(keys).items() if count > 1}
    rows = tuple(PreviewRow(number, "conflict" if key in duplicate else action,
                            errors + (("duplicate_input",) if key in duplicate else ()),
                            None if key in duplicate else candidate)
                 for number, key, errors, action, candidate in prepared)
    counts = Counter(row.action for row in rows)
    return Preview(tuple(cell.text for cell in header), rows,
                   tuple((action, counts[action]) for action in ("add", "update", "unchanged", "skipped", "conflict", "invalid")))
