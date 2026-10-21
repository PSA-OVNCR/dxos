# Ví dụ: Sổ mượn sách (`so-muon-sach`)

Ứng dụng nhỏ làm ví dụ cho hướng dẫn **[Viết app DX-OS trong 30 phút](../../docs/tutorial-app-30-phut.md)** (H13, AT-26).
Mục đích: chứng minh một app mới chỉ cần **một manifest, một BPMN và (tùy chọn) một giao diện mỏng**, không sửa `core/`.

- `manifest.yaml`: app `so-muon-sach` 1.0.0, vai trò `ban_doc` và `thu_thu`, collection `phieu_muon`
  (`so_phieu` do lõi cấp số `{n}/PM`; `ten_sach`, `nguoi_muon` (PII `NAME`), `ngay_muon`, `email` (PII `EMAIL`)), quy trình
  một bước `duyet_muon` (vai trò `thu_thu`, guard `not_same_actor:creator`), niêm phong khi quy trình kết thúc ở `approved`,
  `verify.public: true`, `require_file: false`.
- `bpmn/duyet-muon.bpmn`: một `userTask` và một cổng, kết thúc `approved` hoặc `rejected`; chỉ dùng phần tử trong danh sách cho
  phép của lõi (P2-D2).
- `web/`: SPA Vue 3 (gói npm `dxos-example-so-muon-sach`, phục vụ ở `/apps/so-muon-sach/`). Biểu mẫu và cột danh sách **sinh từ
  `client.manifest('so-muon-sach')`** (SDK `dxos-sdk-js`), không chép tay schema nào. Mã của đội dưới 150 dòng
  (`.ts` và `.vue` trong `web/src`, không tính dòng trống và chú thích; test `web/test/app.test.ts` đếm và chặn vượt).

## Kiểm thử

```bash
python -m pytest tests/apps -q                      # manifest + BPMN qua cùng bộ kiểm với App A/B; AT-14 quét cả examples/
npm run test -w dxos-example-so-muon-sach           # giao diện (cần Node 22, npm 11.6.2, đã npm ci)
```

`web/test/fixtures/manifest-view.json` là đúng thân `GET /api/v1/apps/so-muon-sach/manifest` mà lõi sẽ trả cho manifest này.
Test `test_example_web_fixture_is_exactly_what_the_core_would_serve` đỏ nếu `manifest.yaml` đổi mà tệp này chưa sinh lại:

```bash
python - <<'PY'
import json, yaml
from pathlib import Path
from dxos_core.registry.bpmn import check_against_manifest
from dxos_core.registry.client_view import client_view
from dxos_core.registry.validator import validate_manifest

root = Path("examples/so-muon-sach")
m = validate_manifest(yaml.safe_load((root / "manifest.yaml").read_text(encoding="utf-8")))
pm = check_against_manifest((root / m.workflow.bpmn).read_bytes(), m)
view = client_view(m, {t: sorted(v) for t, v in pm.decisions_by_task.items()})
(root / "web/test/fixtures/manifest-view.json").write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
```

## Cài lên stack

Từng bước, có mốc thời gian và dấu kiểm: [docs/tutorial-app-30-phut.md](../../docs/tutorial-app-30-phut.md). Tóm tắt:
`dxos app install examples/so-muon-sach` (admin A), `dxos app approve so-muon-sach 1.0.0` (admin B khác), gán vai trò
`app:so-muon-sach:*` trong console Keycloak, `make web-build`, mở `/apps/so-muon-sach/`.

Ví dụ này **không** nằm trong danh sách cài mặc định của `ops/e2e/install_apps.sh` (chỉ App A và App B).
Định danh của nó (`so-muon-sach`, `phieu_muon`, `ban_doc`, `thu_thu`) nằm trong danh sách quét AT-14: lõi không được chứa chúng.
