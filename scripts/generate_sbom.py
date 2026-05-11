"""Generate an SPDX 2.3 SBOM for the repository and declared dependencies."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = Path("custom_components/inepro_metering/manifest.json")
PROJECT_PATH = Path("pyproject.toml")
REPOSITORY_NAME = "home-assistant-inepro-metering"
REPOSITORY_URL = "https://github.com/ineprometering/home-assistant-inepro-metering"
PYPI_PROJECT_NAME = "inepro-metering"


@dataclass
class Dependency:
    """Dependency declaration plus resolved installed metadata, when available."""

    name: str
    requirements: set[str] = field(default_factory=set)
    scopes: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    installed_version: str | None = None
    exact_declared_version: str | None = None
    license_declared: str | None = None
    homepage: str | None = None
    transitive: bool = False


def run_git(args: list[str], *, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def spdx_id(prefix: str, value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9.-]+", "-", value).strip("-")
    return f"SPDXRef-{prefix}-{safe}"


def requirement_name(requirement: str) -> str:
    requirement = requirement.split(";", 1)[0].strip()
    match = re.match(r"([A-Za-z0-9_.-]+)", requirement)
    if not match:
        raise ValueError(f"Cannot parse dependency name from {requirement!r}")
    return match.group(1)


def exact_version(requirement: str) -> str | None:
    match = re.search(r"==\s*([A-Za-z0-9_.!+*-]+)", requirement)
    if not match or "*" in match.group(1):
        return None
    return match.group(1)


def is_optional_extra_requirement(requirement: str) -> bool:
    if ";" not in requirement:
        return False
    marker = requirement.split(";", 1)[1].lower()
    return "extra ==" in marker or "extra in" in marker


def installed_distributions() -> dict[str, importlib.metadata.Distribution]:
    distributions: dict[str, importlib.metadata.Distribution] = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if name:
            distributions[normalize_name(name)] = distribution
    return distributions


def dependency_metadata(
    dependency: Dependency,
    distributions: dict[str, importlib.metadata.Distribution],
) -> None:
    distribution = distributions.get(normalize_name(dependency.name))
    if distribution is None:
        return
    dependency.installed_version = distribution.version
    dependency.license_declared = distribution.metadata.get("License-Expression")
    dependency.homepage = (
        distribution.metadata.get("Project-URL", "").split(",", 1)[-1].strip()
        or distribution.metadata.get("Home-page")
    )


def read_text_from_ref(path: Path, git_ref: str | None) -> str:
    if git_ref:
        return run_git(["show", f"{git_ref}:{path.as_posix()}"])
    return (ROOT / path).read_text(encoding="utf-8")


def tracked_files(git_ref: str | None) -> list[str]:
    if git_ref:
        output = run_git(["ls-tree", "-r", "--name-only", git_ref])
        return [line for line in output.splitlines() if line]
    output = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    return [entry.decode("utf-8") for entry in output.split(b"\0") if entry]


def file_bytes(path: str, git_ref: str | None) -> bytes:
    if git_ref:
        return subprocess.run(
            ["git", "show", f"{git_ref}:{path}"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
    return (ROOT / path).read_bytes()


def file_entries(git_ref: str | None) -> tuple[list[dict[str, object]], list[str], str]:
    entries: list[dict[str, object]] = []
    file_ids: list[str] = []
    sha1_values: list[str] = []
    for path in sorted(tracked_files(git_ref)):
        digest = hashlib.sha1(file_bytes(path, git_ref)).hexdigest()
        file_id = spdx_id("File", hashlib.sha1(path.encode("utf-8")).hexdigest())
        entries.append(
            {
                "SPDXID": file_id,
                "fileName": f"./{path}",
                "checksums": [{"algorithm": "SHA1", "checksumValue": digest}],
                "licenseConcluded": "NOASSERTION",
                "copyrightText": "NOASSERTION",
            }
        )
        file_ids.append(file_id)
        sha1_values.append(digest)
    verification = hashlib.sha1("".join(sorted(sha1_values)).encode("utf-8")).hexdigest()
    return entries, file_ids, verification


def add_dependency(
    dependencies: dict[str, Dependency],
    requirement: str,
    *,
    scope: str,
    source: str,
    transitive: bool = False,
) -> None:
    name = requirement_name(requirement)
    normalized = normalize_name(name)
    dependency = dependencies.setdefault(normalized, Dependency(name=name))
    dependency.requirements.add(requirement)
    dependency.scopes.add(scope)
    dependency.sources.add(source)
    dependency.transitive = dependency.transitive or transitive
    declared = exact_version(requirement)
    if declared:
        dependency.exact_declared_version = declared


def declared_dependencies(pyproject: dict[str, object], manifest: dict[str, object]) -> dict[str, Dependency]:
    dependencies: dict[str, Dependency] = {}
    project = pyproject["project"]
    for requirement in project.get("dependencies", []):
        add_dependency(
            dependencies,
            requirement,
            scope="runtime",
            source="pyproject.toml project.dependencies",
        )
    for requirement in manifest.get("requirements", []):
        if normalize_name(requirement_name(requirement)) == normalize_name(PYPI_PROJECT_NAME):
            continue
        add_dependency(
            dependencies,
            requirement,
            scope="runtime",
            source="custom_components/inepro_metering/manifest.json requirements",
        )
    optional = project.get("optional-dependencies", {})
    for requirement in optional.get("test", []):
        add_dependency(
            dependencies,
            requirement,
            scope="test",
            source="pyproject.toml project.optional-dependencies.test",
        )
    for requirement in optional.get("build", []):
        add_dependency(
            dependencies,
            requirement,
            scope="build",
            source="pyproject.toml project.optional-dependencies.build",
        )
    for requirement in optional.get("security", []):
        add_dependency(
            dependencies,
            requirement,
            scope="security",
            source="pyproject.toml project.optional-dependencies.security",
        )
    for requirement in pyproject.get("build-system", {}).get("requires", []):
        add_dependency(
            dependencies,
            requirement,
            scope="build",
            source="pyproject.toml build-system.requires",
        )
    return dependencies


def add_transitive_dependencies(
    dependencies: dict[str, Dependency],
    distributions: dict[str, importlib.metadata.Distribution],
) -> None:
    queue = list(dependencies.values())
    seen_edges: set[tuple[str, str]] = set()
    while queue:
        parent = queue.pop(0)
        distribution = distributions.get(normalize_name(parent.name))
        if distribution is None:
            continue
        for requirement in distribution.requires or []:
            if is_optional_extra_requirement(requirement):
                continue
            try:
                child_name = requirement_name(requirement)
            except ValueError:
                continue
            child_key = normalize_name(child_name)
            if child_key not in distributions:
                continue
            edge = (normalize_name(parent.name), child_key)
            if edge in seen_edges:
                continue
            seen_edges.add(edge)
            child = dependencies.get(child_key)
            existing_scopes = set(child.scopes) if child else set()
            for scope in parent.scopes:
                add_dependency(
                    dependencies,
                    requirement,
                    scope=scope,
                    source=f"installed metadata Requires-Dist from {parent.name}",
                    transitive=True,
                )
            child = dependencies[child_key]
            if child.scopes != existing_scopes:
                queue.append(child)


def package_for_dependency(dependency: Dependency, created: str) -> dict[str, object]:
    version = dependency.installed_version or dependency.exact_declared_version
    has_direct_source = any(
        not source.startswith("installed metadata Requires-Dist")
        for source in dependency.sources
    )
    dependency_type = (
        "direct+transitive"
        if dependency.transitive and has_direct_source
        else "transitive"
        if dependency.transitive
        else "direct"
    )
    package: dict[str, object] = {
        "name": dependency.name,
        "SPDXID": spdx_id("Package", normalize_name(dependency.name)),
        "versionInfo": version or "NOASSERTION",
        "downloadLocation": (
            f"https://pypi.org/project/{dependency.name}/{version}/"
            if version
            else "NOASSERTION"
        ),
        "filesAnalyzed": False,
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": dependency.license_declared or "NOASSERTION",
        "copyrightText": "NOASSERTION",
        "externalRefs": [
            {
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": (
                    f"pkg:pypi/{normalize_name(dependency.name)}@{version}"
                    if version
                    else f"pkg:pypi/{normalize_name(dependency.name)}"
                ),
            }
        ],
        "annotations": [
            {
                "annotationType": "OTHER",
                "annotator": "Tool: scripts/generate_sbom.py",
                "annotationDate": created,
                "comment": (
                    f"dependency_scopes={','.join(sorted(dependency.scopes))}; "
                    f"dependency_type={dependency_type}; "
                    f"declared_requirements={'; '.join(sorted(dependency.requirements))}; "
                    f"sources={'; '.join(sorted(dependency.sources))}"
                ),
            }
        ],
    }
    if dependency.homepage:
        package["homepage"] = dependency.homepage
    return package


def relationship_type(scope: str) -> str:
    if scope == "runtime":
        return "RUNTIME_DEPENDENCY_OF"
    if scope == "build":
        return "BUILD_DEPENDENCY_OF"
    if scope == "test":
        return "TEST_DEPENDENCY_OF"
    if scope == "security":
        return "DEV_DEPENDENCY_OF"
    return "DEPENDS_ON"


def git_commit_for_ref(git_ref: str | None) -> str:
    if git_ref:
        return run_git(["rev-parse", git_ref])
    return run_git(["rev-parse", "HEAD"])


def git_dirty() -> bool:
    return bool(run_git(["status", "--porcelain"], check=True))


def creation_time(git_ref: str | None) -> str:
    source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_date_epoch:
        timestamp = int(source_date_epoch)
    elif git_ref:
        timestamp = int(run_git(["show", "-s", "--format=%ct", git_ref]))
    else:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return datetime.fromtimestamp(timestamp, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_sbom(args: argparse.Namespace) -> dict[str, object]:
    pyproject = tomllib.loads(read_text_from_ref(PROJECT_PATH, args.git_ref))
    manifest = json.loads(read_text_from_ref(MANIFEST_PATH, args.git_ref))
    release_version = args.release_version or pyproject["project"]["version"]
    commit = git_commit_for_ref(args.git_ref)
    created = args.created or creation_time(args.git_ref)
    files, file_ids, verification_code = file_entries(args.git_ref)
    distributions = installed_distributions()
    dependencies = declared_dependencies(pyproject, manifest)
    for dependency in dependencies.values():
        dependency_metadata(dependency, distributions)
    if not args.direct_only:
        add_transitive_dependencies(dependencies, distributions)
        for dependency in dependencies.values():
            dependency_metadata(dependency, distributions)

    root_spdx_id = spdx_id("Package", REPOSITORY_NAME)
    root_package = {
        "name": REPOSITORY_NAME,
        "SPDXID": root_spdx_id,
        "versionInfo": release_version,
        "downloadLocation": REPOSITORY_URL,
        "filesAnalyzed": True,
        "packageFileName": f"{REPOSITORY_NAME}-{release_version}",
        "packageVerificationCode": {
            "packageVerificationCodeValue": verification_code,
        },
        "hasFiles": file_ids,
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": pyproject["project"].get("license", "NOASSERTION"),
        "copyrightText": "NOASSERTION",
        "homepage": REPOSITORY_URL,
        "externalRefs": [
            {
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": f"pkg:github/ineprometering/{REPOSITORY_NAME}@{commit}",
            }
        ],
        "annotations": [
            {
                "annotationType": "OTHER",
                "annotator": "Tool: scripts/generate_sbom.py",
                "annotationDate": created,
                "comment": (
                    f"git_commit={commit}; git_ref={args.git_ref or 'working-tree'}; "
                    f"working_tree_dirty={git_dirty() if not args.git_ref else 'not-applicable'}; "
                    f"python_project={pyproject['project']['name']}=={pyproject['project']['version']}; "
                    f"home_assistant_manifest_version={manifest['version']}"
                ),
            }
        ],
    }

    packages = [
        root_package,
        *(
            package_for_dependency(dep, created)
            for dep in sorted(dependencies.values(), key=lambda item: normalize_name(item.name))
        ),
    ]
    relationships: list[dict[str, str]] = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": root_spdx_id,
        }
    ]
    for dependency in sorted(dependencies.values(), key=lambda item: normalize_name(item.name)):
        dep_id = spdx_id("Package", normalize_name(dependency.name))
        for scope in sorted(dependency.scopes):
            relationships.append(
                {
                    "spdxElementId": dep_id,
                    "relationshipType": relationship_type(scope),
                    "relatedSpdxElement": root_spdx_id,
                }
            )
        if "runtime" in dependency.scopes:
            relationships.append(
                {
                    "spdxElementId": root_spdx_id,
                    "relationshipType": "DEPENDS_ON",
                    "relatedSpdxElement": dep_id,
                }
            )

    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"{REPOSITORY_NAME}-{release_version}",
        "documentNamespace": f"{REPOSITORY_URL}/sbom/{release_version}/{commit}",
        "creationInfo": {
            "created": created,
            "creators": [
                "Tool: scripts/generate_sbom.py",
                "Organization: inepro Metering",
            ],
        },
        "packages": packages,
        "files": files,
        "relationships": relationships,
    }


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dist/sbom/inepro-metering.spdx.json"),
        help="Output path for the SPDX JSON document.",
    )
    parser.add_argument(
        "--git-ref",
        help="Git commit, tag, or ref to read. Omit to use the current working tree.",
    )
    parser.add_argument(
        "--release-version",
        help="Release version to place on the repository package. Defaults to pyproject.toml project.version.",
    )
    parser.add_argument(
        "--created",
        help="SPDX creation timestamp, for reproducible regeneration. Example: 2026-05-12T00:00:00Z.",
    )
    parser.add_argument(
        "--direct-only",
        action="store_true",
        help="Only include direct declared dependencies, not installed transitive dependencies.",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    sbom = build_sbom(args)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
