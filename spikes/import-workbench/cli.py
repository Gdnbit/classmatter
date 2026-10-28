"""Read a synthetic file and emit a typed, review-only preview as JSON."""
import argparse
from dataclasses import asdict
from decimal import Decimal
import json
from pathlib import Path

from importer import MAX_BYTES, load, preview, suggest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--profile", choices=("roster", "grades"), required=True)
    parser.add_argument("--sheet")
    parser.add_argument("--encoding", choices=("utf-8-sig", "gb18030"), default="utf-8-sig")
    parser.add_argument("--header-row", type=int, default=1)
    parser.add_argument("--mapping", help='JSON column indices, e.g. {"student_id":0,"name":1}')
    parser.add_argument("--roster", default="{}", help="JSON synthetic ID/name map")
    args = parser.parse_args()
    try:
        if args.file.stat().st_size > MAX_BYTES:
            raise ValueError("file exceeds limit")
        table = load(args.file.read_bytes(), args.file.suffix.lstrip(".").lower(),
                     sheet=args.sheet, encoding=args.encoding)
        header = next((cells for row, cells in table.rows if row == args.header_row), ())
        required = {"student_id", "name"} if args.profile == "roster" else {"student_id", "exam", "subject", "score"}
        mapping = json.loads(args.mapping) if args.mapping else {
            key: value for key, value in suggest(tuple(cell.text for cell in header)).items() if key in required}
        roster = json.loads(args.roster)
        if (type(mapping) is not dict or type(roster) is not dict
                or any(type(key) is not str or type(value) is not str for key, value in roster.items())):
            raise ValueError("invalid mapping or roster object")
        result = preview(table, args.profile, mapping, header_row=args.header_row, roster=roster)
        print(json.dumps(asdict(result), ensure_ascii=False, default=lambda value: str(value) if isinstance(value, Decimal) else value))
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
