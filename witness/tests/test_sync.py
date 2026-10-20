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


# ---------- Sửa sau rà soát độc lập: lịch sử đã neo không viết lại được ----------

def _rewrite_after(server, keep: int, total: int) -> None:
    """Giữ ``keep`` lá đầu, viết lại phần sau, tổng ``total`` lá; ký STH nhưng không neo."""
    server.entries = server.entries[:keep]
    server.add_entries(total - keep, tag="forged")
    server.make_sth_without_anchor()


def test_rewrite_of_anchored_history_after_last_witness_run(server, tmp_path):     # rà soát #1, kịch bản A
    assert sync(server.url, server.anchor_dir, tmp_path).status == "FIRST_RUN"      # witness thấy cây 3
    server.add_entries(3)
    server.make_and_anchor_sth()                         # neo cây 6, witness chưa chạy
    _rewrite_after(server, keep=3, total=8)                                         # sửa lá 3..5
    r = sync(server.url, server.anchor_dir, tmp_path)
    assert r.status == "INCONSISTENT" and "6" in r.detail


def test_fresh_witness_checks_anchor_chain(server, tmp_path):                       # rà soát #1, kịch bản B
    server.add_entries(3)
    server.make_and_anchor_sth()
    _rewrite_after(server, keep=3, total=8)
    assert sync(server.url, server.anchor_dir, tmp_path / "moi").status == "INCONSISTENT"


def test_server_older_than_anchor_is_rewrite(server, tmp_path):
    server.add_entries(3)
    server.make_and_anchor_sth()                                                    # neo cây 6
    server.sths.append(server.sths[0])                   # máy chủ trả lại STH cây 3
    assert sync(server.url, server.anchor_dir, tmp_path).status == "REWRITE_DETECTED"


def test_forged_anchor_file_name(server, tmp_path):
    (server.anchor_dir / "sth/000000000003.json").rename(server.anchor_dir / "sth/000000000004.json")
    assert sync(server.url, server.anchor_dir, tmp_path).status == "ANCHOR_MISMATCH"


def test_honest_growth_with_many_anchors_ok(server, tmp_path):
    for _ in range(4):
        server.add_entries(2)
        server.make_and_anchor_sth()
    assert sync(server.url, server.anchor_dir, tmp_path).status == "FIRST_RUN"
    server.add_entries(1)
    server.make_sth_without_anchor()                                                # chưa kịp neo: vẫn OK
    r = sync(server.url, server.anchor_dir, tmp_path)
    state = json.loads((tmp_path / "latest-sth.json").read_text())
    assert r.status == "OK" and state["anchor_verified_size"] == 11


def test_rate_limited_then_ok(server, tmp_path):
    server.throttle = 2
    assert sync(server.url, server.anchor_dir, tmp_path).status == "FIRST_RUN"


def test_pinned_key_kept_when_server_adds_version(server, tmp_path):
    sync(server.url, server.anchor_dir, tmp_path)
    pinned = json.loads((tmp_path / "known-keys.json").read_text())["1"]
    server.extra_keys = {"2": "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="}
    assert sync(server.url, server.anchor_dir, tmp_path).status == "OK"
    keys = json.loads((tmp_path / "known-keys.json").read_text())
    assert keys["1"] == pinned and "2" in keys
