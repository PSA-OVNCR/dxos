# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Unit test khung worker: heartbeat làm healthcheck cho container trust-core-worker."""

import os
import time

from dxos_core import worker


def test_heartbeat_fresh(tmp_path):
    hb = tmp_path / "hb"
    worker.touch_heartbeat(hb)
    assert worker.heartbeat_fresh(hb, max_age=60)


def test_heartbeat_stale(tmp_path):
    hb = tmp_path / "hb"
    worker.touch_heartbeat(hb)
    old = time.time() - 120
    os.utime(hb, (old, old))
    assert not worker.heartbeat_fresh(hb, max_age=60)


def test_heartbeat_missing(tmp_path):
    assert not worker.heartbeat_fresh(tmp_path / "khong-co", max_age=60)


def test_check_cli_exit_codes(tmp_path):
    hb = tmp_path / "hb"
    assert worker.main(["--check", "--heartbeat", str(hb)]) == 1
    worker.touch_heartbeat(hb)
    assert worker.main(["--check", "--heartbeat", str(hb)]) == 0


async def test_run_once_without_db_does_not_touch_heartbeat(settings, tmp_path):
    hb = tmp_path / "hb"
    await worker.run(settings, heartbeat=hb, once=True)
    assert not hb.exists()


async def test_run_loop_survives_errors_inside_iteration(settings, tmp_path, monkeypatch):   # rà soát #10
    """Lỗi bất ngờ trong một vòng (DB rớt khi claim...) không được làm worker thoát."""
    calls = {"n": 0}

    class FakeConn:
        async def fetchval(self, *_):
            return 1

    class FakeAcquire:
        async def __aenter__(self):
            return FakeConn()

        async def __aexit__(self, *a):
            return False

    class FakePool:
        def acquire(self, timeout=None):
            return FakeAcquire()

        async def close(self):
            pass

    async def fake_pool(*a, **k):
        return FakePool()

    def boom(*a, **k):
        calls["n"] += 1
        if calls["n"] >= 3:
            raise KeyboardInterrupt  # dừng vòng lặp của test
        raise RuntimeError("DB rớt")
    monkeypatch.setattr(worker, "create_pool", fake_pool)
    monkeypatch.setattr(worker, "_make_context", boom)
    import pytest
    with pytest.raises(KeyboardInterrupt):
        await worker.run(settings, heartbeat=tmp_path / "hb", interval=0)
    assert calls["n"] == 3
