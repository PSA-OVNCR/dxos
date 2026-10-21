# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""E2E mốc M2, các phép thử tấn công (Plan 02 Task 15): task của app khác, thiếu ``If-Match``, manifest
nới chính sách sàn hoặc vượt namespace (AT-11, AT-12, qua CLI ``dxos``), rate-limit cổng công khai (AT-19),
OpenBao bị khóa trước task cuối (AT-20).

AT-20 chỉ chạy khi máy chạy test điều khiển được container OpenBao bằng ``docker`` (trên máy chủ, không trong
container của ``run_e2e.sh``) và có:
- ``DXOS_E2E_BAO_TOKEN``: token có quyền ``sudo`` trên ``sys/seal`` (root token tạo lại bằng
  ``bao operator generate-root``, thu hồi sau khi chạy);
- ``DXOS_E2E_BAO_UNSEAL_KEYS``: các unseal key cần để mở khóa, cách nhau bằng dấu phẩy.
Thiếu thì test AT-20 được bỏ qua (có lý do). Tên container: ``DXOS_E2E_OPENBAO_CONTAINER`` (mặc định
``dxos-openbao-1``).

Giới hạn của AT-20 ở E2E: chỉ chứng minh trường hợp OpenBao khóa **trước** task cuối. Trường hợp OpenBao hỏng
**sau** khi Flowable đã hoàn thành (``SEAL_PENDING`` rồi job tự hoàn tất) chỉ chứng minh được ở integration
test (Plan 02 Task 7, ``FlakySigner``), vì trên stack thật không chọn được thời điểm hỏng.
"""

import asyncio
import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
import yaml

pytestmark = [pytest.mark.infra, pytest.mark.e2e]

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "core/tests/fixtures"
OPENBAO = os.environ.get("DXOS_E2E_OPENBAO_CONTAINER", "dxos-openbao-1")


def _ready_a_record(stack) -> str:
    """Bản ghi App A có một PDF sạch, đã bắt đầu quy trình (đang chờ ``duyet_noi_dung``)."""
    a, col = stack.APP_A, stack.COL_A
    rid = stack.create(a, col, {"trich_yeu": "E2E tấn công", "nguoi_lien_he_cccd": "079203001235"},
                       "chuyen_vien1")["id"]
    up = stack.upload(a, col, rid, stack.clean_pdf(), "chuyen_vien1")
    assert stack.wait_upload(up, "chuyen_vien1") == "CLEAN"
    r = stack.start(a, col, rid, "chuyen_vien1")
    assert r.status_code == 200, r.text
    return rid


# ---------------------------------------------------------------- task và If-Match
def test_completing_a_task_of_another_app_is_404(stack):
    rid = _ready_a_record(stack)
    task = stack.task(stack.APP_A, rid, "truong_phong1", "duyet_noi_dung")
    v = stack.version(stack.APP_A, stack.COL_A, rid, "truong_phong1")
    # Task của App A gọi qua đường dẫn của App B, bởi người có vai trò App B.
    r = stack.complete(stack.APP_B, task["task_id"], "approve", "truong_clb1", version=v)
    assert r.status_code == 404, r.text
    # Cả người có vai trò đúng task cũng không đi vòng qua app khác được.
    r = stack.complete(stack.APP_B, task["task_id"], "approve", "truong_phong1", version=v)
    assert r.status_code == 404, r.text
    assert stack.task(stack.APP_A, rid, "truong_phong1", "duyet_noi_dung")["task_id"] == task["task_id"]


def test_complete_without_if_match_is_428(stack):
    rid = _ready_a_record(stack)
    task = stack.task(stack.APP_A, rid, "truong_phong1", "duyet_noi_dung")
    r = stack.complete(stack.APP_A, task["task_id"], "approve", "truong_phong1", version=None)
    assert r.status_code == 428, r.text


# ---------------------------------------------------------------- manifest qua CLI (AT-11, AT-12)
def _app_dir(tmp_path: Path, name: str, manifest: dict, bpmn: bytes | None = None) -> Path:
    d = tmp_path / name
    d.mkdir()
    text = yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
    (d / "manifest.yaml").write_text(text, encoding="utf-8")
    if bpmn is not None:
        (d / "bpmn").mkdir()
        (d / "bpmn/test-review.bpmn").write_bytes(bpmn)
    return d


def _fixture(name: str) -> dict:
    return yaml.safe_load((FIXTURES / f"manifest-{name}.yaml").read_text(encoding="utf-8"))


def _rejected(stack, app_dir: Path, code: str) -> None:
    out = stack.cli("app", "install", str(app_dir))
    assert out.returncode == 1, (out.returncode, out.stdout, out.stderr)
    assert code in out.stdout, out.stdout


def _never_stored(stack, *app_ids: str) -> None:
    out = stack.cli("--json", "app", "list")
    assert out.returncode == 0, out.stderr
    assert not {row["app_id"] for row in json.loads(out.stdout)} & set(app_ids)


def test_manifest_weakening_quarantine_is_rejected_by_cli(stack, tmp_path):                     # AT-11
    m = _fixture("test-app")
    m["app"]["id"] = "e2e-at11-quarantine"
    m["collections"]["item"]["attachments"]["quarantine"] = "optional"
    _rejected(stack, _app_dir(tmp_path, "q", m), "FLOOR_WEAKENED")
    _never_stored(stack, "e2e-at11-quarantine")


def test_manifest_with_unknown_guard_is_rejected_by_cli(stack, tmp_path):                       # AT-11
    m = _fixture("test-flow")
    m["app"]["id"] = "e2e-at11-guard"
    m["workflow"]["tasks"]["review"]["guards"] = ["attachments_clean", "teleport_to_approved"]
    bpmn = (FIXTURES / "bpmn/test-review.bpmn").read_bytes()
    _rejected(stack, _app_dir(tmp_path, "g", m, bpmn), "UNKNOWN_GUARD")
    _never_stored(stack, "e2e-at11-guard")


def test_manifest_claiming_foreign_role_is_rejected_by_cli(stack, tmp_path):                    # AT-12
    m = _fixture("test-app")
    m["app"]["id"] = "e2e-at12-namespace"
    m["roles"] = [*m["roles"], "app:other:x"]
    _rejected(stack, _app_dir(tmp_path, "n", m), "NAMESPACE_VIOLATION")
    _never_stored(stack, "e2e-at12-namespace")


# ---------------------------------------------------------------- AT-19
async def _burst(base: str, n: int) -> list[int]:
    """``n`` request **đồng thời** (không tuần tự: limit-req làm chậm phần trong burst thay vì từ chối), mỗi
    request kèm ``X-Forwarded-For`` giả khác nhau: Caddy không được tin header do client tự gửi."""
    async with httpx.AsyncClient(timeout=60, limits=httpx.Limits(max_connections=n)) as client:
        async def one() -> int:
            fake = f"203.0.113.{secrets.randbelow(254) + 1}"
            r = await client.get(f"{base}/verify/v1/seals/{'A' * 26}", headers={"X-Forwarded-For": fake})
            return r.status_code
        return list(await asyncio.gather(*(one() for _ in range(n))))


def test_public_verify_is_rate_limited_even_with_forged_forwarded_for(stack):                   # AT-19
    codes = asyncio.run(_burst(stack.base, 40))
    assert 429 in codes, codes
    assert set(codes) <= {404, 429}, codes


# ---------------------------------------------------------------- AT-20
def _bao(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    """``docker exec`` vào container OpenBao; bí mật chỉ đi qua biến môi trường, không nằm trong argv."""
    names = [k for k in env if k.startswith("BAO_")]
    cmd = ["docker", "exec", *[x for k in names for x in ("-e", k)], OPENBAO, *args]
    return subprocess.run(cmd, check=False, capture_output=True, text=True,  # noqa: S603
                          env={**os.environ, **env})


@pytest.fixture
def openbao_control():
    token, keys = os.environ.get("DXOS_E2E_BAO_TOKEN"), os.environ.get("DXOS_E2E_BAO_UNSEAL_KEYS")
    if shutil.which("docker") is None or not token or not keys:
        pytest.skip("AT-20 cần docker và DXOS_E2E_BAO_TOKEN, DXOS_E2E_BAO_UNSEAL_KEYS"
                    " (chạy trên máy chủ của stack)")

    def seal() -> None:
        out = _bao("bao", "operator", "seal", env={"BAO_TOKEN": token})
        assert out.returncode == 0, out.stderr

    def sealed() -> bool:
        status = _bao("bao", "status", "-format=json", env={})        # mã thoát 2 khi đang khóa: chỉ đọc JSON
        return json.loads(status.stdout)["sealed"] is True

    def unseal() -> None:
        for key in keys.split(","):
            if not sealed():
                break
            out = _bao("sh", "-c", 'bao operator unseal "$BAO_UNSEAL_KEY" >/dev/null',
                       env={"BAO_UNSEAL_KEY": key.strip()})
            assert out.returncode == 0, out.stderr
        assert not sealed(), "OpenBao vẫn khóa sau khi dùng hết unseal key"

    yield seal, unseal
    unseal()                                      # luôn mở khóa lại, kể cả khi test hỏng giữa chừng


def test_openbao_sealed_before_last_task_is_503_and_flowable_untouched(stack, openbao_control):   # AT-20
    seal, unseal = openbao_control
    a, col = stack.APP_A, stack.COL_A
    rid = _ready_a_record(stack)
    assert stack.complete_task(a, col, rid, "duyet_noi_dung", "approve", "truong_phong1").status_code == 200
    assert stack.pii_review(a, col, rid, "van_thu1").status_code == 200
    task = stack.task(a, rid, "giam_doc1", "ban_hanh")

    seal()
    r = stack.complete_task(a, col, rid, "ban_hanh", "approve", "giam_doc1")
    assert r.status_code == 503, r.text
    assert stack.task(a, rid, "giam_doc1", "ban_hanh")["task_id"] == task["task_id"]     # task vẫn ở Flowable
    assert stack.get(a, col, rid, "giam_doc1")["seal_state"] == "NONE"

    unseal()
    r = stack.complete_task(a, col, rid, "ban_hanh", "approve", "giam_doc1")
    assert r.status_code == 200, r.text
    stack.wait_sealed(a, col, rid, "giam_doc1")
