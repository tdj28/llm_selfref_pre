#!/usr/bin/env python3
"""Create and audit OSF resources for the SAE/J-lens v2 preregistration."""

from __future__ import annotations

import argparse
import hashlib
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
OPEN_ENDED_SCHEMA_ID = "5df83f7dd28338001ac0ab0d"
OPEN_ENDED_SCHEMA_NAME = "Open-Ended Registration"


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
        "description_sha256": hashlib.sha256(
            str(attributes.get("description", "")).encode("utf-8")
        ).hexdigest(),
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


def storage_root(project_id: str) -> dict[str, Any]:
    payload = request_json("GET", f"/nodes/{project_id}/files/")
    matches = [
        row
        for row in payload.get("data", [])
        if row.get("attributes", {}).get("name") == "osfstorage"
    ]
    if len(matches) != 1:
        raise OSFError(f"Expected one OSF Storage provider, found {len(matches)}")
    return matches[0]


def list_files(url: str) -> list[dict[str, Any]]:
    payload = request_json("GET", url)
    rows = list(payload.get("data", []))
    next_url = payload.get("links", {}).get("next")
    while next_url:
        payload = request_json("GET", next_url)
        rows.extend(payload.get("data", []))
        next_url = payload.get("links", {}).get("next")
    return rows


def waterbutler_json(
    method: str,
    url: str,
    *,
    data: bytes = b"",
    expected: tuple[int, ...] = (200, 201),
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=data,
        method=method.upper(),
        headers={
            "Authorization": f"Bearer {token_from_environment()}",
            "Accept": "application/json",
            "Content-Type": "application/octet-stream",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            status = int(response.status)
            raw = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise OSFError(
            f"OSF Storage {method} failed with HTTP {error.code}: {detail}"
        ) from error
    if status not in expected:
        raise OSFError(f"OSF Storage {method} returned unexpected HTTP {status}")
    return {} if not raw else json.loads(raw)


def with_query(url: str, **values: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    query.update(values)
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), parsed.fragment)
    )


def ensure_folder(project_id: str, name: str) -> dict[str, Any]:
    root = storage_root(project_id)
    root_children_url = f"{API_ROOT}/nodes/{project_id}/files/osfstorage/"
    matches = [
        row
        for row in list_files(root_children_url)
        if row.get("attributes", {}).get("name") == name
    ]
    if len(matches) > 1:
        raise OSFError(f"OSF Storage has duplicate folders named {name!r}")
    if matches:
        if matches[0].get("attributes", {}).get("kind") != "folder":
            raise OSFError(f"OSF Storage name is not a folder: {name!r}")
        return matches[0]
    url = with_query(root["links"]["new_folder"], name=name, kind="folder")
    payload = waterbutler_json("PUT", url)
    row = payload.get("data", payload)
    if row.get("attributes", {}).get("name") != name:
        raise OSFError("OSF folder name failed round-trip creation")
    return row


def folder_children_url(project_id: str, folder: dict[str, Any]) -> str:
    related = (
        folder.get("relationships", {})
        .get("files", {})
        .get("links", {})
        .get("related", {})
        .get("href")
    )
    if related:
        return str(related)
    folder_id = str(folder["id"]).split("/")[-2 if str(folder["id"]).endswith("/") else -1]
    return f"{API_ROOT}/nodes/{project_id}/files/osfstorage/{folder_id}/"


def remote_sha256(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token_from_environment()}"},
    )
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=600) as response:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_upload_record(
    project_id: str,
    folder_name: str,
    base_dir: Path,
    path: Path,
    remote: dict[str, Any],
) -> dict[str, Any]:
    attributes = remote.get("attributes", {})
    links = remote.get("links", {})
    download_url = links.get("download")
    if not download_url:
        raise OSFError(f"Uploaded OSF file lacks a download URL: {path.name}")
    local_hash = sha256_file(path)
    observed_size = attributes.get("size")
    if observed_size is not None and int(observed_size) != path.stat().st_size:
        raise OSFError(f"Uploaded OSF file byte count differs: {path.name}")
    downloaded_hash = remote_sha256(str(download_url))
    if downloaded_hash != local_hash:
        raise OSFError(f"Downloaded OSF file hash differs: {path.name}")
    return {
        "local_path": path.relative_to(base_dir).as_posix(),
        "folder": folder_name,
        "name": path.name,
        "bytes": path.stat().st_size,
        "sha256": local_hash,
        "downloaded_sha256": downloaded_hash,
        "file_id": remote.get("id"),
        "info_url": links.get("info") or links.get("self"),
        "download_url": download_url,
    }


def upload_files(
    project_record_path: Path,
    base_dir: Path,
    paths: list[Path],
    folder_name: str,
) -> dict[str, Any]:
    project = json.loads(project_record_path.read_text(encoding="utf-8"))
    project_id = str(project["id"])
    folder = ensure_folder(project_id, folder_name)
    child_url = folder_children_url(project_id, folder)
    existing = {
        row.get("attributes", {}).get("name"): row for row in list_files(child_url)
    }
    records = []
    for path in paths:
        resolved = path.resolve()
        if not resolved.is_file() or not resolved.is_relative_to(base_dir):
            raise OSFError(f"Upload path is not a file below base directory: {path}")
        remote = existing.get(resolved.name)
        if remote is None:
            upload_url = with_query(
                folder["links"]["upload"], name=resolved.name, kind="file"
            )
            payload = waterbutler_json("PUT", upload_url, data=resolved.read_bytes())
            remote = payload.get("data", payload)
        records.append(
            file_upload_record(
                project_id, folder_name, base_dir, resolved, remote
            )
        )
    return {
        "status": "verified_complete",
        "captured_at_utc": utc_now(),
        "project_id": project_id,
        "project_record_sha256": sha256_file(project_record_path),
        "folder": folder_name,
        "files": records,
    }


def cmd_upload(args: argparse.Namespace) -> None:
    base_dir = args.base_dir.resolve()
    paths = [(base_dir / value).resolve() for value in args.file]
    result = upload_files(
        args.project_record.resolve(), base_dir, paths, args.folder
    )
    write_json(args.out.resolve(), result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "project_id": result["project_id"],
                "folder": result["folder"],
                "files": len(result["files"]),
                "manifest": str(args.out.resolve()),
            },
            sort_keys=True,
        )
    )


def draft_matches(project_id: str) -> list[dict[str, Any]]:
    payload = request_json("GET", f"/nodes/{project_id}/draft_registrations/")
    return [
        row
        for row in payload.get("data", [])
        if row.get("attributes", {}).get("title") == PROJECT_TITLE
    ]


def prepare_draft(project_id: str, summary: str) -> tuple[dict[str, Any], bool]:
    matches = draft_matches(project_id)
    if len(matches) > 1:
        raise OSFError("Multiple exact v2 draft registrations exist")
    created = False
    if matches:
        draft = matches[0]
    else:
        payload = {
            "data": {
                "type": "draft_registrations",
                "relationships": {
                    "registration_schema": {
                        "data": {
                            "id": OPEN_ENDED_SCHEMA_ID,
                            "type": "registration_schemas",
                        }
                    }
                },
            }
        }
        response = request_json(
            "POST",
            f"/nodes/{project_id}/draft_registrations/",
            payload=payload,
            expected=(201,),
        )
        draft = response["data"]
        created = True
    draft_id = str(draft["id"])
    update = {
        "data": {
            "id": draft_id,
            "type": "draft_registrations",
            "attributes": {
                "title": PROJECT_TITLE,
                "description": PROJECT_DESCRIPTION,
                "category": "project",
                "tags": PROJECT_TAGS,
                "registration_responses": {"summary": summary},
            },
        }
    }
    response = request_json(
        "PATCH", f"/draft_registrations/{draft_id}/", payload=update
    )
    return response["data"], created


def sanitized_draft_record(
    project_id: str, data: dict[str, Any], summary: str
) -> dict[str, Any]:
    attributes = data.get("attributes", {})
    relationships = data.get("relationships", {})
    schema_data = relationships.get("registration_schema", {}).get("data", {})
    return {
        "schema_version": 1,
        "id": str(data["id"]),
        "project_id": project_id,
        "title": attributes.get("title"),
        "registration_schema_id": schema_data.get("id") or OPEN_ENDED_SCHEMA_ID,
        "registration_schema_name": OPEN_ENDED_SCHEMA_NAME,
        "summary_sha256": hashlib.sha256(summary.encode("utf-8")).hexdigest(),
        "datetime_initiated": attributes.get("datetime_initiated"),
        "datetime_updated": attributes.get("datetime_updated"),
        "html_url": data.get("links", {}).get("html"),
        "captured_at_utc": utc_now(),
        "state": "editable_draft_not_registered",
    }


def audit_draft(record_path: Path, summary_path: Path) -> dict[str, Any]:
    record = json.loads(record_path.read_text(encoding="utf-8"))
    summary = summary_path.read_text(encoding="utf-8")
    payload = request_json("GET", f"/draft_registrations/{record['id']}/")
    data = payload["data"]
    observed_summary = data.get("attributes", {}).get(
        "registration_responses", {}
    ).get("summary")
    errors = []
    if data.get("attributes", {}).get("title") != PROJECT_TITLE:
        errors.append("draft title differs")
    if observed_summary != summary:
        errors.append("draft summary differs")
    if record.get("summary_sha256") != hashlib.sha256(summary.encode("utf-8")).hexdigest():
        errors.append("saved draft record summary hash differs")
    return {
        "status": "pass" if not errors else "fail",
        "captured_at_utc": utc_now(),
        "draft_id": record["id"],
        "project_id": record["project_id"],
        "record_sha256": sha256_file(record_path),
        "summary_sha256": hashlib.sha256(summary.encode("utf-8")).hexdigest(),
        "state": "editable_draft_not_registered",
        "n_errors": len(errors),
        "errors": errors,
    }


def cmd_draft(args: argparse.Namespace) -> None:
    project = json.loads(args.project_record.read_text(encoding="utf-8"))
    summary = args.summary.read_text(encoding="utf-8")
    data, created = prepare_draft(str(project["id"]), summary)
    record = sanitized_draft_record(str(project["id"]), data, summary)
    write_json(args.out.resolve(), record)
    audit = audit_draft(args.out.resolve(), args.summary.resolve())
    if audit["status"] != "pass":
        raise OSFError(f"OSF draft audit failed: {audit['errors']}")
    print(
        json.dumps(
            {
                "status": "pass",
                "created": created,
                "draft_id": record["id"],
                "html_url": record["html_url"],
                "state": record["state"],
                "record": str(args.out.resolve()),
            },
            sort_keys=True,
        )
    )


def cmd_audit_draft(args: argparse.Namespace) -> None:
    result = audit_draft(args.record.resolve(), args.summary.resolve())
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
    upload = subparsers.add_parser(
        "upload", help="Upload and download-hash-verify files in a private folder"
    )
    upload.add_argument("--project-record", type=Path, required=True)
    upload.add_argument("--base-dir", type=Path, required=True)
    upload.add_argument("--folder", required=True)
    upload.add_argument("--file", action="append", required=True)
    upload.add_argument("--out", type=Path, required=True)
    upload.set_defaults(func=cmd_upload)
    draft = subparsers.add_parser(
        "draft", help="Create or update an editable Open-Ended Registration draft"
    )
    draft.add_argument("--project-record", type=Path, required=True)
    draft.add_argument("--summary", type=Path, required=True)
    draft.add_argument("--out", type=Path, required=True)
    draft.set_defaults(func=cmd_draft)
    audit_draft_parser = subparsers.add_parser(
        "audit-draft", help="Round-trip audit an editable registration draft"
    )
    audit_draft_parser.add_argument("--record", type=Path, required=True)
    audit_draft_parser.add_argument("--summary", type=Path, required=True)
    audit_draft_parser.add_argument("--out", type=Path)
    audit_draft_parser.set_defaults(func=cmd_audit_draft)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
