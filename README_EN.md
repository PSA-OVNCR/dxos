# DX-OS Trust Core

A **headless core platform (Layer 1) for the DX-OS Open-Core model**. Applications that plug in get SSO, storage and workflow, and are **forced to comply** with trust policies. Every important result is **independently verifiable**.

Entry for the **Vietnam Student Informatics Olympiad – Open Source Software 2026** (theme: *DX-OS Open-Core*).

## Status
- **v0.2.0 (M2): in progress; not tagged yet.** The Tier-0 code (workflow, sealing, verification, installer) is in place
  with unit and integration tests. The M2 end-to-end tests passed 13/13 on Docker Desktop (22 Oct, AT-20 skipped); the
  parts that need the VPS (AT-13, AT-18, AT-19, AT-20) have not been run. v0.1.0 is tagged (22 Oct).
- **v0.3.0 (M3): code done in the cloud; not tagged yet.** The SDK, the App A and App B user interfaces, the Vue
  verification portal, tag-based deployment and the 30-minute tutorial exist, with unit tests and Playwright tests
  against a mocked API. **Not run on a real stack yet:** the SPA build in Docker (`make web-build`), the Playwright suite
  on a real browser (V27), the attack board (V28), `ops/deploy.sh` on the VPS (V29) and OpenTimestamps receipts (V32).
  The to-do list (Vietnamese) is in section 13 of `docs/progress/2026-10-21-tong-ket-tien-do.md`.

## Layer 2: SDK, applications and verification portal
The user interfaces are static Vue 3 single-page apps built with Vite and served by Caddy from the `apps-static` volume.
They are clients of the core API only; every security decision stays in the core.

| Path | What it is | Source |
|---|---|---|
| `/apps/phong-ho-so/` | App A "Digital Records Room": documents, attachments with quarantine status, task inbox, PII review and erasure, seal with QR code, revocation, outgoing-document register | `apps/phong-ho-so/web` |
| `/apps/chung-nhan/` | App B "Digital Certificates": CSV import (including Excel CSV in UTF-8 BOM, CP1258, UTF-16), batch approval, certificate and print page | `apps/chung-nhan/web` |
| `/apps/verify/` | Verification portal: hashes the file and checks the proof bundle in the browser (the file never leaves the machine); compares against the anchor repository when built with `VITE_ANCHOR_RAW_BASE` | `verify-portal/app` |
| `/apps/verify-lite/` | The earlier minimal verification page (static HTML, no build), kept as a fallback | `verify-portal/minimal` |
| `/apps/so-muon-sach/` | Example app of the 30-minute tutorial | `examples/so-muon-sach` |

Scope of App B (spec section 14): it is a system to **manage and verify electronic certificates** (certificates of event
participation). It is **not** a PKI certificate-issuing system, **not** a digital signature or digital-signature
certification service, and it does **not** issue diplomas or certificates of the national education system. The "digital
seal" is the operating organisation's special-purpose electronic signature and has **not** been certified as secure
(section 25.1); for outsiders, verification is a technical integrity check.

The tutorial's AT-26 test (an outside person follows the 30-minute guide) has not been organised yet (V31).

```bash
npm ci && make web-check     # needs Node 22 and npm 11.6.2 (see BUILD.md)
make web-build               # builds in a one-shot Node container into the apps-static volume
```
`make web-build` needs Docker and a digest-pinned Node image. The digest was pinned on 22 Oct 2026 with `make pin-images`
on the team lead's machine (V35); the build itself has not been run yet (V27). The portal compares against the anchor repository only when the
build has `VITE_ANCHOR_RAW_BASE` and `.env` has a matching `DXOS_ANCHOR_RAW_ORIGIN` (needs the real anchor repository,
V34); otherwise it says plainly that no comparison was made. Tag-based VPS deployment:
[docs/runbook-deploy.md](docs/runbook-deploy.md) (Vietnamese). The SDK for Layer-2 developers:
[sdk/js/README.md](sdk/js/README.md) (Vietnamese). Acceptance matrix AT-01..AT-28:
[docs/acceptance.md](docs/acceptance.md).

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
