# Plan 01 — Nền móng & Tier-0 phần 1 (M0 → M1, release v0.1.0)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng xong repo chuẩn PoF, hạ tầng có phân vùng mạng kiểm chứng được, khung trust-core gồm identity, manifest, PDP, Records API, kiểm dịch + CAS, ledger Merkle + STH ký + neo + witness. Kết thúc bằng release **v0.1.0** ngày **09/11/2026**.

**Architecture:** Xem Plan 00 mục "Architecture". Plan này hiện thực các story S0.1, S0.2, S1.1–S1.5, S2.1–S2.5, S3.0–S3.3, S4.1.

**Tech Stack:**
- Python 3.12, FastAPI, asyncpg, pydantic-settings, PyJWT[crypto], jsonschema, PyYAML, pypdfium2, boto3, httpx, cryptography.
- Test: pytest, pytest-asyncio, respx.
- Hạ tầng: Docker Compose, Caddy, Apache APISIX, Keycloak, PostgreSQL, SeaweedFS, ClamAV, OpenBao, Flowable.

**Spec:** `docs/superpowers/specs/2026-10-20-dxos-trust-core-design.md` (1.0.1) · **Kế hoạch tổng thể:** `docs/superpowers/plans/2026-10-20-dxos-00-ke-hoach-tong-the.md`

## Global Constraints

Toàn bộ mục "Global Constraints" của Plan 00 áp dụng nguyên văn. Plan này thêm:
- Mọi dependency Python mới phải được thêm vào `LICENSES-THIRD-PARTY.md` **trong cùng commit**. Giấy phép phải là MIT, BSD, Apache-2.0, PSF hoặc ISC. Gặp giấy phép khác thì **dừng lại hỏi trưởng nhóm**.
- Mọi image Docker được ghim bằng `@sha256:<digest>`. Digest được chọn khi thêm image và ghi vào `LICENSES-THIRD-PARTY.md`.
- **Không commit chuỗi EICAR nguyên văn** vào repo (Windows Defender trên máy thành viên sẽ cách ly tệp). Fixture lưu ở dạng base64 và giải mã khi chạy test.

## Review Focus

Như Plan 00. Các test tương ứng nằm ở:
- RF1 (NFC/NFD) và RF5 (múi giờ): Task 2 và Task 13
- RF2 (tệp đội lốt PDF): Task 14
- RF3 (token mang vai trò app khác): Task 10 và Task 12
- RF4 (ghi ledger đồng thời): Task 9

## Quyết định của plan (bổ sung cho spec, có lý do)

- **D1: Kiểm dịch trước, kiểm PDF sau** (spec 13.1 ghi thứ tự ngược lại). Đảo lại để **mọi** mã độc, kể cả tệp không phải PDF, đều được cách ly và ghi `object.infected`, thay vì chỉ bị `REJECTED`. Cách này củng cố I2 và khớp khoảnh khắc demo EICAR.
- **D2: `ledger_entries.idx` do lõi cấp** dưới `pg_advisory_xact_lock`, không dùng `bigserial`. Lý do: `bigserial` có thể nhảy số khi rollback, trong khi chỉ số lá Merkle bắt buộc liên tục.
- **D3: Vai trò lấy từ realm role trong claim `realm_access.roles`**, dạng `app:<id>:<role>` và `dxos-admin`.
- **D4: Admin (`dxos-admin`) không mặc nhiên có quyền đọc dữ liệu ứng dụng.** Admin chỉ có quyền nếu được gán vai trò của app đó. Lý do: quyền tối thiểu, khớp mô hình X2 ở spec 11.6.
- **D5: Records API chuẩn hóa mọi chuỗi về NFC khi ghi** (RF1).
- **D6: Lõi được kiểm thử bằng manifest tổng hợp `test-app`** (`core/tests/fixtures/manifest-test-app.yaml`), không dùng manifest của A hay B. Lý do: phục vụ I3, nhất quán với AT-14.

## Phân công và thứ tự

| Task | Story | Chủ | Hạn | Phụ thuộc |
|---|---|---|---|---|
| 1 Khung repo & PoF | S0.1 | A | 22/10 | — |
| 2 Canonical JSON | S3.0 | B | 23/10 | 1 |
| 3 Merkle RFC 6962 | S3.0 | B | 26/10 | 2 |
| 4 Compose + mạng + gateway | S1.1, S1.3 | A | 25/10 | 1 |
| 5 Realm Keycloak | S1.2 | C | 24/10 | 4 (một phần) |
| 6 Spike Flowable | S1.5 | C | 26/10 | 4 |
| 7 Đo RAM | S1.4 | A | 26/10 | 4 |
| 8 Khung trust-core + migration | S2.1 | A | 29/10 | 4 |
| 9 Ledger | S3.1 | B | 30/10 | 3, 8 |
| 10 Identity | S2.2 | C | 29/10 | 5, 8 |
| 11 Manifest + validator + store | S2.3 | C | 31/10 | 8 |
| 12 PDP + che PII | S2.4 | B | 03/11 | 9, 10, 11 |
| 13 Records API | S2.5 | A | 06/11 | 12 |
| 14 Kiểm dịch + CAS + worker | S4.1 | B | 07/11 | 12 |
| 15 STH + OpenBao | S3.2 | C | 04/11 | 9 |
| 16 Neo + witness + admin anchor | S3.3 | C | 07/11 | 15 |
| 17 E2E M1 + release v0.1.0 | S0.2 | A | 09/11 | 13, 14, 16 |

---

### Task 1: Khung repo và baseline PoF (TV-A)

**Files:**
- Create: `LICENSE` (toàn văn https://www.apache.org/licenses/LICENSE-2.0.txt, không sửa), `NOTICE`, `README.md`, `README_EN.md`, `CHANGELOG.md` (Keep a Changelog, có mục `[Unreleased]`), `BUILD.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), `SECURITY.md`, `LICENSES-THIRD-PARTY.md`, `REUSE.toml`, `.gitattributes`, `.editorconfig`, `.env.example`, `Makefile`, `requirements-dev.txt`, `ruff.toml`, `pytest.ini`
- Create: `.github/workflows/ci.yml`, `.github/ISSUE_TEMPLATE/bug.yml`, `.github/ISSUE_TEMPLATE/feature.yml`, `.github/pull_request_template.md`
- Test: `tests/repo/test_repo_hygiene.py`

**Interfaces:**
- Produces: `make lint`, `make test`, `make reuse`; CI có các job `reuse`, `lint`, `unit`, `secrets`. Mọi task sau đều dựa vào những lệnh và job này.

- [ ] **Step 1: Viết test thất bại**

```python
# tests/repo/test_repo_hygiene.py
REQUIRED = ["LICENSE", "NOTICE", "README.md", "README_EN.md", "CHANGELOG.md", "BUILD.md",
            "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md",
            "LICENSES-THIRD-PARTY.md", "REUSE.toml", ".gitattributes", ".env.example", "Makefile"]

def test_required_files_exist():
    missing = [f for f in REQUIRED if not (ROOT / f).is_file()]
    assert missing == []

def test_gitattributes_forces_lf():
    assert "* text=auto eol=lf" in (ROOT / ".gitattributes").read_text(encoding="utf-8")

def test_license_is_apache_2():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in text and "Version 2.0, January 2004" in text

def test_env_example_has_no_real_secret():
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            assert line.split("=", 1)[1] in ("", "changeme") or line.split("=", 1)[1].startswith("<")
```

- [ ] **Step 2: Chạy test, xác nhận thất bại**

Run: `pytest tests/repo/test_repo_hygiene.py -v` · Expected: FAIL, `missing` khác rỗng.

- [ ] **Step 3: Tạo các tệp**
- `REUSE.toml` gán `Apache-2.0` và `SPDX-FileCopyrightText: 2026 <Tên đội>` cho các tệp không chèn được header (`*.json`, `*.md` của tài liệu, `LICENSE`, fixture nhị phân). Riêng `CODE_OF_CONDUCT.md` gán `CC-BY-4.0`.
- `Makefile` có các target: `lint` (`ruff check .`), `test` (`pytest -m "not integration and not infra"`), `reuse` (`reuse lint`), `up`, `down`, `netcheck`.
- Job `secrets` trong `ci.yml` chạy gitleaks bằng image Docker chính thức. **Không dùng `gitleaks-action`**, vì action này yêu cầu license key với tài khoản tổ chức.

- [ ] **Step 4: Chạy lại test và reuse**

Run: `pytest tests/repo -v && reuse lint` · Expected: PASS và dòng `Congratulations! Your project is compliant with version 3.x of the REUSE Specification :-)`

- [ ] **Step 5: Thiết lập GitHub (thủ công, có ảnh chụp lưu ở `docs/evidence/m0-github.png`)**

Tạo repo **public** `dxos`. Bật Issues và Discussions. Bảo vệ nhánh `main`: bắt buộc CI xanh và 1 người duyệt.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "chore: repo skeleton, Apache-2.0, REUSE, CI baseline"
```

---

### Task 2: `dxos-proof`: canonical JSON (TV-B)

**Files:**
- Create: `libs/dxos-proof/pyproject.toml` (tên gói `dxos-proof`, version `0.1.0`, `requires-python = ">=3.12"`, **không có dependency runtime**), `libs/dxos-proof/src/dxos_proof/__init__.py`, `libs/dxos-proof/src/dxos_proof/canonical.py`
- Test: `libs/dxos-proof/tests/test_canonical.py`

**Interfaces:**
- Produces:
  - `class CanonicalError(ValueError)`
  - `canonical_bytes(value: object) -> bytes`
  - `rfc3339_utc(dt: datetime) -> str`
  - `sha256_hex(data: bytes) -> str`

- [ ] **Step 1: Viết test thất bại**

```python
def test_sorted_keys_no_whitespace():
    assert canonical_bytes({"b": 1, "a": "x"}) == b'{"a":"x","b":1}'

def test_rejects_float():
    with pytest.raises(CanonicalError): canonical_bytes({"x": 1.5})

def test_rejects_non_string_key():
    with pytest.raises(CanonicalError): canonical_bytes({1: "a"})

def test_unicode_not_escaped():
    assert canonical_bytes({"t": "ễ"}) == '{"t":"ễ"}'.encode("utf-8")

def test_nfc_normalization_values_and_keys():           # RF1
    nfd, nfc = "Nguyễn", "Nguyễn"
    assert canonical_bytes({"t": nfd}) == canonical_bytes({"t": nfc})
    assert canonical_bytes({nfd: 1}) == canonical_bytes({nfc: 1})

def test_rfc3339_utc_converts_offset():                   # RF5
    dt = datetime(2026, 10, 20, 7, 30, tzinfo=timezone(timedelta(hours=7)))
    assert rfc3339_utc(dt) == "2026-10-20T00:30:00Z"

def test_rfc3339_rejects_naive():
    with pytest.raises(CanonicalError): rfc3339_utc(datetime(2026, 10, 20))

def test_rejects_datetime_object_directly():
    with pytest.raises(CanonicalError): canonical_bytes({"ts": datetime.now(timezone.utc)})

def test_sha256_hex():
    assert sha256_hex(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
```

- [ ] **Step 2:** Run `pytest libs/dxos-proof/tests/test_canonical.py -v` · Expected: FAIL (ImportError).

- [ ] **Step 3: Cài đặt `canonical_bytes`**
- Duyệt đệ quy; chỉ chấp nhận `dict` với khóa `str`, `list`, `str`, `int`, `bool`, `None`.
- Chuẩn hóa mọi `str` (cả khóa lẫn giá trị) bằng `unicodedata.normalize("NFC", …)`.
- Sau đó gọi `json.dumps(..., ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8")`.
- Ghi chú trong docstring: thứ tự khóa theo code point có thể khác JCS (RFC 8785) với ký tự ngoài BMP. Repo không dùng ký tự ngoài BMP làm khóa.
- `rfc3339_utc`: `dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`.

- [ ] **Step 4:** Run lại · Expected: PASS (9 test).

- [ ] **Step 5:** Commit `feat(proof): canonical JSON with NFC and UTC timestamps`

---

### Task 3: `dxos-proof`: Merkle RFC 6962 (TV-B)

**Files:**
- Create: `libs/dxos-proof/src/dxos_proof/merkle.py`
- Test: `libs/dxos-proof/tests/test_merkle.py`

**Interfaces:**
- Produces (mọi hash là `bytes` 32 byte; `entries` là danh sách **dữ liệu lá thô**, chưa băm):
  - `leaf_hash(data: bytes) -> bytes`
  - `node_hash(left: bytes, right: bytes) -> bytes`
  - `root(entries: Sequence[bytes]) -> bytes`
  - `inclusion_proof(index: int, entries: Sequence[bytes]) -> list[bytes]`
  - `consistency_proof(m: int, entries: Sequence[bytes]) -> list[bytes]`
  - `verify_inclusion(leaf: bytes, index: int, size: int, proof: Sequence[bytes], root_hash: bytes) -> bool`. Tham số `leaf` là **leaf hash**.
  - `verify_consistency(m: int, n: int, root_m: bytes, root_n: bytes, proof: Sequence[bytes]) -> bool`

- [ ] **Step 1: Viết test thất bại**

Dùng các test vector dưới đây. Chúng đã được tính lại khi viết plan và khớp với vector chuẩn của Certificate Transparency.

```python
L = [bytes.fromhex(x) for x in ["", "00", "10", "2021", "3031", "40414243",
                                 "5051525354555657", "606162636465666768696a6b6c6d6e6f"]]
ROOTS = {
 0: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
 1: "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d",
 2: "fac54203e7cc696cf0dfcb42c92a1d9dbaf70ad9e621f4bd8d98662f00e3c125",
 3: "aeb6bcfe274b70a14fb067a5e5578264db0fa9b51af5e0ba159158f329e06e77",
 4: "d37ee418976dd95753c1c73862b9398fa2a2cf9b4ff0fdfe8b30cd95209614b7",
 5: "4e3bbb1f7b478dcfe71fb631631519a3bca12c9aefca1612bfce4c13a86264d4",
 6: "76e67dadbcdf1e10e1b74ddc608abd2f98dfb16fbce75277b5232a127f2087ef",
 7: "ddb89be403809e325750d3d263cd78929c2942b7942a34b77e122c9594a74c8c",
 8: "5dc9da79a70659a9ad559cb701ded9a2ab9d823aad2f4960cfe370eff4604328"}

@pytest.mark.parametrize("n", range(9))
def test_roots(n): assert root(L[:n]).hex() == ROOTS[n]

def test_inclusion_proof_index5_size8():
    assert [h.hex() for h in inclusion_proof(5, L)] == [
      "bc1a0643b12e4d2d7c77918f44e0f4f79a838b6cf9ec5b5c283e1f4d88599e6b",
      "ca854ea128ed050b41b35ffc1b87b8eb2bde461e9e3b5596ece6b9d5975a0ae0",
      "d37ee418976dd95753c1c73862b9398fa2a2cf9b4ff0fdfe8b30cd95209614b7"]

def test_consistency_3_to_7():
    assert [h.hex() for h in consistency_proof(3, L[:7])] == [
      "0298d122906dcfc10892cb53a73992fc5b9f493ea4c9badb27b791b4127a7fe7",
      "07506a85fd9dd2f120eb694f86011e5bb4662e5c415a62917033d4a9624487e7",
      "fac54203e7cc696cf0dfcb42c92a1d9dbaf70ad9e621f4bd8d98662f00e3c125",
      "837dbb152e9b079010717e84e865da4ebc0fa198a806d59d31bf15accef22d0e"]

def test_consistency_4_to_8():
    assert [h.hex() for h in consistency_proof(4, L)] == [
      "6b47aaf29ee3c2af9af889bc1fb9254dabd31177f16232dd6aab035ca39bf6e4"]

def test_verify_all_pairs_up_to_16():
    E = [bytes([i]) for i in range(16)]
    for n in range(1, 17):
        for i in range(n):
            assert verify_inclusion(leaf_hash(E[i]), i, n, inclusion_proof(i, E[:n]), root(E[:n]))
        for m in range(1, n + 1):
            assert verify_consistency(m, n, root(E[:m]), root(E[:n]), consistency_proof(m, E[:n]))

def test_tampered_proofs_fail():
    p = consistency_proof(3, L[:7]); p[0] = bytes(32)
    assert not verify_consistency(3, 7, bytes.fromhex(ROOTS[3]), bytes.fromhex(ROOTS[7]), p)
    q = inclusion_proof(5, L); q[1] = bytes(32)
    assert not verify_inclusion(leaf_hash(L[5]), 5, 8, q, bytes.fromhex(ROOTS[8]))
```

- [ ] **Step 2:** Run `pytest libs/dxos-proof/tests/test_merkle.py -v` · Expected: FAIL.

- [ ] **Step 3: Cài đặt**
- Sinh cây và proof theo RFC 6962 §2.1: MTH, PATH, SUBPROOF với `k` là lũy thừa 2 lớn nhất mà `k < n`.
- Kiểm chứng theo thuật toán lặp của **RFC 9162 §2.1.3.2** (inclusion) và **§2.1.4.2** (consistency). Phải xử lý đủ các trường hợp `m == n`, `m` là lũy thừa của 2, proof rỗng.

- [ ] **Step 4:** Run lại · Expected: PASS.

- [ ] **Step 5:** Commit `feat(proof): RFC 6962 Merkle tree, inclusion and consistency proofs`

---

### Task 4: Compose, phân vùng mạng, gateway, netcheck (TV-A)

**Files:**
- Create:
  - `deploy/compose.yaml`, `deploy/compose.p16.yaml`, `deploy/compose.p8.yaml`, `deploy/compose.dev-lite.yaml`, `deploy/compose.test.yaml`
  - `deploy/network-matrix.yaml`
  - `deploy/caddy/Caddyfile`, `deploy/apisix/config.yaml`, `deploy/apisix/apisix.yaml`
  - `deploy/fake-av/` (stub nói giao thức clamd, **chỉ nhận diện EICAR**; trong compose gắn label `dxos.dev-only: "true"`)
  - `ops/netcheck.py`
- Test: `tests/infra/test_compose_static.py`, `tests/infra/test_network_live.py` (marker `infra`)

**Interfaces:**
- Produces:
  - Tên service (các task sau phải dùng đúng): `caddy`, `apisix`, `keycloak`, `kc-db`, `trust-core-api`, `trust-core-worker`, `flowable`, `flowable-db`, `core-db`, `seaweedfs`, `clamav`, `openbao`, `net-probe-app`.
  - Tên mạng: `net-edge`, `net-front`, `net-app`, `net-idp`, `net-kcdb`, `net-wf`, `net-fldb`, `net-data`, `net-egress`.
  - Hàm `ops/netcheck.py::run_probes(matrix_path: Path, project: str) -> list[ProbeResult]`.
  - Lớp `ProbeResult(src_net: str, target: str, expect: Literal["open","closed"], actual: Literal["open","closed"])`.
- `trust-core-api` và `trust-core-worker` tạm dùng **image stub** (`python:3.12-slim` chạy `python -m http.server 8000`). Task 8 sẽ thay bằng image thật.
- `net-probe-app` là container `busybox` nằm trong `net-app`, giả lập Viewer và backend Tầng 2.

- [ ] **Step 1: Viết `deploy/network-matrix.yaml`**

Chép nguyên ma trận ở spec 6.2 (phần `membership` và cờ `internal`), thêm danh sách `probes`. Ví dụ tối thiểu, bản thật phải có đủ các probe sau:

```yaml
probes:
  - {from: net-front, to: "apisix:9080",           expect: open}
  - {from: net-front, to: "trust-core-api:8000",   expect: closed}   # caddy không vòng qua APISIX được
  - {from: net-app,   to: "trust-core-api:8000",   expect: open}
  - {from: net-app,   to: "core-db:5432",          expect: closed}
  - {from: net-app,   to: "seaweedfs:8333",        expect: closed}
  - {from: net-app,   to: "openbao:8200",          expect: closed}
  - {from: net-app,   to: "clamav:3310",           expect: closed}
  - {from: net-app,   to: "flowable:8080",         expect: closed}
  - {from: net-app,   to: "kc-db:5432",            expect: closed}
  - {from: net-wf,    to: "core-db:5432",          expect: closed}
  - {from: net-fldb,  to: "core-db:5432",          expect: closed}
  - {from: net-wf,    to: "openbao:8200",          expect: closed}
  - {from: net-data,  to: "core-db:5432",          expect: open}
```

- [ ] **Step 2: Viết test tĩnh, chưa cần Docker chạy**

```python
# compose_cfg: json.loads(docker compose -f deploy/compose.yaml -f deploy/compose.p16.yaml config --format json)
def test_membership_matches_matrix(compose_cfg, matrix):
    for svc, nets in matrix["membership"].items():
        assert set(compose_cfg["services"][svc]["networks"]) == set(nets), svc

def test_only_caddy_publishes_ports(compose_cfg):
    assert {s for s, d in compose_cfg["services"].items() if d.get("ports")} == {"caddy"}

def test_internal_flags(compose_cfg, matrix):
    for net, spec in matrix["networks"].items():
        assert compose_cfg["networks"][net].get("internal", False) == spec["internal"], net

def test_no_dev_only_service_in_production(compose_cfg):        # AT-24
    assert not [s for s, d in compose_cfg["services"].items()
                if d.get("labels", {}).get("dxos.dev-only") == "true"]

def test_images_pinned_by_digest(compose_cfg):
    assert all("@sha256:" in d["image"] for d in compose_cfg["services"].values() if "image" in d)
```

- [ ] **Step 3:** Run `pytest tests/infra/test_compose_static.py -v` · Expected: FAIL.

- [ ] **Step 4: Viết compose, Caddyfile, APISIX**
- Caddy:
  - `/auth/*` → `keycloak:8080`
  - `/api/*`, `/admin/*`, `/verify/*` → `apisix:9080`
  - `/apps/*` → `file_server` thư mục `/srv/apps`
  - Host admin: giới hạn bằng `remote_ip` lấy từ `.env`
- APISIX chạy chế độ standalone, route theo bảng ở spec 6.2:
  - `openid-connect` với `bearer_only: true` và `discovery` trỏ tới `http://keycloak:8080/realms/dxos/.well-known/openid-configuration`
  - `limit-req` cho `/verify/v1/*`
  - Route `/view/*` để ở trạng thái tắt cho tới khi có Viewer
- p16 và p8 khác nhau về heap JVM và cấu hình ClamAV (spec 16.1).

- [ ] **Step 5:** Run test tĩnh · Expected: PASS.

- [ ] **Step 6: Viết test sống**

```python
@pytest.mark.infra
def test_probes_match_matrix():                                   # AT-01 bản đầu
    bad = [r for r in run_probes(MATRIX, "dxos") if r.expect != r.actual]
    assert bad == []

@pytest.mark.infra
def test_api_requires_token():                                    # AT-02 (phía gateway)
    r = httpx.get("https://localhost/api/v1/healthz", verify=False)
    assert r.status_code == 401
```

Cách `run_probes` hoạt động: `docker run --rm --network dxos_<net> busybox:<digest> nc -z -w 2 <host> <port>`; mã thoát 0 nghĩa là `open`.

- [ ] **Step 7:** Run `make up && pytest -m infra tests/infra -v` · Expected: PASS. In bảng kết quả bằng `python ops/netcheck.py --matrix deploy/network-matrix.yaml`.

- [ ] **Step 8:** Commit `feat(deploy): segmented networks, gateway routes, netcheck (AT-01 v1, AT-24)`

---

### Task 5: Realm Keycloak `dxos` (TV-C)

**Files:**
- Create: `deploy/keycloak/realm-dxos.json` (dùng cho production), `deploy/keycloak/realm-dxos-dev.json` (thêm người dùng và client test; **chỉ nạp ở dev-lite và test**)
- Test: `tests/infra/test_keycloak_realm.py` (marker `infra`)

**Interfaces:**
- Produces:
  - Client `dxos-spa`: public, PKCE S256, redirect `https://<domain>/apps/*`.
  - Client scope `dxos-api-audience`: audience mapper thêm `dxos-api` vào `aud`.
  - Client `dxos-installer`: confidential, có service account. Quyền cụ thể do Plan 02 cấp.
  - Realm role `dxos-admin`.
  - Người dùng dev: `chuyen_vien1`, `truong_phong1`, `giam_doc1`, `van_thu1`, `nhan_vien1` (vai trò `app:phong-ho-so:*`); `can_bo_clb1`, `truong_clb1` (vai trò `app:chung-nhan:*`); `owner_a1`, `owner_b1` (vai trò `app:test-app:member`); `admin1` (`dxos-admin`).
  - Client `dxos-test`: chỉ có trong bản dev, cho phép direct grant để test lấy token.

- [ ] **Step 1: Viết test thất bại**

```python
@pytest.mark.infra
def test_token_has_dxos_api_audience_and_issuer():
    tok = password_grant("dxos-test", "chuyen_vien1")
    claims = jwt.decode(tok, options={"verify_signature": False})
    assert "dxos-api" in (claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]])
    assert claims["iss"].endswith("/realms/dxos")
    assert "app:phong-ho-so:chuyen_vien" in claims["realm_access"]["roles"]

@pytest.mark.infra
def test_spa_client_disallows_password_grant():
    assert password_grant_status("dxos-spa", "chuyen_vien1") == 400
```

- [ ] **Step 2:** Run · Expected: FAIL.
- [ ] **Step 3:** Tạo realm bằng console admin, export ra JSON, xóa secret khỏi tệp export (secret lấy từ `.env`). Dùng `kc.sh import` khi khởi động container.
- [ ] **Step 4:** Run `pytest -m infra tests/infra/test_keycloak_realm.py -v` · Expected: PASS.
- [ ] **Step 5:** Commit `feat(deploy): keycloak realm dxos with dxos-api audience and dev users`

---

### Task 6: Spike Flowable (TV-C). **Spike là mã thử nghiệm; chỉ giữ lại tài liệu và script smoke**

**Files:**
- Create: `docs/spikes/flowable.md`, `docs/spikes/flowable-smoke.sh`
- Modify: `deploy/compose.yaml`: thêm service `flowable` và `flowable-db` vào đúng mạng `net-wf` và `net-fldb`

**Cần trả lời trong `docs/spikes/flowable.md`:**
1. Image OSS nào dùng được, version bao nhiêu, giấy phép gì (kiểm trực tiếp tệp LICENSE trong image hoặc repo).
2. Thời gian khởi động và RAM khi rảnh.
3. Endpoint REST cho các thao tác: deploy BPMN, start process theo key, liệt kê task theo `candidateGroup`/`assignee`, complete task kèm biến, lấy trạng thái process instance.
4. Cấu hình kết nối tới `flowable-db` với tài khoản riêng.
5. **Có console admin trong bản OSS hay không** (để đưa vào ma trận UI admin của R7).
6. Đề xuất: giữ ADR-09 hay dùng phương án lùi (tự build image).

- [ ] **Step 1:** Viết `flowable-smoke.sh`: deploy một BPMN gồm 1 user task → start → complete → kiểm tra process đã kết thúc.
- [ ] **Step 2:** Run `bash docs/spikes/flowable-smoke.sh` · Expected: dòng cuối `SMOKE OK`.
- [ ] **Step 3:** Run lại `pytest tests/infra/test_compose_static.py` · Expected: PASS (ma trận mạng vẫn đúng sau khi thêm Flowable).
- [ ] **Step 4:** Commit `docs(spike): flowable REST findings and smoke script`

---

### Task 7: Đo RAM, hồ sơ p16 (TV-A)

**Files:**
- Create: `ops/measure.sh` (cú pháp `ops/measure.sh <giây> <out.csv>`; lấy mẫu `docker stats --no-stream --format '{{.Name}},{{.MemUsage}}'` và `free -m` mỗi 5 giây), `docs/capacity.md`

- [ ] **Step 1:** Chạy 4 kịch bản theo spec 16.2, kịch bản e2e để tới Task 17 mới chạy:
  1. Khởi động lạnh `make up`
  2. `docker compose exec clamav freshclam`
  3. 20 lượt tải lên song song (dùng `ops/load_upload.py` sau Task 14; tạm bỏ qua ở M0)
- [ ] **Step 2:** Ghi vào `docs/capacity.md` bảng đỉnh RAM theo từng container cùng tổng RAM.
  Expected (AT-22): tổng đỉnh < 80% RAM của VPS; không container nào ở trạng thái `OOMKilled` (kiểm bằng `docker inspect --format '{{.State.OOMKilled}}'`).
- [ ] **Step 3:** Commit `docs(ops): capacity measurement p16 (AT-22 v1)`

---

### Task 8: Khung trust-core và migration (TV-A)

**Files:**
- Create: `core/pyproject.toml` (gói `dxos-core`; dependency: `fastapi`, `uvicorn[standard]`, `asyncpg`, `pydantic-settings`, `pyjwt[crypto]`, `jsonschema`, `pyyaml`, `httpx`, `boto3`, `pypdfium2`, `cryptography`, `dxos-proof` cài ở chế độ path)
- Create: `core/src/dxos_core/settings.py`, `app.py`, `errors.py`, `db/pool.py`, `db/migrate.py`, `health.py`, `core/migrations/001_core.sql`, `core/Dockerfile` (chạy bằng user không phải root)
- Modify: `deploy/compose.yaml`: thay stub của `trust-core-api` và `trust-core-worker` bằng image thật
- Test: `core/tests/test_app.py`, `core/tests/integration/test_migrations.py`

**Interfaces:**
- Produces:
  - `class Settings(BaseSettings)` với `env_prefix="DXOS_"` và đúng các trường sau:
    `database_url: str`, `s3_endpoint: str`, `s3_access_key_file: Path`, `s3_secret_key_file: Path`,
    `s3_bucket_staging: str = "dxos-staging"`, `s3_bucket_objects: str = "dxos-objects"`, `s3_bucket_quarantine: str = "dxos-quarantine"`,
    `clamd_host: str = "clamav"`, `clamd_port: int = 3310`, `openbao_addr: str = "http://openbao:8200"`, `openbao_token_file: Path`,
    `keycloak_issuer: str`, `keycloak_jwks_url: str`, `jwt_audience: str = "dxos-api"`,
    `actor_hmac_key_file: Path`, `anchor_repo_dir: Path`, `max_upload_mb_default: int = 15`
  - `create_app(settings: Settings | None = None) -> FastAPI`
  - `async def create_pool(dsn: str) -> asyncpg.Pool`
  - `async def apply_migrations(dsn: str, migrations_dir: Path) -> list[str]` (theo dõi bằng bảng `schema_migrations`)
  - `problem(status: int, type_: str, title: str, detail: str | None = None) -> JSONResponse` (`application/problem+json`, `type_` dạng `https://dxos.dev/problems/<slug>`)
  - Hai role trong DB: `dxos_owner` (chạy migration), `dxos_core` (ứng dụng dùng)
- **Schema `001_core.sql`** đúng bảng ở spec 10.1, với các điều chỉnh sau:
  - `records.seal_state` kiểu text, `CHECK (seal_state IN ('NONE','SEAL_PENDING','SEALED','REVOKED'))`, mặc định `'NONE'`.
  - `objects.sha256` có `CHECK (sha256 ~ '^[0-9a-f]{64}$')`.
  - `ledger_entries.idx` là `bigint PRIMARY KEY`, **không** dùng `bigserial` (D2).
  - Trigger `ledger_append_only` trên `ledger_entries` và `tree_heads`: `BEFORE UPDATE OR DELETE` → `RAISE EXCEPTION 'ledger_append_only'`.
  - Trigger `record_seal_guard`: khi `OLD.seal_state <> 'NONE'` và `NEW.data IS DISTINCT FROM OLD.data` → `RAISE EXCEPTION 'record_sealed'`. Chỉ cho phép chuyển trạng thái `NONE→SEAL_PENDING→SEALED→REVOKED` (và `NONE→SEALED`).
  - `GRANT SELECT, INSERT ON ledger_entries, tree_heads TO dxos_core` (**không** cấp UPDATE, DELETE).

- [ ] **Step 1: Viết test thất bại**

```python
def test_healthz_ok(client):
    assert client.get("/healthz").json()["status"] == "ok"

@pytest.mark.integration
async def test_migrations_idempotent(owner_dsn):
    first = await apply_migrations(owner_dsn, MIGRATIONS); second = await apply_migrations(owner_dsn, MIGRATIONS)
    assert first == ["001_core.sql"] and second == []

@pytest.mark.integration
async def test_core_role_cannot_update_ledger(core_conn, seeded_ledger_row):
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await core_conn.execute("UPDATE ledger_entries SET subject='x' WHERE idx=0")

@pytest.mark.integration
async def test_owner_update_blocked_by_trigger(owner_conn, seeded_ledger_row):
    with pytest.raises(asyncpg.RaiseError, match="ledger_append_only"):
        await owner_conn.execute("UPDATE ledger_entries SET subject='x' WHERE idx=0")

@pytest.mark.integration
async def test_sealed_record_data_immutable(owner_conn, sealed_record_id):
    with pytest.raises(asyncpg.RaiseError, match="record_sealed"):
        await owner_conn.execute("UPDATE records SET data='{}' WHERE id=$1", sealed_record_id)

@pytest.mark.integration
async def test_seal_pending_to_sealed_allowed(owner_conn, pending_record_id):
    await owner_conn.execute("UPDATE records SET seal_state='SEALED' WHERE id=$1", pending_record_id)

@pytest.mark.integration
async def test_object_sha256_format(owner_conn):
    with pytest.raises(asyncpg.CheckViolationError):
        await owner_conn.execute("INSERT INTO objects(sha256,size,mime_sniffed,status,storage_key) VALUES('XYZ',1,'application/pdf','CLEAN','k')")
```

- [ ] **Step 2:** Run `docker compose -f deploy/compose.test.yaml up -d core-db && pytest core/tests -m "integration or not integration" -v` · Expected: FAIL.
- [ ] **Step 3:** Cài đặt các interface ở trên và viết `001_core.sql`.
- [ ] **Step 4:** Run lại · Expected: PASS. Chạy thêm `pytest tests/infra/test_compose_static.py` · Expected: PASS.
- [ ] **Step 5:** Commit `feat(core): app skeleton, settings, migrations with append-only ledger and seal guard`

---

### Task 9: Ghi ledger (TV-B)

**Files:**
- Create: `core/src/dxos_core/ledger/events.py`, `core/src/dxos_core/ledger/log.py`
- Test: `core/tests/integration/test_ledger_log.py`

**Interfaces:**
- Consumes: `canonical_bytes`, `rfc3339_utc`, `sha256_hex` (Task 2); `leaf_hash` (Task 3).
- Produces:
  - `EVENT_TYPES: frozenset[str]`, gồm **đúng** 18 loại ở spec 12.4: `app.submitted, app.installed, app.disabled, record.created, record.updated, upload.staged, object.clean, object.infected, object.rejected, object.read, field.revealed, pii.detected, pii.reviewed, task.completed, record.sealed, record.revoked, policy.denied, sth.published`
  - `@dataclass(frozen=True) class LedgerEntry: idx: int; ts: str; type: str; app_id: str | None; subject: str; actor_ref: str | None; body_sha256: str; leaf_hash: bytes`
  - `entry_bytes(e: LedgerEntry) -> bytes`: là `canonical_bytes` của 7 trường `{idx, ts, type, app_id, subject, actor_ref, body_sha256}`
  - `actor_ref(sub: str, key: bytes) -> str`: HMAC-SHA256 dạng hex
  - `async def append(conn, *, type: str, subject: str, body: Mapping, hmac_key: bytes, app_id: str | None = None, actor_sub: str | None = None) -> LedgerEntry`
  - `async def entries_bytes(conn, upto: int | None = None) -> list[bytes]` (sắp theo `idx`; `upto` không bao gồm)
  - `@dataclass class VerifyResult: ok: bool; first_bad_idx: int | None`
  - `async def verify_log(conn) -> VerifyResult`
- Ghi chú cài đặt `append`:
  - Mở transaction riêng.
  - Gọi `SELECT pg_advisory_xact_lock(724001)`.
  - `idx = COALESCE(MAX(idx), -1) + 1`.
  - `ts = rfc3339_utc(now)`; `body_sha256 = sha256_hex(canonical_bytes(body))`.
  - **Không lưu body.**

- [ ] **Step 1: Viết test thất bại**

```python
async def test_sequential_idx_from_zero(core_conn, key):
    a = await append(core_conn, type="record.created", subject="r1", body={}, hmac_key=key)
    b = await append(core_conn, type="record.updated", subject="r1", body={"v": 2}, hmac_key=key)
    assert (a.idx, b.idx) == (0, 1)

async def test_unknown_type_rejected(core_conn, key):
    with pytest.raises(ValueError): await append(core_conn, type="foo.bar", subject="x", body={}, hmac_key=key)

async def test_actor_ref_is_hmac_not_sub(core_conn, key):
    e = await append(core_conn, type="object.read", subject="o", body={}, hmac_key=key, actor_sub="user-123")
    assert e.actor_ref == hmac.new(key, b"user-123", "sha256").hexdigest() and "user-123" not in e.actor_ref

async def test_concurrent_appends_contiguous(core_pool, key):                     # RF4
    async def one(i):
        async with core_pool.acquire() as c:
            return (await append(c, type="object.read", subject=f"s{i}", body={}, hmac_key=key)).idx
    idxs = await asyncio.gather(*(one(i) for i in range(50)))
    assert sorted(idxs) == list(range(50))

async def test_leaf_hash_matches_entry_bytes(core_conn, key):
    e = await append(core_conn, type="record.created", subject="r", body={}, hmac_key=key)
    assert e.leaf_hash == leaf_hash(entry_bytes(e))

async def test_verify_detects_tamper(owner_conn, core_conn, key):                # AT-15 (phần DB)
    for i in range(5): await append(core_conn, type="object.read", subject=f"s{i}", body={}, hmac_key=key)
    await owner_conn.execute("ALTER TABLE ledger_entries DISABLE TRIGGER ledger_append_only")
    await owner_conn.execute("UPDATE ledger_entries SET subject='evil' WHERE idx=3")
    assert await verify_log(core_conn) == VerifyResult(ok=False, first_bad_idx=3)
```

- [ ] **Step 2:** Run `pytest core/tests/integration/test_ledger_log.py -v` · Expected: FAIL.
- [ ] **Step 3:** Cài đặt theo các interface ở trên.
- [ ] **Step 4:** Run lại · Expected: PASS (6 test).
- [ ] **Step 5:** Commit `feat(ledger): append-only log with advisory lock, HMAC actor ref, verify`

---

### Task 10: Identity (TV-C)

**Files:**
- Create: `core/src/dxos_core/identity/jwt.py`, `core/src/dxos_core/identity/deps.py`, `core/tests/helpers/tokens.py`
- Test: `core/tests/test_identity.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Principal: sub: str; roles: frozenset[str]; is_admin: bool`
  - `class AuthError(Exception)`
  - `class JwksVerifier`: khởi tạo `(jwks_url: str, issuer: str, audience: str, cache_ttl_s: int = 300)`; phương thức `async def verify(self, token: str) -> Principal`
    - **Chỉ chấp nhận RS256.**
    - Kiểm `iss`, `aud`, `exp`, `nbf`.
    - Vai trò lấy từ `realm_access.roles` (D3).
  - `app_roles(p: Principal, app_id: str) -> frozenset[str]`: trả tên vai trò **đã bỏ tiền tố**, chỉ tính các vai trò của đúng `app_id`.
  - FastAPI dependency `require_principal`: lỗi trả `401` dạng `problem+json`, type `.../unauthenticated`.
  - Test helper `make_token(sub: str, roles: list[str], **overrides) -> str` và fixture `test_jwks` (khóa RSA sinh lúc chạy test, JWKS được mock bằng respx). Các task 12, 13, 14 dùng lại helper này.

- [ ] **Step 1: Viết test thất bại**

```python
async def test_valid_token(verifier):
    p = await verifier.verify(make_token("u1", ["app:phong-ho-so:giam_doc", "dxos-admin"]))
    assert p.sub == "u1" and p.is_admin and "app:phong-ho-so:giam_doc" in p.roles

@pytest.mark.parametrize("override", [{"aud": "other"}, {"iss": "https://evil/realms/dxos"},
                                      {"exp": 1}, {"alg": "HS256"}, {"alg": "none"}])
async def test_rejected_tokens(verifier, override):
    with pytest.raises(AuthError): await verifier.verify(make_token("u1", [], **override))

def test_app_roles_only_for_that_app():                                         # RF3 (phần 1)
    p = Principal("u", frozenset({"app:phong-ho-so:giam_doc", "app:chung-nhan:truong_clb", "offline_access"}), False)
    assert app_roles(p, "phong-ho-so") == {"giam_doc"}
    assert app_roles(p, "chung-nhan") == {"truong_clb"}
    assert app_roles(p, "test-app") == frozenset()

def test_endpoint_without_token_is_401(client):
    r = client.get("/api/v1/whoami")
    assert r.status_code == 401 and r.headers["content-type"].startswith("application/problem+json")
```

- [ ] **Step 2:** Run `pytest core/tests/test_identity.py -v` · Expected: FAIL.
- [ ] **Step 3:** Cài đặt. Thêm route `GET /api/v1/whoami` trả về `{sub, roles, is_admin}` (dùng cho test và cho SDK sau này).
- [ ] **Step 4:** Run lại · Expected: PASS.
- [ ] **Step 5:** Commit `feat(identity): RS256 JWKS verifier, app-scoped roles, 401 problem responses`

---

### Task 11: Schema manifest, validator và kho manifest (TV-C)

**Files:**
- Create: `core/src/dxos_core/registry/manifest.schema.json`, `model.py`, `validator.py`, `store.py`
- Create: `apps/phong-ho-so/manifest.yaml` (chép **nguyên văn** spec 9.1), `apps/chung-nhan/manifest.yaml` (nội dung ở Step 3), `core/tests/fixtures/manifest-test-app.yaml`
- Test: `core/tests/test_manifest_validator.py`, `core/tests/integration/test_manifest_store.py`

**Interfaces:**
- Produces:
  - `GUARD_CATALOG = frozenset({"attachments_clean", "pii_reviewed", "not_same_actor", "role_in", "field_required", "record_not_sealed", "assignee_is_caller"})`
  - `class ManifestError(ValueError)` có thuộc tính `code: Literal["SCHEMA_INVALID","NAMESPACE_VIOLATION","FLOOR_WEAKENED","UNKNOWN_GUARD"]` và `path: str`
  - Các model pydantic: `Manifest`, `AppInfo`, `CollectionSpec`, `FieldSpec(type: Literal["string","sequence","integer","boolean","date"], required=False, public=False, pii: Literal["CCCD","PHONE","BANK_ACCOUNT","EMAIL","NAME"] | None = None, format: str | None = None)`, `AttachmentSpec(kinds: list[Literal["pdf"]], max_mb: int, min: int = 0)`, `AccessSpec(read: list[str], create: list[str], update: list[str] = [])`, `Policies`, `WorkflowSpec`
  - `validate_manifest(doc: dict) -> Manifest`
  - `async def save_manifest(conn, m: Manifest, raw: dict, status: Literal["PENDING","ACTIVE","DISABLED"], actor_sub: str) -> None`
  - `async def get_active(conn, app_id: str) -> Manifest | None`
- **Quy tắc validator:**
  - `app.id` khớp `^[a-z][a-z0-9-]{1,30}$`.
  - Tên role và collection khớp `^[a-z][a-z0-9_]{0,30}$`. Chứa `:` hoặc bắt đầu bằng `app` thì báo `NAMESPACE_VIOLATION`.
  - Phần tử trong `access` phải là `owner` hoặc `role:<role đã khai báo>`.
  - `reveal_roles` và `tasks.*.role` phải thuộc `roles`.
  - Tên guard (phần trước dấu `:`) phải thuộc `GUARD_CATALOG`.
  - Có khóa `quarantine` ở bất kỳ đâu với giá trị khác `"required"` thì báo `FLOOR_WEAKENED`.
  - `public_fields` phải là trường có cờ `public: true`.

- [ ] **Step 1: Viết test thất bại**

```python
@pytest.mark.parametrize("path", ["apps/phong-ho-so/manifest.yaml", "apps/chung-nhan/manifest.yaml",
                                  "core/tests/fixtures/manifest-test-app.yaml"])
def test_shipped_manifests_valid(path): assert validate_manifest(load_yaml(path)).app.id

def test_floor_weakened():                                                       # AT-11
    doc = load("phong-ho-so"); doc["collections"]["van_ban"]["attachments"]["quarantine"] = "optional"
    assert raises_code(doc) == "FLOOR_WEAKENED"

def test_unknown_guard():                                                        # AT-11
    doc = load("phong-ho-so"); doc["workflow"]["tasks"]["ban_hanh"]["guards"].append("skip_scan")
    assert raises_code(doc) == "UNKNOWN_GUARD"

@pytest.mark.parametrize("mutate", [lambda d: d["roles"].append("app:chung-nhan:truong_clb"),
                                    lambda d: d["collections"].__setitem__("x:y", {"fields": {}, "access": {"read": [], "create": []}})])
def test_namespace_violation(mutate):                                            # AT-12
    doc = load("phong-ho-so"); mutate(doc); assert raises_code(doc) == "NAMESPACE_VIOLATION"

def test_reveal_role_must_be_declared():
    doc = load("phong-ho-so"); doc["policies"]["pii"]["reveal_roles"] = ["ghost"]
    assert raises_code(doc) == "SCHEMA_INVALID"

@pytest.mark.integration
async def test_store_roundtrip(core_conn):
    m = validate_manifest(load("test-app")); await save_manifest(core_conn, m, load("test-app"), "ACTIVE", "admin")
    assert (await get_active(core_conn, "test-app")).app.id == "test-app"
```

- [ ] **Step 2:** Run · Expected: FAIL.

- [ ] **Step 3: Tạo manifest của App B** (theo spec 14 và 2.6)

```yaml
apiVersion: dxos/v1
app: { id: chung-nhan, version: 1.0.0, name: "Chứng nhận số", spaces: [P, D] }
roles: [can_bo_clb, truong_clb]
collections:
  chung_nhan:
    fields:
      so_chung_nhan: { type: sequence, format: "{n}/CN-CLB", public: true }
      ho_ten:        { type: string, required: true, public: true }
      su_kien:       { type: string, required: true, public: true }
      ngay_cap:      { type: date, required: true, public: true }
      email:         { type: string, pii: EMAIL }
    access: { read: [role:can_bo_clb, role:truong_clb], create: [role:can_bo_clb] }
policies:
  pii:    { reveal_roles: [truong_clb] }
  seal:   { on_event: "process.completed:approved", target: [record], public_fields: [so_chung_nhan, ho_ten, su_kien, ngay_cap] }
  verify: { public: true, require_file: false }
workflow:
  bpmn: bpmn/cap-chung-nhan.bpmn
  tasks:
    phe_duyet: { role: truong_clb, guards: [not_same_actor:creator] }
```

Fixture `test-app`:
- `roles: [member, reviewer]`
- collection `item` gồm các trường `title` (string, public), `secret_code` (string, `pii: CCCD`)
- `access: {read: [owner, role:reviewer], create: [role:member], update: [owner]}`
- `reveal_roles: [reviewer]`
- **không có** workflow

- [ ] **Step 4:** Cài đặt validator và store · Run lại · Expected: PASS.
- [ ] **Step 5:** Commit `feat(registry): manifest schema, floor and namespace validation, store; app manifests A/B`

---

### Task 12: PDP và che PII (TV-B)

**Files:**
- Create: `core/src/dxos_core/policy/pdp.py`, `core/src/dxos_core/policy/masking.py`
- Test: `core/tests/test_pdp.py`, `core/tests/test_masking.py`, `core/tests/integration/test_enforce.py`

**Interfaces:**
- Consumes: `Principal`, `app_roles` (Task 10); `Manifest`, `CollectionSpec` (Task 11); `append` (Task 9).
- Produces:
  - `Action = Literal["list", "read", "create", "update", "reveal_pii"]`
  - `@dataclass(frozen=True) class Decision: allow: bool; reason: str`
  - `decide(p: Principal, action: Action, m: Manifest, collection: str, record_owner: str | None) -> Decision`
    - Là hàm thuần.
    - Các `reason` có thể trả về: `"no_app_role"`, `"admin_no_data_access"` (D4), `"owner"`, `"role:<r>"`, `"not_in_access_list"`.
    - `list` dùng danh sách `read`. `update` dùng danh sách `update`. `reveal_pii` dùng `policies.pii.reveal_roles`.
  - `class NotFound(Exception)`, `class Forbidden(Exception)`
  - `async def enforce(conn, p, action, m, collection, record_owner, subject: str, hmac_key: bytes) -> None`
    - Khi từ chối: ghi ledger `policy.denied` với body `{action, reason, collection}`, `app_id=m.app.id`.
    - Sau đó raise `NotFound` nếu action là `read`/`update`/`reveal_pii`, raise `Forbidden` nếu là `list`/`create`.
  - `mask_value(v: str, pii: str) -> str`:
    - `CCCD`, `PHONE`, `BANK_ACCOUNT`: giữ 2 ký tự đầu và 2 ký tự cuối, phần giữa thay bằng `*` cùng số ký tự.
    - `EMAIL`: ký tự đầu + `***@` + tên miền.
    - `NAME`: chữ cái đầu mỗi từ kèm `.`.
  - `mask_record(data: dict, spec: CollectionSpec, can_reveal: bool) -> dict`

- [ ] **Step 1: Viết test thất bại**

```python
def test_owner_can_read(m_test):   assert decide(P("owner_a1", ["app:test-app:member"]), "read", m_test, "item", "owner_a1").allow
def test_non_owner_member_denied(m_test):
    assert decide(P("owner_b1", ["app:test-app:member"]), "read", m_test, "item", "owner_a1") == Decision(False, "not_in_access_list")
def test_role_from_other_app_denied(m_a):                                        # RF3
    assert decide(P("u", ["app:chung-nhan:truong_clb"]), "read", m_a, "van_ban", "x") == Decision(False, "no_app_role")
def test_admin_has_no_implicit_data_access(m_test):                              # D4
    assert decide(P("admin1", ["dxos-admin"], admin=True), "read", m_test, "item", "x") == Decision(False, "admin_no_data_access")
def test_reveal_only_reveal_roles(m_test):
    assert decide(P("r", ["app:test-app:reviewer"]), "reveal_pii", m_test, "item", "x").allow
    assert not decide(P("owner_a1", ["app:test-app:member"]), "reveal_pii", m_test, "item", "owner_a1").allow

@pytest.mark.parametrize("v,t,out", [("079203001234", "CCCD", "07********34"), ("0912345678", "PHONE", "09******78"),
                                     ("an.nguyen@saomai.vn", "EMAIL", "a***@saomai.vn"), ("Nguyễn Văn An", "NAME", "N. V. A.")])
def test_mask_value(v, t, out): assert mask_value(v, t) == out

@pytest.mark.integration
async def test_enforce_logs_policy_denied(core_conn, m_test, key):
    with pytest.raises(NotFound):
        await enforce(core_conn, P("owner_b1", ["app:test-app:member"]), "read", m_test, "item", "owner_a1", "rec-1", key)
    row = await core_conn.fetchrow("SELECT type, app_id FROM ledger_entries ORDER BY idx DESC LIMIT 1")
    assert tuple(row) == ("policy.denied", "test-app")
```

- [ ] **Step 2:** Run · Expected: FAIL.
- [ ] **Step 3:** Cài đặt.
- [ ] **Step 4:** Run lại · Expected: PASS.
- [ ] **Step 5:** Commit `feat(policy): PDP with app-scoped roles, admin least privilege, PII masking, denied events`

---

### Task 13: Records API (TV-A)

**Files:**
- Create: `core/src/dxos_core/records/router.py`, `service.py`, `sequences.py`
- Test: `core/tests/integration/test_records_api.py`

**Interfaces:**
- Consumes: `require_principal` (Task 10); `get_active`, `validate_manifest` (Task 11); `enforce`, `mask_record` (Task 12); `append` (Task 9); `problem` (Task 8).
- Produces (đường dẫn đúng như spec 12.1):
  - `GET /api/v1/apps/{app}/collections/{col}/records?cursor=&limit=` → `{"items": [Record], "next_cursor": str | null}`; mặc định `limit=50`, tối đa 200
  - `POST .../records` → `201`, kèm header `ETag: "<version>"`
  - `POST .../records:bulk` → `200 {"results": [{"ok": true, "id": ...} | {"ok": false, "row": i, "error": {...}}]}` (kết quả theo từng dòng)
  - `GET .../records/{id}`
  - `PATCH .../records/{id}`: header `If-Match` bắt buộc
  - Hình dạng `Record`: `{"id","app_id","collection","data","is_owner","version","seal_state","created_at","updated_at"}`. **Không trả `owner_sub`.**
  - Bảng mã lỗi `type`:

    | Slug | HTTP |
    |---|---|
    | `schema` | 422 |
    | `not-found` | 404 |
    | `forbidden` | 403 |
    | `precondition-required` | 428 |
    | `version-conflict` | 409 |
    | `record-sealed` | 409 |
    | `app-not-active` | 404 |

  - `async def next_sequence(conn, app_id: str, name: str) -> int`: cấp số trong cùng transaction với việc tạo bản ghi.
  - Mọi chuỗi trong `data` được chuẩn hóa NFC trước khi lưu (D5).
  - Ghi ledger `record.created` và `record.updated`. Khi người dùng được xem bản rõ trường PII thì ghi `field.revealed`, body `{fields: [...]}`.

- [ ] **Step 1: Viết test thất bại**

```python
async def test_create_assigns_sequence(api, tok_cv):          # app phong-ho-so ở trạng thái ACTIVE
    r1 = await api.post(URL_A, json={"trich_yeu": "QĐ 1"}, headers=tok_cv)
    r2 = await api.post(URL_A, json={"trich_yeu": "QĐ 2"}, headers=tok_cv)
    assert r1.status_code == 201 and r1.headers["etag"] == '"1"'
    assert (r1.json()["data"]["so_hieu"], r2.json()["data"]["so_hieu"]) == ("1/QĐ-SM", "2/QĐ-SM")

async def test_schema_violation_422(api, tok_cv):
    r = await api.post(URL_A, json={}, headers=tok_cv)        # thiếu trích yếu (bắt buộc)
    assert r.status_code == 422 and r.json()["type"].endswith("/schema")

async def test_idor_returns_404_and_logs(api, tok_owner_a, tok_owner_b, core_conn):   # AT-06
    rid = (await api.post(URL_T, json={"title": "t"}, headers=tok_owner_a)).json()["id"]
    r = await api.get(f"{URL_T}/{rid}", headers=tok_owner_b)
    assert r.status_code == 404
    assert await last_event_type(core_conn) == "policy.denied"

async def test_patch_requires_if_match(api, tok_owner_a, rid_t):
    assert (await api.patch(f"{URL_T}/{rid_t}", json={"title": "x"}, headers=tok_owner_a)).status_code == 428

async def test_patch_version_conflict(api, tok_owner_a, rid_t):
    r = await api.patch(f"{URL_T}/{rid_t}", json={"title": "x"}, headers={**tok_owner_a, "If-Match": '"9"'})
    assert r.status_code == 409 and r.json()["type"].endswith("/version-conflict")

async def test_sealed_record_patch_409(api, tok_owner_a, rid_t, owner_conn):          # AT-09
    await owner_conn.execute("UPDATE records SET seal_state='SEALED' WHERE id=$1", rid_t)
    r = await api.patch(f"{URL_T}/{rid_t}", json={"title": "x"}, headers={**tok_owner_a, "If-Match": '"1"'})
    assert r.status_code == 409 and r.json()["type"].endswith("/record-sealed")

async def test_pii_masked_and_reveal_logged(api, tok_owner_a, tok_reviewer, core_conn):  # AT-10
    rid = (await api.post(URL_T, json={"title": "t", "secret_code": "079203001234"}, headers=tok_owner_a)).json()["id"]
    assert (await api.get(f"{URL_T}/{rid}", headers=tok_owner_a)).json()["data"]["secret_code"] == "07********34"
    assert (await api.get(f"{URL_T}/{rid}", headers=tok_reviewer)).json()["data"]["secret_code"] == "079203001234"
    assert await last_event_type(core_conn) == "field.revealed"

async def test_nfd_input_stored_as_nfc(api, tok_owner_a):                              # RF1
    r = await api.post(URL_T, json={"title": "Nguyễn"}, headers=tok_owner_a)
    assert r.json()["data"]["title"] == "Nguyễn"

async def test_bulk_per_row_results(api, tok_cb):
    r = await api.post(URL_B + ":bulk", json=[{"ho_ten": "A", "su_kien": "S", "ngay_cap": "2026-11-20"}, {"ho_ten": "B"}], headers=tok_cb)
    assert [x["ok"] for x in r.json()["results"]] == [True, False]

async def test_inactive_app_404(api, tok_owner_a):
    assert (await api.get("/api/v1/apps/khong-ton-tai/collections/x/records", headers=tok_owner_a)).status_code == 404
```

- [ ] **Step 2:** Run `pytest core/tests/integration/test_records_api.py -v` · Expected: FAIL.
- [ ] **Step 3:** Cài đặt. Phân trang bằng keyset theo `(created_at, id)`. Bản ghi được trả về đã qua `mask_record`, trừ khi `decide(..., "reveal_pii", ...)` cho phép.
- [ ] **Step 4:** Run lại · Expected: PASS.
- [ ] **Step 5:** Commit `feat(records): generic records API with sequences, If-Match, masking, NFC, RFC 7807`

---

### Task 14: Upload, kiểm dịch, CAS, hàng đợi và worker (TV-B)

**Files:**
- Create: `core/src/dxos_core/objects/clamd.py`, `pdfcheck.py`, `storage.py`, `ingest.py`, `router.py`; `core/src/dxos_core/jobs/queue.py`; `core/src/dxos_core/worker.py`
- Create: các fixture trong `core/tests/fixtures/files/`:
  - `clean-text.pdf`
  - `image-only.pdf`
  - `encrypted.pdf`
  - `polyglot.bin` (header `%PDF-1.7\n` nối với nội dung ZIP)
  - `eicar.b64` (EICAR mã hóa base64, xem Global Constraints)
- Test: `core/tests/test_clamd.py`, `test_pdfcheck.py`, `core/tests/integration/test_ingest.py`

**Interfaces:**
- Consumes: `enforce` (Task 12); `append` (Task 9); `Settings` (Task 8).
- Produces:
  - `@dataclass ScanResult: clean: bool; signature: str | None`
  - `class ScannerUnavailable(Exception)`
  - `async def instream_scan(host: str, port: int, data: bytes, chunk: int = 65536, timeout_s: float = 30) -> ScanResult`
    - Gửi `b"zINSTREAM\0"`, rồi các khối dạng `[4 byte big-endian độ dài][dữ liệu]`, kết thúc bằng `b"\0\0\0\0"`.
    - Phản hồi `stream: OK` nghĩa là sạch. `stream: <sig> FOUND` nghĩa là nhiễm.
  - `@dataclass PdfCheck: ok: bool; reason: Literal["OK","EMPTY","TOO_LARGE","BAD_MAGIC","ENCRYPTED","PARSE_ERROR","NO_TEXT_LAYER"]`
  - `check_pdf(data: bytes, max_bytes: int) -> PdfCheck`: dùng pypdfium2; nếu không trang nào có chữ thì trả `NO_TEXT_LAYER`.
  - `class ObjectStore`, khởi tạo `(settings)`, gồm các phương thức:
    - `put_staging(upload_id: UUID, data: bytes) -> None`
    - `read_staging(upload_id) -> bytes`
    - `promote(upload_id, sha256: str) -> bool`: nếu object đã tồn tại thì trả `False` và **không ghi đè**
    - `move_to_quarantine(upload_id) -> None`
    - `read_object(sha256) -> bytes`: băm lại khi đọc, sai thì raise `IntegrityError`
  - Hàng đợi việc:
    - `async def enqueue(conn, kind: str, payload: dict, run_after: datetime | None = None) -> int`
    - `async def claim(conn, kinds: Sequence[str]) -> Job | None` (dùng `FOR UPDATE SKIP LOCKED`)
    - `async def complete(conn, job_id: int) -> None`
    - `async def retry_later(conn, job_id: int, delay_s: int) -> None`
  - `async def process_scan_job(ctx: WorkerContext, job: Job) -> None`, theo thứ tự (D1):
    1. Quét AV.
    2. Nếu `FOUND`: chuyển vào cách ly, đặt `INFECTED`, ghi `object.infected`.
    3. Nếu sạch: chạy `check_pdf`. Không đạt thì đặt `REJECTED` và ghi `object.rejected{reason}`.
    4. Nếu đạt: tính sha256, `promote`, chèn `objects` (bỏ qua nếu trùng), chèn `object_refs`, ghi `object.clean`.
    5. Nếu gặp `ScannerUnavailable`: gọi `retry_later(job, 30)`; upload vẫn ở `STAGING` (F8).
  - Routes:
    - `POST /api/v1/apps/{app}/collections/{col}/records/{id}/attachments`: multipart với trường `file`; enforce quyền `update`; vượt `max_mb` trả `413`; thành công trả `202 {"upload_id", "status": "STAGING"}` và ghi `upload.staged`.
    - `GET /api/v1/uploads/{upload_id}` → `{"status", "sha256"?, "reason"?}`
    - `GET /api/v1/objects/{sha256}?variant=original`: chỉ trả khi có bản ghi tham chiếu mà người gọi được `read`, và object ở trạng thái `CLEAN`. Các trường hợp khác trả `404`.

- [ ] **Step 1: Viết test thất bại**

```python
async def test_instream_found(fake_clamd):            # fake_clamd: server asyncio tạm, trả FOUND khi gặp EICAR
    assert await instream_scan(*fake_clamd, eicar()) == ScanResult(False, "Eicar-Test-Signature")

async def test_instream_unavailable():
    with pytest.raises(ScannerUnavailable): await instream_scan("127.0.0.1", 1, b"x", timeout_s=1)

@pytest.mark.parametrize("name,reason", [("clean-text.pdf", "OK"), ("image-only.pdf", "NO_TEXT_LAYER"),
    ("encrypted.pdf", "ENCRYPTED"), ("polyglot.bin", "PARSE_ERROR")])                    # RF2
def test_check_pdf(name, reason): assert check_pdf(fixture(name), 15 * 2**20).reason == reason
def test_check_pdf_empty_and_large():
    assert check_pdf(b"", 10).reason == "EMPTY"
    assert check_pdf(b"%PDF" + b"0" * 20, 10).reason == "TOO_LARGE"

@pytest.mark.integration
async def test_eicar_quarantined(api, tok_cv, run_worker_once, core_conn):          # AT-03
    up = await upload(api, tok_cv, eicar(), "a.pdf"); await run_worker_once()
    assert (await api.get(f"/api/v1/uploads/{up}", headers=tok_cv)).json()["status"] == "INFECTED"
    assert await last_event_type(core_conn) == "object.infected"

@pytest.mark.integration
async def test_staging_not_readable_even_by_admin(api, tok_cv, tok_admin_with_app_role):   # AT-04
    up = await upload(api, tok_cv, fixture("clean-text.pdf"), "a.pdf")         # chưa chạy worker
    sha = hashlib.sha256(fixture("clean-text.pdf")).hexdigest()
    assert (await api.get(f"/api/v1/objects/{sha}", headers=tok_admin_with_app_role)).status_code == 404

@pytest.mark.integration
async def test_cas_dedup_and_byte_change(api, tok_cv, run_worker_once, core_conn):  # AT-05 (phần CAS)
    data = fixture("clean-text.pdf")
    await upload(api, tok_cv, data, "1.pdf"); await upload(api, tok_cv, data, "2.pdf"); await run_worker_once(2)
    assert await core_conn.fetchval("SELECT count(*) FROM objects") == 1
    changed = data[:-2] + bytes([data[-2] ^ 1]) + data[-1:]
    await upload(api, tok_cv, changed, "3.pdf"); await run_worker_once()
    assert await core_conn.fetchval("SELECT count(*) FROM objects") in (1, 2)   # 2 nếu bản sửa vẫn là PDF hợp lệ, 1 nếu bị REJECTED

@pytest.mark.integration
async def test_clamd_down_stays_staging_and_retries(api, tok_cv, run_worker_once_with_clamd_down, core_conn):  # AT-20 (ClamAV)
    up = await upload(api, tok_cv, fixture("clean-text.pdf"), "a.pdf"); await run_worker_once_with_clamd_down()
    assert (await api.get(f"/api/v1/uploads/{up}", headers=tok_cv)).json()["status"] == "STAGING"
    assert await core_conn.fetchval("SELECT attempts FROM jobs ORDER BY id DESC LIMIT 1") == 1

@pytest.mark.integration
async def test_bad_job_does_not_stop_worker(run_worker_loop_with_poison_job): ...   # assert: job hợp lệ phía sau vẫn được xử lý
```

- [ ] **Step 2:** Run · Expected: FAIL.
- [ ] **Step 3:** Cài đặt. Kiểm tra `max_mb` lấy theo `AttachmentSpec`; nếu manifest không khai thì dùng `max_upload_mb_default`.
- [ ] **Step 4:** Run lại · Expected: PASS. Chạy thêm bài kiểm thử nightly với ClamAV thật: `pytest -m integration --real-clamav core/tests/integration/test_ingest.py::test_eicar_quarantined`.
- [ ] **Step 5:** Commit `feat(objects): upload, AV-first quarantine, PDF checks, content-addressed store, job queue`

---

### Task 15: STH ký qua OpenBao và endpoint xác minh (TV-C)

**Files:**
- Create: `core/src/dxos_core/kms/base.py`, `core/src/dxos_core/kms/openbao.py`, `core/src/dxos_core/ledger/sth.py`, `core/src/dxos_core/ledger/router.py`
- Create: `deploy/openbao/config.hcl`, `deploy/openbao/init.sh`, `docs/runbook-openbao.md`
- Create: `core/tests/helpers/local_signer.py` (**chỉ dùng trong test**)
- Test: `core/tests/test_sth.py`, `core/tests/integration/test_openbao_signer.py`

**Interfaces:**
- Consumes: `entries_bytes` (Task 9); `root`, `consistency_proof` (Task 3); `canonical_bytes` (Task 2).
- Produces:
  - `KeyName = Literal["seal-key", "sth-key"]`
  - `@dataclass SignResult: signature: bytes; key_version: int`
  - `class Signer(Protocol)`:
    - `async def sign(self, key: KeyName, data: bytes) -> SignResult`
    - `async def public_keys(self) -> dict[KeyName, dict[int, bytes]]`
  - `class KmsUnavailable(Exception)`
  - `class OpenBaoTransit(Signer)`, khởi tạo `(addr: str, token: str)`:
    - Ký: `POST /v1/transit/sign/{key}` với body `{"input": b64(data)}`, đọc `data.signature` dạng `vault:v<n>:<b64>`.
    - Lấy khóa công khai: `GET /v1/transit/keys/{key}` → `data.keys.<ver>.public_key`.
    - OpenBao bị khóa, trả 403 hoặc 5xx → raise `KmsUnavailable`.
  - `@dataclass TreeHead: tree_size: int; root_hash: str; ts: str; key_version: int; signature: str` (`root_hash` là hex, `signature` là base64)
  - `sth_signing_bytes(tree_size: int, root_hash: str, ts: str, key_version: int) -> bytes`: là `canonical_bytes` của 4 trường đó
  - `async def make_sth(conn, signer: Signer) -> TreeHead`: lấy STH mới; nếu ký lỗi thì **không** chèn `tree_heads` và ghi ledger `sth.published` khi thành công
  - `verify_sth(th: TreeHead, pubkey: bytes) -> bool`
  - Routes:
    - `GET /verify/v1/sth/latest`
    - `GET /verify/v1/sth/consistency?first=&second=` → `{"first", "second", "proof": [hex]}`; trả `400` nếu `first > second` hoặc `second > latest`
    - `GET /verify/v1/keys` → `{"seal-key": {"1": "<b64>"}, "sth-key": {...}}`
- **Thứ tự bắt buộc trong `make_sth`:**
  1. Ghi lá `sth.published` trước, với body `{tree_size_before}`.
  2. Sau đó tính root trên **toàn bộ** lá, bao gồm cả lá vừa ghi.
  3. Ký.
  4. Chèn `tree_heads`.

  Lý do: STH luôn phủ cả sự kiện công bố chính nó. **Cả 4 bước nằm trong một transaction**: nếu ký lỗi (`KmsUnavailable`) thì rollback toàn bộ, kể cả lá `sth.published`.
- `init.sh`:
  - Bật transit.
  - Tạo `seal-key` và `sth-key` với `type=ed25519 exportable=false`.
  - Tạo policy `dxos-core` chỉ cho phép `update` trên `transit/sign/seal-key`, `transit/sign/sth-key` và `read` trên `transit/keys/*`.
  - Thu hồi root token sau khi thiết lập xong.

- [ ] **Step 1: Viết test thất bại**

```python
async def test_sth_root_matches_proof_lib(core_conn, local_signer, seeded_entries):
    th = await make_sth(core_conn, local_signer)
    assert th.root_hash == root(await entries_bytes(core_conn)).hex() and th.tree_size == len(await entries_bytes(core_conn))

async def test_sth_signature_verifies_and_tamper_fails(core_conn, local_signer, seeded_entries):
    th = await make_sth(core_conn, local_signer); pk = (await local_signer.public_keys())["sth-key"][th.key_version]
    assert verify_sth(th, pk)
    assert not verify_sth(dataclasses.replace(th, root_hash="00" * 32), pk)

async def test_kms_unavailable_inserts_nothing(core_conn, failing_signer, seeded_entries):     # F8
    before = await core_conn.fetchval("SELECT count(*) FROM tree_heads")
    with pytest.raises(KmsUnavailable): await make_sth(core_conn, failing_signer)
    assert await core_conn.fetchval("SELECT count(*) FROM tree_heads") == before

async def test_consistency_endpoint_verifies(api, core_conn, local_signer):                   # AT-17 (phần STH)
    a = await make_sth(core_conn, local_signer); await add_entries(core_conn, 5); b = await make_sth(core_conn, local_signer)
    p = (await api.get(f"/verify/v1/sth/consistency?first={a.tree_size}&second={b.tree_size}")).json()["proof"]
    assert verify_consistency(a.tree_size, b.tree_size, bytes.fromhex(a.root_hash), bytes.fromhex(b.root_hash), [bytes.fromhex(x) for x in p])

async def test_consistency_bad_range_400(api):
    assert (await api.get("/verify/v1/sth/consistency?first=9&second=3")).status_code == 400

@pytest.mark.integration
async def test_openbao_sign_and_public_key(openbao_signer):           # cần OpenBao thật trong compose.test
    r = await openbao_signer.sign("sth-key", b"hello")
    pk = (await openbao_signer.public_keys())["sth-key"][r.key_version]
    Ed25519PublicKey.from_public_bytes(pk).verify(r.signature, b"hello")
```

- [ ] **Step 2:** Run · Expected: FAIL.
- [ ] **Step 3:** Cài đặt. Viết runbook mở khóa OpenBao: checklist lấy từ spec 16.4 và 11.6.
- [ ] **Step 4:** Run lại · Expected: PASS.
- [ ] **Step 5:** Commit `feat(ledger): signed tree heads via OpenBao transit, verify endpoints, runbook`

---

### Task 16: Neo GitHub, `dxos-witness` và endpoint quản trị neo (TV-C)

**Files:**
- Create: `core/src/dxos_core/ledger/anchor.py`; job `anchor_sth` trong `worker.py`; `core/src/dxos_core/admin/router.py` (`POST /admin/v1/anchor:run`, `GET /admin/v1/ledger/status`)
- Create: `witness/pyproject.toml` (gói `dxos-witness`; dependency: `dxos-proof`, `httpx`, `cryptography`; console script `dxos-witness`), `witness/src/dxos_witness/sync.py`, `witness/src/dxos_witness/cli.py`
- Create: `witness/template/.github/workflows/witness.yml` (chạy theo cron `0 */6 * * *`), `witness/template/README.md`
- Create: `docs/evidence/README.md` (nơi lưu ảnh chụp AT-18)
- Test: `core/tests/integration/test_anchor.py`, `witness/tests/test_sync.py`

**Interfaces:**
- Consumes: `TreeHead`, `verify_sth`, `make_sth`, các route verify (Task 15); `verify_consistency` (Task 3).
- Produces:
  - `sth_path(tree_size: int) -> str`: trả `f"sth/{tree_size:012d}.json"`
  - `class AnchorError(Exception)`, có `code: Literal["ANCHOR_CONFLICT","PUSH_FAILED"]`
  - `async def publish_sth(th: TreeHead, repo_dir: Path, git_ssh_command: str) -> str`
    - Ghi tệp `canonical_bytes(asdict(th))`, commit với message `sth <tree_size>`, `git push origin main`, trả commit sha.
    - Tệp đã tồn tại với nội dung **khác** thì raise `ANCHOR_CONFLICT`. **Không bao giờ ghi đè.**
  - Job `anchor_sth`: `make_sth` rồi `publish_sth`. Gặp `PUSH_FAILED` thì `retry_later(60)`.
  - `@dataclass SyncResult: status: Literal["OK","FIRST_RUN","REWRITE_DETECTED","INCONSISTENT","BAD_SIGNATURE","ANCHOR_MISMATCH"]; tree_size: int; detail: str`
  - `sync(server_url: str, anchor_dir: Path, state_dir: Path) -> SyncResult`, các bước:
    1. Lấy `sth/latest` và `keys`, kiểm chữ ký → nếu sai: `BAD_SIGNATURE`.
    2. So với tệp neo cùng `tree_size` nếu đã có → khác nhau: `ANCHOR_MISMATCH`.
    3. Đọc STH đã lưu gần nhất trong `state_dir`. Chưa có → lưu, trả `FIRST_RUN`.
    4. Cùng `tree_size` nhưng khác root → `REWRITE_DETECTED`.
    5. Nhỏ hơn → lấy consistency proof và kiểm. Sai → `INCONSISTENT`. Đúng → lưu, trả `OK`.
  - CLI: `dxos-witness sync --server URL --anchor-dir DIR --state-dir DIR`. Mã thoát `0` khi `OK` hoặc `FIRST_RUN`, mã `2` cho các trường hợp còn lại.

- [ ] **Step 1: Viết test thất bại**

```python
@pytest.mark.integration
async def test_publish_writes_file_and_commits(tmp_bare_repo_clone, th):
    sha = await publish_sth(th, tmp_bare_repo_clone, GIT_SSH)
    assert (tmp_bare_repo_clone / sth_path(th.tree_size)).is_file() and len(sha) == 40

@pytest.mark.integration
async def test_publish_never_overwrites(tmp_bare_repo_clone, th):
    await publish_sth(th, tmp_bare_repo_clone, GIT_SSH)
    with pytest.raises(AnchorError) as e: await publish_sth(dataclasses.replace(th, root_hash="ab" * 32), tmp_bare_repo_clone, GIT_SSH)
    assert e.value.code == "ANCHOR_CONFLICT"

def test_witness_first_run_then_ok(server, tmp_path):          # server: app ledger chạy trong process với local_signer
    assert sync(server.url, server.anchor_dir, tmp_path).status == "FIRST_RUN"
    server.add_entries(3); server.make_and_anchor_sth()
    assert sync(server.url, server.anchor_dir, tmp_path).status == "OK"

def test_witness_detects_full_rewrite(server, tmp_path):                                  # AT-16
    sync(server.url, server.anchor_dir, tmp_path)
    server.rebuild_log_with_different_entries(same_key=True); server.make_sth_without_anchor()
    assert sync(server.url, server.anchor_dir, tmp_path).status in ("REWRITE_DETECTED", "INCONSISTENT")

def test_witness_bad_signature(server, tmp_path):
    server.serve_tampered_signature()
    assert sync(server.url, server.anchor_dir, tmp_path).status == "BAD_SIGNATURE"

async def test_anchor_run_requires_admin(api, tok_cv):
    assert (await api.post("/admin/v1/anchor:run", headers=tok_cv)).status_code == 403
```

- [ ] **Step 2:** Run · Expected: FAIL.
- [ ] **Step 3:** Cài đặt.
- [ ] **Step 4:** Run lại · Expected: PASS.
- [ ] **Step 5: Thiết lập thủ công**
  - Tạo repo `dxos-transparency-log`; owner là trưởng nhóm và GV, cả hai bật 2FA.
  - Bật bảo vệ nhánh `main`: cấm force-push, cấm xóa, bắt lịch sử tuyến tính.
  - Thêm **deploy key có quyền ghi** (khóa riêng chỉ lưu trên VPS dưới dạng Docker secret).
  - **AT-18:** dùng deploy key thử `git push --force` → phải bị từ chối. Lưu ảnh chụp vào `docs/evidence/at18-force-push-rejected.png`.
- [ ] **Step 6:** Commit `feat(anchor): publish signed STH to protected repo; dxos-witness sync CLI and template`

---

### Task 17: E2E mốc M1 và release v0.1.0 (TV-A)

**Files:**
- Create: `tests/e2e/test_m1_flow.py`, `tests/e2e/conftest.py` (lấy token Keycloak thật qua client `dxos-test`)
- Create: `.github/workflows/release.yml`, `.github/workflows/nightly.yml`
- Modify: `CHANGELOG.md` (mục `[0.1.0] - 2026-11-09`), `BUILD.md`, `LICENSES-THIRD-PARTY.md`, `README.md` (thêm phần "Trạng thái v0.1.0")
- Create: `ops/seed_manifests.py` (đưa manifest `test-app` và `phong-ho-so` vào trạng thái `ACTIVE` bằng `save_manifest`; **chỉ dùng tạm** tới khi có installer ở Plan 02)

**Interfaces:**
- Consumes: mọi task trước đó.
- Produces:
  - Tag `v0.1.0`.
  - GitHub Release đính kèm:
    - `dxos-0.1.0.tar.gz`: tạo bằng `git archive --prefix=dxos-0.1.0/`
    - `sbom-0.1.0.cdx.json`: tạo bằng syft, định dạng CycloneDX
    - Wheel của `dxos-proof`, `dxos-core`, `dxos-witness`

- [ ] **Step 1: Viết test E2E thất bại**

Chạy trên stack p16 thật (`make up` + `ops/seed_manifests.py`):

```python
def test_m1_end_to_end(kc_token, base):
    cv = kc_token("chuyen_vien1"); adm = kc_token("admin1")
    rid = post(base, "/api/v1/apps/phong-ho-so/collections/van_ban/records", {"trich_yeu": "E2E"}, cv)["id"]
    bad = upload(base, rid, eicar(), cv); good = upload(base, rid, fixture("clean-text.pdf"), cv)
    assert wait_status(base, bad, cv) == "INFECTED" and wait_status(base, good, cv) == "CLEAN"   # AT-03
    th = post(base, "/admin/v1/anchor:run", {}, adm)
    assert th["tree_size"] > 0
    assert subprocess.run(["dxos-witness", "sync", "--server", base, "--anchor-dir", ANCHOR_CLONE,
                           "--state-dir", STATE], check=False).returncode == 0
```

Chạy kèm `pytest -m infra tests/infra` (AT-01 trên VPS).

- [ ] **Step 2:** Run `make up && python ops/seed_manifests.py && pytest tests/e2e/test_m1_flow.py -v` · Expected: FAIL trước khi nối hết các phần. Sửa tới khi PASS.
- [ ] **Step 3:** Viết `release.yml` chạy khi đẩy tag `v*.*.*`: build wheel, `git archive`, syft SBOM, tạo GitHub Release, dán mục CHANGELOG tương ứng vào phần mô tả release.
- [ ] **Step 4: Kiểm chứng tiêu chí M1**

Run `pytest -m "not infra" && pytest -m integration && pytest -m infra tests/infra && reuse lint`.
Expected: tất cả PASS, cụ thể các AT-01, 02, 03, 04, 05 (phần CAS), 06, 09, 10, 11, 12, 15, 16, 17 (phần STH).

- [ ] **Step 5: Phát hành**

```bash
git tag -a v0.1.0 -m "v0.1.0: Tier-0 phần 1"
git push origin v0.1.0
```

Expected: workflow release xanh; trang Release có đủ 3 nhóm tệp.

- [ ] **Step 6: Cổng năng suất** (Plan 00 mục 8)

Ghi tỷ lệ hoàn thành Tier-0 vào `docs/progress/2026-11-09.md` và quyết định hành động theo bảng cổng.

- [ ] **Step 7:** Commit `chore(release): v0.1.0, e2e M1, release and nightly workflows`

---

## Kiểm tra cuối Plan 01 (map về spec)

| Spec | Task |
|---|---|
| I1 / AT-01, AT-02 | 4, 10 |
| I2 / AT-03, AT-04, AT-05 (CAS) | 14 |
| I3 (một phần: lõi chỉ thử bằng `test-app`, D6) | 11, 12, 13 |
| I4 / AT-15, AT-16, AT-17 (STH), AT-18 | 9, 15, 16 |
| F1, F2 (trigger), F3, F4, F7, F8 (ClamAV, OpenBao khi ký STH) | 8, 9, 12, 13, 14, 15 |
| Records API spec 12.1, trừ workflow, niêm phong, `:check` | 13, 14 |
| API công khai `sth/*`, `keys` | 15 |
| PoF: LICENSE, SPDX/REUSE, CI, release v0.1.0, SBOM | 1, 17 |
| Ngoài phạm vi Plan 01 | Workflow, guard, niêm phong, đối soát, installer, SPA → Plan 02, 03 |
