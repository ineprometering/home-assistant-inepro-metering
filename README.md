# inepro Metering

`inepro Metering` connects supported inepro energy meters to Home Assistant and
provides a reusable Python protocol library published as `inepro-metering`.

The Home Assistant integration domain is `inepro_metering`. The Python import
package is `inepro_metering`.

## Installation status

This repository contains the public release source for the custom Home
Assistant integration and the reusable Python package.

The integration manifest pins:

```text
inepro-metering==0.1.2
```

Install the Python package directly with:

```bash
pip install inepro-metering==0.1.2
```

## Release validation

The public package release workflow validates the reusable
`src/inepro_metering` library with
`python -m pytest --confcutdir=tests/library tests/library`, audits the runtime
dependencies, generates an SPDX SBOM, builds the wheel and source distribution,
and verifies a clean wheel install.

Home Assistant integration tests are validated in the matching Home Assistant
Core PR branch, where the copied integration code runs against the current Core
test harness.

## High-level capabilities

- Modbus TCP setup for supported meters.
- Modbus RTU setup for supported serial buses.
- GROW mDNS discovery.
- Ambition Gateway scan.
- Host-paired Bluetooth setup for supported GROW meters.
- Diagnostics and configuration entities for supported meter features.

## Home Assistant companion PRs

- Documentation PR: https://github.com/home-assistant/home-assistant.io/pull/45149
- Brands PR: https://github.com/home-assistant/brands/pull/10242

These PRs are companion submissions for the public Home Assistant ecosystem.
This README does not claim Home Assistant Core acceptance or a quality-scale
rating.

## Source

Public source repository:

https://github.com/ineprometering/home-assistant-inepro-metering
