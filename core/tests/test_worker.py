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
