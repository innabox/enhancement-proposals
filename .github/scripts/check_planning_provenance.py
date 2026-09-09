#!/usr/bin/env python3
"""Require provenance metadata for planning documents changed by a pull request.

The workflow runs this trusted base-branch copy against the pull request's
document blobs. It deliberately validates the published machine-readable
contract rather than session-local artifacts, which are not committed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence


# Match every PRD/design path recognized by ep-review.yml.  README.md is the
# legacy design-document convention; filenames vary in case across the library.
CHECKED_FILENAMES = {"prd.md": "prd", "design.md": "design", "readme.md": "design"}
PROVENANCE_KINDS = {"session", "commit_only", "declined"}
PROVENANCE_COMMENT_PREFIX = "<!-- ai-workflow-provenance:"
PROVENANCE_COMMENT_SUFFIX = "-->"


def run_git(args: Sequence[str]) -> bytes:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True
    ).stdout


def changed_document_paths(diff_output: bytes) -> list[str]:
    """Return changed planning-document paths from a NUL diff list."""
    paths = []
    for raw_path in diff_output.split(b"\0"):
        if not raw_path:
            continue
        path = raw_path.decode("utf-8")
        basename = path.rsplit("/", 1)[-1].casefold()
        if path.startswith("enhancements/") and basename in CHECKED_FILENAMES:
            paths.append(path)
    return paths


def provenance_payloads(content: str) -> list[str]:
    """Extract unparsed provenance payloads without accepting malformed comments."""
    payloads = []
    start = 0
    while True:
        prefix_index = content.find(PROVENANCE_COMMENT_PREFIX, start)
        if prefix_index == -1:
            return payloads
        payload_start = prefix_index + len(PROVENANCE_COMMENT_PREFIX)
        payload_end = content.find(PROVENANCE_COMMENT_SUFFIX, payload_start)
        if payload_end == -1:
            return payloads + [""]
        payloads.append(content[payload_start:payload_end].strip())
        start = payload_end + len(PROVENANCE_COMMENT_SUFFIX)


def validate_document(path: str, content: str) -> list[str]:
    """Return contract violations for one changed planning document."""
    expected_workflow = CHECKED_FILENAMES[path.rsplit("/", 1)[-1].casefold()]
    payloads = provenance_payloads(content)
    if not payloads:
        return [f"{path}: missing ai-workflow-provenance comment"]
    if len(payloads) != 1:
        return [f"{path}: expected exactly one ai-workflow-provenance comment"]

    try:
        payload = json.loads(payloads[0])
    except json.JSONDecodeError:
        return [f"{path}: provenance comment does not contain valid JSON"]

    if not isinstance(payload, dict):
        return [f"{path}: provenance comment must contain a JSON object"]
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        return [f"{path}: provenance schema_version must be integer 1"]

    kind = payload.get("provenance_kind")
    if kind not in PROVENANCE_KINDS:
        return [f"{path}: unsupported provenance_kind {kind!r}"]

    if kind == "declined":
        if "## Provenance" in content:
            return [f"{path}: declined provenance must not retain a Provenance footer"]
        return []

    if payload.get("workflow") != expected_workflow:
        return [
            f"{path}: provenance workflow must be {expected_workflow!r}, "
            f"not {payload.get('workflow')!r}"
        ]
    if "## Provenance" not in content:
        return [f"{path}: provenance comment requires a Provenance footer"]
    return []


def validate_changed_documents(base: str, head: str) -> list[str]:
    diff_output = run_git(
        [
            "diff",
            "--name-only",
            "-z",
            "--diff-filter=AMR",
            "--find-renames",
            base,
            head,
            "--",
        ]
    )
    violations = []
    for path in changed_document_paths(diff_output):
        content = run_git(["show", f"{head}:{path}"]).decode("utf-8")
        violations.extend(validate_document(path, content))
    return violations


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="trusted base commit SHA")
    parser.add_argument("--head", required=True, help="fetched pull request head ref")
    args = parser.parse_args(argv)

    try:
        violations = validate_changed_documents(args.base, args.head)
    except (subprocess.CalledProcessError, UnicodeDecodeError) as error:
        print(f"error: unable to inspect pull request documents: {error}", file=sys.stderr)
        return 2

    for violation in violations:
        print(violation, file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
