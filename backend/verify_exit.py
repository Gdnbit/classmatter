"""Offline bounded core-package verifier. Does not import/write a database."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from class_os.domain.exit_package import validate_package


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate package field")
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description="Validate synthetic core exit; no database writes")
    parser.add_argument("path", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    try:
        with args.path.open("rb") as file:
            raw = file.read(2097153)
        if len(raw) > 2097152:
            raise ValueError("Package too large")
        bundle = json.loads(raw, object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        counts = validate_package(bundle, require_complete=args.require_complete)
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        print("Package rejected: invalid/incomplete synthetic exit. No database was changed.", file=sys.stderr)
        return 1
    print(json.dumps({"valid_synthetic_core": True, "lifecycle_complete": False, "counts": counts,
                      "limitations": "Checksum is integrity only, not source authentication or recovery/retirement proof."}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
