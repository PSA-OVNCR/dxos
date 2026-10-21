# DX-OS Trust Core

A **headless core platform (Layer 1) for the DX-OS Open-Core model**. Applications that plug in get SSO, storage and workflow, and are **forced to comply** with trust policies. Every important result is **independently verifiable**.

Entry for the **Vietnam Student Informatics Olympiad – Open Source Software 2026** (theme: *DX-OS Open-Core*).

## Status: v0.2.0
**In progress; not tagged yet.** The code of milestone M2 (Tier-0: workflow, sealing, verification, installer) is in
place with unit and integration tests. The M2 end-to-end tests and the evidence for AT-13, AT-18, AT-19 and AT-20 have
not been run on a real stack yet (they need Docker and the VPS); v0.1.0 is not tagged either. Progress notes
(Vietnamese): `docs/progress/`.

## Legal nature of the seal
Close translation of the team's agreed statement (the Vietnamese original in [README.md](README.md) is authoritative):

> A digital seal is a special-purpose electronic signature created by the operating organisation (Article 22(1)(a), Law on Electronic Transactions 2023). Within the organisation, the seal confirms that a document has been approved and has not been modified. The seal has **not** been certified as "secure", so it is **not** equivalent to a handwritten signature (Article 23(2)) and is **not** a digital signature. To use the seal in transactions with outside organisations or individuals with legal effect, the organisation must register for certification (Article 25(3)). For outsiders, the verification portal is a tool for **technical integrity checking**.

Mapping of mechanisms to articles, what is **not** achieved, and personal-data limits (Vietnamese):
[docs/legal-mapping.md](docs/legal-mapping.md). This is the team's technical interpretation, not legal advice.

## Quick start (development)
```bash
make dev-install
make check
```
See [BUILD.md](BUILD.md).

**Write a new app in 30 minutes without touching `core/`** (the guide is in Vietnamese): [docs/tutorial-app-30-phut.md](docs/tutorial-app-30-phut.md). It uses the runnable example [examples/so-muon-sach/](examples/so-muon-sach/); the checklist for an outside tester is [docs/at26-checklist.md](docs/at26-checklist.md).

## License
Apache License 2.0 (see [LICENSE](LICENSE)). Every source file carries an SPDX header, checked with `reuse lint`.

Third-party services run independently, are not distributed in this repository, and keep their own licenses. See [LICENSES-THIRD-PARTY.md](LICENSES-THIRD-PARTY.md).

The `trust-core` image installs pypdfium2 at build time; it bundles PDFium and third-party components, including software
from **The FreeType Project** (www.freetype.org) and software based in part on the work of the **Independent JPEG Group**.
Details (Vietnamese): [docs/evidence/pypdfium2-giay-phep.md](docs/evidence/pypdfium2-giay-phep.md).
