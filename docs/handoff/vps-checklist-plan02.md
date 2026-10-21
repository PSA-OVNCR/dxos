<!--
SPDX-FileCopyrightText: 2026 PSA_OVNCR
SPDX-License-Identifier: Apache-2.0
-->

# Việc trên VPS và của trưởng nhóm sau Plan 02 (M2)

*Tổng hợp 21/10/2026 từ báo cáo Task 15 (đã sửa theo review: bí mật nhập bằng `read -rs`, không đặt trên dòng lệnh). Mọi lệnh dưới đây CHƯA được chạy ở phiên cloud. Danh sách việc ngắn gọn: `docs/progress/2026-10-21-tong-ket-tien-do.md` mục 12.*


Chạy từ thư mục gốc repo, sau `git pull`. `<miền>` = `DXOS_DOMAIN`. Mọi lệnh dưới đây CHƯA được chạy trong phiên này.

## A. E2E trên dev-lite (máy có Docker)
```bash
# .env: DXOS_ORG_NAME=Công ty TNHH Sao Mai   (không đặt trong dấu nháy; tên này ghi vĩnh viễn vào tuyên bố khóa của stack)
docker compose -p dxos --env-file .env -f deploy/compose.yaml -f deploy/compose.dev-lite.yaml -f deploy/compose.e2e.yaml up -d --build
python ops/keycloak_upgrade.py --profile dev-lite          # stack có từ trước: thêm admin2, chuyen_vien_tp1, dxos-cli
# OpenBao mới: init/unseal/init.sh theo docs/runbook-openbao.md
mkdir -p ../e2e-out && docker compose -p dxos cp caddy:/data/caddy/pki/authorities/local/root.crt ../e2e-out/caddy-root.crt
docker run --rm --add-host=host.docker.internal:host-gateway \
  -e DXOS_ORG_NAME="$(grep '^DXOS_ORG_NAME=' .env | cut -d= -f2-)" \
  -v "$PWD":/src:ro -v "$PWD/../e2e-out":/out -v dxos_anchor-repo:/var/lib/dxos:ro \
  python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 sh /src/ops/e2e/run_e2e.sh
```
(Docker Desktop: `--add-host` không cần nhưng vô hại.) Kết quả: `../e2e-out/e2e-junit.xml`; AT-20 sẽ SKIPPED ở đây.

## B. E2E trên VPS hồ sơ p16 (ClamAV thật), gồm AT-19 và AT-20
1. Quyết định của trưởng nhóm (concern 1). Nếu đồng ý thêm tạm người dùng dev:
   ```bash
   python ops/keycloak_upgrade.py --profile dev-lite
   ```
2. Cài app bằng CLI (hai admin khác nhau; với người dùng dev tạm thì dùng token admin1/admin2):
   ```bash
   python3 -m venv .venv-e2e && . .venv-e2e/bin/activate
   pip install ./libs/dxos-proof ./witness ./cli "pytest>=8" "httpx>=0.27" "PyYAML>=6"
   dxos login --server https://admin.<miền>                                  # thành viên A
   DXOS_SERVER=https://admin.<miền> sh ops/e2e/install_apps.sh apps/phong-ho-so apps/chung-nhan
   dxos --server https://admin.<miền> app approve phong-ho-so 1.1.0          # thành viên B, máy của B
   dxos --server https://admin.<miền> app approve chung-nhan 1.1.0           # thành viên B
   ```
   (Nếu muốn giữ App B cho AT-13 ở bước E thì chỉ cài `apps/phong-ho-so` ở đây và chạy E2E App B trong bước E.)
3. AT-20 cần root token tạm của OpenBao (`init.sh` đã thu hồi root token):
   ```bash
   docker exec dxos-openbao-1 bao operator generate-root -init                 # ghi Nonce và OTP
   read -rs BAO_UNSEAL_KEY                                                      # dán một unseal key
   printf '%s\n' "$BAO_UNSEAL_KEY" | docker exec -i dxos-openbao-1 bao operator generate-root -nonce=<Nonce> -
   # lặp hai dòng trên với từng key tới đủ ngưỡng; ghi Encoded Token
   read -rs ENC && read -rs OTP && export ENC OTP
   read -rs DXOS_E2E_BAO_TOKEN < <(docker exec -e ENC -e OTP dxos-openbao-1 sh -c 'bao operator generate-root -decode="$ENC" -otp="$OTP"')
   export DXOS_E2E_BAO_TOKEN; unset ENC OTP
   read -rs DXOS_E2E_BAO_UNSEAL_KEYS && export DXOS_E2E_BAO_UNSEAL_KEYS          # key1,key2,... (dấu phẩy)
   ```
4. Chạy E2E (từ IP nằm trong `DXOS_ADMIN_ALLOWED_IPS`):
   ```bash
   unset SSL_CERT_FILE                                  # chứng chỉ VPS do CA công khai cấp; chỉ đặt khi dùng CA nội bộ
   DXOS_E2E_REQUIRE=1 DXOS_E2E_BASE=https://<miền> DXOS_E2E_ADMIN_BASE=https://admin.<miền> \
   DXOS_E2E_ANCHOR_REMOTE=https://github.com/PSA-OVNCR/dxos-transparency-log.git \
   DXOS_ORG_NAME='<như .env>' \
   python -m pytest -p no:cacheprovider -m e2e tests/e2e -v -rs --junitxml=../e2e-junit-vps.xml
   BAO_TOKEN=$DXOS_E2E_BAO_TOKEN docker exec -e BAO_TOKEN dxos-openbao-1 bao token revoke -self   # thu hồi root token tạm
   unset DXOS_E2E_BAO_TOKEN DXOS_E2E_BAO_UNSEAL_KEYS
   ```
5. Gỡ người dùng dev và client `dxos-test` (nếu đã thêm ở bước 1; lệnh kcadm chưa chạy thử):
   ```bash
   read -rs KC_CLI_PASSWORD && export KC_CLI_PASSWORD      # KEYCLOAK_ADMIN_PASSWORD trong .env
   KC="docker exec -e KC_CLI_PASSWORD dxos-keycloak-1 /opt/keycloak/bin/kcadm.sh"
   $KC config credentials --config /tmp/kc.cfg --server http://localhost:8080/auth --realm master --user admin
   for u in chuyen_vien1 chuyen_vien_tp1 truong_phong1 giam_doc1 van_thu1 nhan_vien1 can_bo_clb1 truong_clb1 owner_a1 owner_b1 admin1 admin2; do
     id=$($KC get users --config /tmp/kc.cfg -r dxos -q username=$u -q exact=true --fields id --format csv --noquotes)
     [ -n "$id" ] && $KC delete users/$id --config /tmp/kc.cfg -r dxos
   done
   cid=$($KC get clients --config /tmp/kc.cfg -r dxos -q clientId=dxos-test --fields id --format csv --noquotes)
   [ -n "$cid" ] && $KC delete clients/$cid --config /tmp/kc.cfg -r dxos
   docker exec dxos-keycloak-1 rm -f /tmp/kc.cfg; unset KC_CLI_PASSWORD
   ```
   (Cùng bộ lệnh đã có trong repo: `docs/evidence/README.md`, mục "Người dùng dev tạm trên VPS".)
6. Ghi `docs/progress/2026-11-xx-m2-e2e.md` theo mẫu `docs/progress/2026-10-20-task17-e2e.md` (lệnh, commit, junit).

## C. Gắn tag v0.2.0 (chỉ khi v0.1.0 đã có và trưởng nhóm đồng ý; hành động công khai)
```bash
sed -i 's/^version = "0.1.0"$/version = "0.2.0"/' libs/dxos-proof/pyproject.toml core/pyproject.toml witness/pyproject.toml cli/pyproject.toml
sed -i 's/^__version__ = "0.1.0"$/__version__ = "0.2.0"/' core/src/dxos_core/__init__.py witness/src/dxos_witness/__init__.py cli/src/dxos_cli/__init__.py
make openapi
sed -i 's/^## \[0.2.0\] - Chưa phát hành$/## [0.2.0] - <YYYY-MM-DD ngày gắn tag>/' CHANGELOG.md
make check
git commit -am "chore(release): v0.2.0 — e2e M2, AT-13 reuse proof, manifest guide, OpenAPI"
git push origin main
git tag -a v0.2.0 -m "v0.2.0: Tier-0 hoàn tất (workflow, niêm phong, đối soát, installer)"
git push origin v0.2.0
gh run watch "$(gh run list --workflow release --limit 1 --json databaseId -q '.[0].databaseId')"
gh release view v0.2.0          # phải có tar.gz, SBOM, 4 wheel, trust-core-image-0.2.0.txt và digest trong mô tả
```

## D. Đồng ý đẩy image lên GHCR (đi cùng bước C; job `image` tự đẩy khi có tag)
- Sau lần đẩy đầu, mở GitHub → PSA-OVNCR → Packages → `trust-core` → Package settings → đổi Public (hành động công khai),
  hoặc trên VPS: `read -rs GHCR_PAT && printf '%s' "$GHCR_PAT" | docker login ghcr.io -u <tài khoản> --password-stdin; unset GHCR_PAT`.
- Kiểm: `docker pull ghcr.io/psa-ovncr/trust-core@sha256:<digest>`.
- Ghi digest vào `LICENSES-THIRD-PARTY.md` (bảng "Image của dự án", cột Digest) và commit.

## E. AT-13 trên VPS (image đã phát hành)
```bash
# .env: DXOS_TRUST_CORE_DIGEST=<digest từ trang Release>; DXOS_ALLOW_SELF_APPROVAL=false
docker compose -p dxos --env-file .env -f deploy/compose.yaml -f deploy/compose.p16.yaml \
  -f deploy/compose.anchor.yaml -f deploy/compose.release.yaml up -d
python ops/keycloak_upgrade.py
docker inspect -f '{{.Config.Image}}' dxos-trust-core-api-1      # ghcr.io/psa-ovncr/trust-core@sha256:<digest>
# App A cài trước (bước B.2 chỉ với apps/phong-ho-so); App B CHƯA cài.
. .venv-e2e/bin/activate && dxos login --server https://admin.<miền>        # thành viên A
DXOS_TRUST_CORE_DIGEST=<digest> DXOS_SERVER=https://admin.<miền> \
DXOS_E2E_BASE=https://<miền> DXOS_E2E_ADMIN_BASE=https://admin.<miền> DXOS_ORG_NAME='<như .env>' \
ops/at13_reuse.sh
# khi script in "chờ người duyệt thứ hai": thành viên B chạy trên máy của B
dxos --server https://admin.<miền> app approve chung-nhan 1.1.0
git add docs/evidence/at13-reuse.txt && git commit -m "docs(evidence): AT-13 reuse proof on the released image"
```
(Bước e2e App B trong script cần người dùng dev: concern 1.)

## F. AT-18, witness, pháp lý, cổng năng suất
- AT-18: theo `docs/runbook-anchor.md`, chụp `docs/evidence/at18-force-push-rejected.png`.
- Witness độc lập: một lượt chạy xanh từ repo dựng theo https://github.com/PSA-OVNCR/dxos-witness-kit; ghi link repo
  witness, người chạy, ngày vào `docs/evidence/README.md`.
- `docs/legal-mapping.md`, mục "Thành viên đã đọc toàn văn": mỗi thành viên đọc toàn văn từng điều rồi tự điền tên và
  ngày đọc; điền luôn cột "Điểm của Điều 14 khoản 1" trong `docs/runbook-pii-erasure.md` và chốt thời hạn giữ backup.
- Cổng năng suất M2: trưởng nhóm viết `docs/progress/2026-11-16.md` sau khi A–E xong (theo dạng
  `docs/progress/2026-10-21-tong-ket-tien-do.md`), rồi commit.

---

