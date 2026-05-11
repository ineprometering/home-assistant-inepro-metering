# Security Policy

## Supported Versions

Security fixes are prepared for the current maintained release line of this
custom integration and shared `inepro-metering` package. Older release branches
may receive fixes when a maintainer decides that the affected version is still
used in a supported product or deployment.

Maintainers should record the supported version decision in the release notes or
issue tracker when a security issue is triaged.

## Reporting A Vulnerability

Report suspected vulnerabilities confidentially before opening a public issue.

- Contact: `security@ineprometering.com`
- Include the affected version, installation path, device model or transport if
  relevant, reproduction steps, expected impact, and any known mitigations.
- Do not include live credentials, customer data, or production network details.

## Triage Process

Maintainers should acknowledge receipt, assign an owner, and classify the report
by affected versions, affected component, severity, exploitability, and whether
the issue is in this repository, Home Assistant, a dependency, or device
firmware.

The triage record should link the affected git commit, release tag, dependency
version, and SBOM artifact when those are relevant. If the report is not a
vulnerability, record the reason and close it through the normal issue process.

## Disclosure Workflow

Security fixes should be developed under limited disclosure when public
discussion would create unnecessary risk before users can update. After a fix is
available, publish a release note or advisory-style issue that describes
affected versions, impact, fixed versions, and mitigation or upgrade steps.

Coordinate disclosure timing with affected upstream projects when the root cause
is in Home Assistant, a Python dependency, or firmware outside this repository.

## Dependency Vulnerability Review

Dependency vulnerability review uses:

- `pyproject.toml` for package runtime, test, build, and security tooling
  declarations.
- `custom_components/inepro_metering/manifest.json` for Home Assistant runtime
  requirements.
- `python -m pip_audit . --progress-spinner off` for Python dependency
  vulnerability checks.
- `python scripts/generate_sbom.py --output dist/sbom/<release>.spdx.json` for
  SBOM evidence tied to a release, tag, and commit.

When a dependency finding appears, maintainers should determine whether the
vulnerable package is used at runtime, test time, build time, or only through
optional Home Assistant behavior. Record the decision, chosen mitigation, and any
temporary accepted risk in the issue tracker or release checklist.

## Security Releases

Security fixes should use the normal version bump process documented in
`docs/packaging.md`. Release notes should identify the fixed version and the git
tag or commit that produced the release SBOM. Do not claim regulatory compliance
from the presence of a fix, scan, or SBOM alone.
