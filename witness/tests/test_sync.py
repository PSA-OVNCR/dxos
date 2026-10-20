# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test dxos-witness sync (Plan 01 Task 16; AT-16)."""

import json

import pytest
from dxos_witness.cli import main
from dxos_witness.sync import WitnessError, sync

# ---------- Các test do Plan 01 Task 16 quy định ----------

def test_witness_first_run_then_ok(server, tmp_path):          # server: ledger giả chạy trong process
    assert sync(server.url, server.anchor_dir, tmp_path).status == "FIRST_RUN"
    server.add_entries(3)
    server.make_and_anchor_sth()
    assert sync(server.url, server.anchor_dir, tmp_path).status == "OK"


def test_witness_detects_full_rewrite(server, tmp_path):                                  # AT-16
    sync(server.url, server.anchor_dir, tmp_path)
    server.rebuild_log_with_different_entries(same_key=True)
    server.make_sth_without_anchor()
    assert sync(server.url, server.anchor_dir, tmp_path).status in ("REWRITE_DETECTED", "INCONSISTENT")


def test_witness_bad_signature(server, tmp_path):
    server.serve_tampered_signature()
    assert sync(server.url, server.anchor_dir, tmp_path).status == "BAD_SIGNATURE"


# ---------- Bổ sung ----------

def test_no_change_is_ok_and_state_saved(server, tmp_path):
    sync(server.url, server.anchor_dir, tmp_path)
    r = sync(server.url, server.anchor_dir, tmp_path)
    assert (r.status, r.tree_size) == ("OK", 3)
    assert json.loads((tmp_path / "latest-sth.json").read_text())["tree_size"] == 3


def test_same_size_different_root_is_rewrite(server, tmp_path):
    sync(server.url, server.anchor_dir, tmp_path)
    n = len(server.entries)
    server.entries = []
    server.add_entries(n, tag="forged")
    server.make_sth_without_anchor()
    (server.anchor_dir / "sth/000000000003.json").unlink()   # kẻ tấn công cũng xóa được tệp neo của mình
    assert sync(server.url, server.anchor_dir, tmp_path).status == "REWRITE_DETECTED"


def test_anchor_mismatch(server, tmp_path):
    th = server.make_sth()
    forged = dict(th, root_hash="00" * 32)
    (server.anchor_dir / f"sth/{th['tree_size']:012d}.json").write_text(json.dumps(forged))
    assert sync(server.url, server.anchor_dir, tmp_path).status == "ANCHOR_MISMATCH"


def test_shrinking_log_is_rewrite(server, tmp_path):
    server.add_entries(4)
    server.make_and_anchor_sth()
    sync(server.url, server.anchor_dir, tmp_path)               # đã lưu cây cỡ 7
    server.entries = server.entries[:5]
    server.make_sth_without_anchor()
    assert sync(server.url, server.anchor_dir, tmp_path).status == "REWRITE_DETECTED"


def test_new_signing_key_without_anchor_is_bad_signature_or_inconsistent(server, tmp_path):
    sync(server.url, server.anchor_dir, tmp_path)
    server.rebuild_log_with_different_entries(same_key=False)
    server.make_sth_without_anchor()
    assert sync(server.url, server.anchor_dir, tmp_path).status in ("INCONSISTENT", "BAD_SIGNATURE")


def test_rejected_result_does_not_overwrite_state(server, tmp_path):
    sync(server.url, server.anchor_dir, tmp_path)
    server.rebuild_log_with_different_entries()
    server.make_sth_without_anchor()
    sync(server.url, server.anchor_dir, tmp_path)
    assert json.loads((tmp_path / "latest-sth.json").read_text())["tree_size"] == 3


def test_unreachable_server_raises(tmp_path):
    with pytest.raises(WitnessError):
        sync("http://127.0.0.1:1", tmp_path, tmp_path)


def test_cli_exit_codes(server, tmp_path, capsys):
    args = ["sync", "--server", server.url, "--anchor-dir", str(server.anchor_dir),
            "--state-dir", str(tmp_path), "--no-pull"]
    assert main(args) == 0                                     # FIRST_RUN
    assert "FIRST_RUN" in capsys.readouterr().out
    assert main(args) == 0                                     # OK
    server.serve_tampered_signature()
    assert main(args) == 2
    assert "BAD_SIGNATURE" in capsys.readouterr().out
    assert main(["sync", "--server", "http://127.0.0.1:1", "--anchor-dir", str(tmp_path),
                 "--state-dir", str(tmp_path), "--no-pull"]) == 2
