"""Offline bounded core-package verifier. Does not import/write a database."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
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


def load_package(path, *, require_complete=False):
    # Local operator input only. Do not block on FIFOs or follow a leaf link.
    if path.is_symlink() or path.is_junction():
        raise ValueError("Not a regular local package")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as file:
        details = os.fstat(file.fileno())
        if not stat.S_ISREG(details.st_mode) or details.st_size > 2097152:
            raise ValueError("Not a bounded regular package")
        raw = file.read(2097153)
    if len(raw) > 2097152:
        raise ValueError("Package too large")
    bundle = json.loads(raw, object_pairs_hook=unique,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    counts = validate_package(bundle, require_complete=require_complete)
    return bundle, counts, hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Validate synthetic core exit; no database writes")
    parser.add_argument("path", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--compare-with", type=Path, help="Second local synthetic package; checks integrity, never imports")
    args = parser.parse_args()
    try:
        bundle, counts, file_hash = load_package(args.path, require_complete=args.require_complete)
        comparison = None
        if args.compare_with is not None:
            other, _, other_hash = load_package(args.compare_with, require_complete=args.require_complete)
            comparison = {"same_file_bytes": file_hash == other_hash,
                          "same_package": bundle["package_checksum"] == other["package_checksum"],
                          "same_core": bundle["core_checksum"] == other["core_checksum"]}
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        print("Package rejected: invalid/incomplete synthetic exit. No database was changed.", file=sys.stderr)
        return 1
    print(json.dumps({"valid_synthetic_core": True, "lifecycle_complete": False, "counts": counts,
                      "file_sha256": file_hash, "package_checksum": bundle["package_checksum"],
                      "core_checksum": bundle["core_checksum"], "comparison": comparison,
                      "limitations": "Checksum is integrity only, not source authentication or recovery/retirement proof."}))
    # Formatting-only differences are distinguished, but exact transfer still fails.
    return 0 if comparison is None or all(comparison.values()) else 2


if __name__ == "__main__":
    sys.exit(main())
