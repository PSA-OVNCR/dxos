# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""``make openapi`` (Plan 02 Task 15): ``docs/api/openapi.json`` được sinh lại y hệt từng byte, không phụ
thuộc tiến trình hay biến môi trường, và luôn khớp mã nguồn (quên chạy lại thì test này đỏ)."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("openapi_gen", ROOT / "ops/openapi.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

COMMITTED = ROOT / "docs/api/openapi.json"


def _render_in_subprocess(**env: str) -> bytes:
    code = ("import importlib.util, sys; s = importlib.util.spec_from_file_location('g', sys.argv[1]); "
            "m = importlib.util.module_from_spec(s); s.loader.exec_module(m); sys.stdout.buffer.write("
            "m.render().encode('utf-8'))")
    out = subprocess.run([sys.executable, "-c", code, str(ROOT / "ops/openapi.py")],  # noqa: S603
                         env={**os.environ, **env}, capture_output=True, check=True)
    return out.stdout


def test_committed_openapi_matches_regenerated_bytes():
    assert COMMITTED.read_bytes() == gen.render().encode("utf-8"), "chạy make openapi rồi commit"


def test_render_is_identical_across_processes_and_environment():
    a = _render_in_subprocess(PYTHONHASHSEED="1")
    b = _render_in_subprocess(PYTHONHASHSEED="2", DXOS_ORG_NAME="Tổ chức khác", DXOS_TIMEZONE="UTC")
    assert a == b == COMMITTED.read_bytes()


def test_check_mode_reports_stale_file(tmp_path, monkeypatch):
    stale = tmp_path / "openapi.json"
    stale.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(gen, "OUT", stale)
    monkeypatch.setattr(gen, "ROOT", tmp_path)
    assert gen.main(["--check"]) == 1
    assert gen.main([]) == 0 and gen.main(["--check"]) == 0


def test_openapi_lists_the_public_admin_and_app_routes():
    paths = json.loads(COMMITTED.read_text(encoding="utf-8"))["paths"]
    for p in ("/verify/v1/seals/{seal_id}", "/verify/v1/seals/{seal_id}:check",
              "/verify/v1/seals/{seal_id}/bundle",
              "/admin/v1/apps", "/admin/v1/apps/{app_id}:approve", "/admin/v1/health",
              "/api/v1/apps/{app}/collections/{col}/records/{rid}:erase-pii",
              "/api/v1/apps/{app}/tasks/{task_id}:complete"):
        assert p in paths, p


def test_makefile_has_openapi_target():
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "\nopenapi:\n\t$(PYTHON) ops/openapi.py\n" in text
