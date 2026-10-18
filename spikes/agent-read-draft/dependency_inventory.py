from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SBOM = ROOT / "evidence" / "sbom.cdx.json"
OUTPUT = ROOT / "evidence" / "dependency-inventory.json"
LOCKFILE = ROOT / "uv.lock"
ALLOWED = {
    "MIT",
    "Apache-2.0",
    "Apache 2.0",
    "BSD-3-Clause",
    "BSD-2-Clause",
    "ISC",
    "Python-2.0",
    "PSF-2.0",
}


def build() -> bytes:
    sbom = json.loads(SBOM.read_text(encoding="utf-8"))
    packages = []
    marker_excluded = []
    unknown = []
    disallowed = []
    for component in sorted(sbom["components"], key=lambda item: item["name"].lower()):
        name = component["name"]
        try:
            metadata = importlib.metadata.metadata(name)
        except importlib.metadata.PackageNotFoundError:
            marker_excluded.append({"name": name, "version": component["version"]})
            continue
        license_expression = metadata.get("License-Expression") or metadata.get("License") or "UNKNOWN"
        entry = {
            "name": name,
            "version": component["version"],
            "license_expression": license_expression,
            "project_url": metadata.get("Project-URL"),
        }
        packages.append(entry)
        if license_expression == "UNKNOWN":
            unknown.append(name)
        elif license_expression not in ALLOWED:
            disallowed.append({"name": name, "license_expression": license_expression})
    document = {
        "schema": "class-os.dependency-inventory/v1",
        "source": "evidence/sbom.cdx.json",
        "lock_sha256": hashlib.sha256(LOCKFILE.read_bytes()).hexdigest(),
        "packages": packages,
        "marker_excluded_on_target": marker_excluded,
        "unknown_licenses": unknown,
        "not_allowlisted": disallowed,
    }
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = build()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_bytes() != payload:
            raise SystemExit("dependency inventory drift")
    else:
        OUTPUT.write_bytes(payload)
    document = json.loads(payload)
    if document["unknown_licenses"] or document["not_allowlisted"]:
        raise SystemExit("dependency license inventory requires review")
    print(json.dumps({"package_count": len(document["packages"]), "licenses_clear": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
