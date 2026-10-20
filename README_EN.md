# DX-OS Trust Core

A **headless core platform (Layer 1) for the DX-OS Open-Core model**. Applications that plug in get SSO, storage and workflow, and are **forced to comply** with trust policies. Every important result is **independently verifiable**.

Entry for the **Vietnam Student Informatics Olympiad – Open Source Software 2026** (theme: *DX-OS Open-Core*).

## Status
Work in progress. Current milestone: **M0 (foundation)**. See `docs/superpowers/plans/`.

## Quick start (development)
```bash
make dev-install
make check
```
See [BUILD.md](BUILD.md).

## License
Apache License 2.0 (see [LICENSE](LICENSE)). Every source file carries an SPDX header, checked with `reuse lint`.

Third-party services run independently, are not distributed in this repository, and keep their own licenses. See [LICENSES-THIRD-PARTY.md](LICENSES-THIRD-PARTY.md).

The `trust-core` image installs pypdfium2 at build time; it bundles PDFium and third-party components, including software
from **The FreeType Project** (www.freetype.org) and software based in part on the work of the **Independent JPEG Group**.
Details (Vietnamese): [docs/evidence/pypdfium2-giay-phep.md](docs/evidence/pypdfium2-giay-phep.md).
