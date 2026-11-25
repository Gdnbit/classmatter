"""Preview a synthetic UTF-8 text file; --review asks for explicit per-draft input."""
import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

from capture import Capture, Person, Roster, Scope, Source, SyntheticSources


def read_file(path):
    if path.suffix.lower() != ".txt" or path.stat().st_size > 200_000:
        raise ValueError("only bounded synthetic UTF-8 .txt files are accepted")
    payload = path.read_bytes()
    return payload.decode("utf-8-sig"), sha256(payload).hexdigest()


def unique_pairs(entries):
    result = {}
    for key, value in entries:
        if key in result:
            raise ValueError("duplicate roster ID")
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--roster", required=True, help="JSON object of synthetic ID/name pairs")
    parser.add_argument("--review", action="store_true", help="prompt for one human decision per draft")
    args = parser.parse_args()
    try:
        names = json.loads(args.roster, object_pairs_hook=unique_pairs)
        if type(names) is not dict:
            raise ValueError("roster must be a JSON object")
        scope = Scope("synthetic", "class-a", "term-a", "fake-owner")
        roster = Roster(scope, 1, tuple(Person(key, value) for key, value in names.items()))
        text, raw_hash = read_file(args.file)
        now = datetime.now(timezone.utc)
        source = Source(scope, "synthetic-input", 1, text, now + timedelta(hours=1))
        sources = SyntheticSources(); sources.publish(source)
        capture = Capture(sources, roster)
        preview = capture.preview(scope, source.source_id, now)
        print(json.dumps(asdict(preview), ensure_ascii=False), flush=True)
        if args.review:
            for draft in preview.drafts:
                print(f"{draft.kind}: {draft.text}\n候选ID: {', '.join(draft.candidate_ids) or '无'}；输入一个ID确认候选，r拒绝，q退出：", file=sys.stderr, flush=True)
                choice = sys.stdin.readline().strip()
                if choice in ("", "q"):
                    break
                _, current_hash = read_file(args.file)
                if current_hash != raw_hash:
                    raise ValueError("file changed during human review; recapture required")
                reviewed = capture.review(scope, draft, decision="reject" if choice == "r" else "accept",
                                          selected=None if choice == "r" else choice,
                                          reviewer="synthetic-human", now=datetime.now(timezone.utc))
                print(json.dumps(asdict(reviewed), ensure_ascii=False, default=str), flush=True)
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
