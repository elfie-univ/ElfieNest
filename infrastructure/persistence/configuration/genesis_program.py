"""Technical integrity of the non-active Genesis source package.

Publication of the source bundle does not activate it for Adoption. Business
payloads stay with the Genesis owner; this inspector checks package integrity.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Literal, Mapping

import yaml
from pydantic import BaseModel, ConfigDict, Field


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _Source(_Record):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class _Member(_Record):
    path: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: Literal["draft", "published"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class _Blocker(_Record):
    id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class _Manifest(_Record):
    package_id: str = Field(min_length=1)
    package_version: str = Field(min_length=1)
    status: Literal["draft", "published"]
    members: list[_Member] = Field(min_length=1)
    publication_blockers: list[_Blocker] = Field(default_factory=list)
    activation_blockers: list[_Blocker] = Field(default_factory=list)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class _Program(_Record):
    version: Literal[1]
    document_kind: Literal["genesis_program"]
    schema_version: Literal[1]
    program_id: str = Field(min_length=1)
    program_version: str = Field(min_length=1)
    status: Literal["draft", "published"]
    sources: dict[str, _Source]
    manifest: _Manifest
    coverage: dict[str, object]
    rules: dict[str, object]


def validate_genesis_program(document: Mapping[str, object], path: Path) -> None:
    """Reject incomplete/tampered packaging without activating Adoption.

    Source paths are provenance only: installed inspection does not need the
    authoring checkout. Members, including display assets, must be self-contained.
    """
    program = _Program.model_validate(document)
    if program.program_version != program.manifest.package_version:
        raise ValueError("Genesis entry and manifest versions differ")
    if program.status != program.manifest.status:
        raise ValueError("Genesis entry and manifest statuses differ")
    paths = [member.path for member in program.manifest.members]
    if paths != sorted(set(paths)):
        raise ValueError("Genesis members must have unique, sorted paths")
    blocker_ids = [blocker.id for blocker in program.manifest.publication_blockers]
    if len(blocker_ids) != len(set(blocker_ids)):
        raise ValueError("Genesis publication blocker IDs must be unique")
    activation_ids = [blocker.id for blocker in program.manifest.activation_blockers]
    if len(activation_ids) != len(set(activation_ids)):
        raise ValueError("Genesis activation blocker IDs must be unique")
    if program.status == "published":
        if blocker_ids:
            raise ValueError(
                "Published Genesis source package has publication blockers"
            )
        if any(member.status != "published" for member in program.manifest.members):
            raise ValueError("Published Genesis source package has draft members")
        coverage = program.coverage
        if coverage.get("status") != "complete":
            raise ValueError("Published Genesis source package lacks source coverage")
        source_coverage = coverage.get("source_coverage")
        if (
            not isinstance(source_coverage, dict)
            or source_coverage.get("status")
            != "complete_for_registered_source_sections"
            or not source_coverage.get("creator_bindings")
            or not source_coverage.get("resident_projection")
        ):
            raise ValueError("Published Genesis source package lacks source bindings")
        conditions = coverage.get("condition_resolution")
        if not isinstance(conditions, dict) or conditions.get("blocked") != 0:
            raise ValueError(
                "Published Genesis source package has unresolved conditions"
            )

    root = path.parent
    for member in program.manifest.members:
        relative = PurePosixPath(member.path)
        if (
            relative.is_absolute()
            or relative.as_posix() != member.path
            or ".." in relative.parts
            or "\\" in member.path
            or ":" in member.path
            or member.path == path.name
        ):
            raise ValueError(f"Unsafe Genesis member path: {member.path}")
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError(f"Symlink in Genesis member: {member.path}")
        if not current.is_file():
            raise ValueError(f"Missing Genesis member: {member.path}")
        if hashlib.sha256(current.read_bytes()).hexdigest() != member.sha256:
            raise ValueError(f"Genesis member digest mismatch: {member.path}")
        if program.status == "published" and current.suffix == ".yaml":
            member_document = yaml.safe_load(current.read_text(encoding="utf-8"))
            if (
                not isinstance(member_document, dict)
                or member_document.get("status") != "published"
            ):
                raise ValueError(
                    f"Genesis published member is not published: {member.path}"
                )

    actual = set()
    for item in root.rglob("*"):
        if item.is_symlink():
            raise ValueError(f"Symlink in Genesis package: {item}")
        if item.is_file() and item != path:
            actual.add(item.relative_to(root).as_posix())
    if actual != set(paths):
        raise ValueError(f"Genesis inventory mismatch: {sorted(actual ^ set(paths))}")

    canonical = dict(document)
    manifest = dict(program.manifest.model_dump())
    manifest.pop("content_sha256")
    canonical["manifest"] = manifest
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if hashlib.sha256(encoded).hexdigest() != program.manifest.content_sha256:
        raise ValueError("Genesis entry content digest mismatch")
