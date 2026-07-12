#!/usr/bin/env python3
"""Create and audit OSF resources for the SAE/J-lens v2 preregistration."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.exp2_sae.sae_jlens_v2_protocol import (  # noqa: E402
    sha256_file,
    write_json,
)


API_ROOT = "https://api.osf.io/v2"
PROJECT_TITLE = "SAE-Jacobian Lens V2: Hard Negatives and Reader Capacity"
PROJECT_DESCRIPTION = (
    "Preregistration materials and release host for a result-blind follow-up "
    "to the public Llama 3.3 70B SAE-through-Jacobian-lens audit. The study "
    "tests semantic hard negatives, same-subfamily comparators, replay "
    "equivalence, and prospectively frozen linear reader capacity."
)
PROJECT_TAGS = [
    "sparse autoencoder",
    "jacobian lens",
    "mechanistic interpretability",
    "preregistration",
    "llama 3.3 70b",
]


class OSFError(RuntimeError):
    """OSF API request or round-trip validation failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def token_from_environment() -> str:
    token = os.environ.get("OSF_TOKEN")
    if not token:
        raise OSFError("OSF_TOKEN must be present in the process environment")
    return token


def request_json(
    method: str,
    path_or_url: str,
    *,
    payload: dict[str, Any] | None = None,
    expected: tuple[int, ...] = (200,),
) -> dict[str, Any]:
    url = (
        path_or_url
        if path_or_url.startswith("https://")
        else f"{API_ROOT}{path_or_url}"
    )
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token_from_environment()}",
        "Accept": "application/vnd.api+json",
    }
    if data is not None:
        headers["Content-Type"] = "application/vnd.api+json"
    request = urllib.request.Request(
        url, data=data, headers=headers, method=method.upper()
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status = int(response.status)
            raw = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise OSFError(f"OSF {method} failed with HTTP {error.code}: {detail}") from error
    if status not in expected:
        raise OSFError(f"OSF {method} returned unexpected HTTP {status}")
    return {} if not raw else json.loads(raw)


def exact_project_matches() -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"filter[title]": PROJECT_TITLE, "page[size]": 100})
    payload = request_json("GET", f"/nodes/?{query}")
    return [
        row
        for row in payload.get("data", [])
        if row.get("attributes", {}).get("title") == PROJECT_TITLE
        and "admin" in row.get("attributes", {}).get("current_user_permissions", [])
    ]


def create_or_reuse_project() -> tuple[dict[str, Any], bool]:
    matches = exact_project_matches()
    if len(matches) > 1:
        raise OSFError(
            f"Found {len(matches)} exact writable OSF projects; refusing ambiguity"
        )
    if matches:
        return matches[0], False
    payload = {
        "data": {
            "type": "nodes",
            "attributes": {
                "title": PROJECT_TITLE,
                "category": "project",
                "description": PROJECT_DESCRIPTION,
                "public": False,
                "tags": PROJECT_TAGS,
            },
        }
    }
    created = request_json("POST", "/nodes/", payload=payload, expected=(201,))
    return created["data"], True


def sanitized_project_record(data: dict[str, Any]) -> dict[str, Any]:
    attributes = data.get("attributes", {})
    links = data.get("links", {})
    project_id = str(data["id"])
    return {
        "schema_version": 1,
        "id": project_id,
        "title": attributes.get("title"),
        "description_sha256": __import__("hashlib")
        .sha256(str(attributes.get("description", "")).encode("utf-8"))
        .hexdigest(),
        "public": bool(attributes.get("public")),
        "category": attributes.get("category"),
        "tags": sorted(str(value) for value in attributes.get("tags", [])),
        "current_user_permissions": sorted(
            str(value) for value in attributes.get("current_user_permissions", [])
        ),
        "created_at_utc": attributes.get("date_created"),
        "modified_at_utc": attributes.get("date_modified"),
        "captured_at_utc": utc_now(),
        "api_url": links.get("self") or f"{API_ROOT}/nodes/{project_id}/",
        "html_url": links.get("html") or f"https://osf.io/{project_id}/",
        "source": "osf_api_v2",
    }


def audit_project(record_path: Path) -> dict[str, Any]:
    expected = json.loads(record_path.read_text(encoding="utf-8"))
    project_id = str(expected["id"])
    payload = request_json("GET", f"/nodes/{project_id}/")
    observed = sanitized_project_record(payload["data"])
    errors = []
    for key in (
        "id",
        "title",
        "description_sha256",
        "public",
        "category",
        "tags",
        "api_url",
        "html_url",
    ):
        if observed.get(key) != expected.get(key):
            errors.append(f"project field differs: {key}")
    if "admin" not in observed["current_user_permissions"]:
        errors.append("current token lacks OSF project admin permission")
    return {
        "status": "pass" if not errors else "fail",
        "captured_at_utc": utc_now(),
        "project_id": project_id,
        "project_record_sha256": sha256_file(record_path),
        "public": observed["public"],
        "n_errors": len(errors),
        "errors": errors,
    }


def cmd_project(args: argparse.Namespace) -> None:
    data, created = create_or_reuse_project()
    record = sanitized_project_record(data)
    if record["title"] != PROJECT_TITLE:
        raise OSFError("OSF project title failed round-trip validation")
    if record["public"]:
        raise OSFError("New v2 OSF project must remain private before registration")
    write_json(args.out.resolve(), record)
    audit = audit_project(args.out.resolve())
    if audit["status"] != "pass":
        raise OSFError(f"OSF project audit failed: {audit['errors']}")
    print(
        json.dumps(
            {
                "status": "pass",
                "created": created,
                "project_id": record["id"],
                "html_url": record["html_url"],
                "record": str(args.out.resolve()),
            },
            sort_keys=True,
        )
    )


def cmd_audit_project(args: argparse.Namespace) -> None:
    result = audit_project(args.record.resolve())
    if args.out:
        write_json(args.out.resolve(), result)
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "pass":
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    project = subparsers.add_parser(
        "project", help="Idempotently create or reuse the exact private project"
    )
    project.add_argument("--out", type=Path, required=True)
    project.set_defaults(func=cmd_project)
    audit = subparsers.add_parser("audit-project", help="Audit a saved project record")
    audit.add_argument("--record", type=Path, required=True)
    audit.add_argument("--out", type=Path)
    audit.set_defaults(func=cmd_audit_project)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
