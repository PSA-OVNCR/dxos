# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""``ops/backup.sh``, ``ops/restore.sh``, ``ops/at21_drill.sh`` (Plan 04 Task 12, S4, AT-21, P4-D9).

``docker`` và ``dxos-witness`` là bản giả đặt đầu PATH, ghi mọi lời gọi vào một tệp log (một lời gọi một dòng)
như ``test_deploy_sh.py``. ``openssl`` là bản **thật** (bọc để ghi lại đối số): mã hóa, giải mã và việc mật
khẩu sai bị phát hiện đều chạy thật. Chạy thật trên laptop và VPS là việc V43."""

import hashlib
import io
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ("backup.sh", "restore.sh", "at21_drill.sh")
LIB = "backup_lib.sh"
PASSPHRASE = "correct-horse-battery-staple-0001"
OTHER_PASSPHRASE = "a-completely-different-passphrase-9"
MEMBERS = ["MANIFEST.txt", "SHA256SUMS", "pg/core-db.dump", "pg/kc-db.dump", "pg/flowable-db.dump",
           "volumes/seaweedfs-data.tar", "volumes/openbao-data.tar"]
ENC_FLAGS = "enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass file:"
PRE_STH = "42 " + "ab" * 32
POST_STH = "42 " + "ab" * 32
SEAL = "PHS-2026-000001"
KEYS = "ef" * 32
OBJECTS = "1 " + "cd" * 32

FAKE_DOCKER = r"""#!/bin/sh
echo "docker $*" >> "$FAKE_LOG"
echo "${MSYS_NO_PATHCONV:-unset}" >> "$FAKE_LOG.msys"
case "$1" in
  ps)
    svc=""; proj=""
    for a; do
      case $a in
        label=com.docker.compose.service=*) svc=${a#label=com.docker.compose.service=} ;;
        label=com.docker.compose.project=*) proj=${a#label=com.docker.compose.project=} ;;
      esac
    done
    if [ -n "$svc" ]; then
      case " ${FAKE_NO_SERVICE:-} " in *" $svc "*) exit 0 ;; esac
      echo "cid-$proj-$svc"
    else
      printf '%s' "${FAKE_EXISTING_CONTAINERS:-}"
    fi ;;
  volume)
    case "$2" in
      ls) printf '%s' "${FAKE_EXISTING_VOLUMES:-}" ;;
      create) [ -z "${FAKE_FAIL_VOLUME:-}" ] || { echo "volume create failed" >&2; exit 1; } ;;
      inspect) case " ${FAKE_EXISTING_VOLUME_NAMES:-} " in *" $3 "*) exit 0 ;; *) exit 1 ;; esac ;;
    esac ;;
  pause) [ -z "${FAKE_FAIL_PAUSE:-}" ] || { echo "cannot pause" >&2; exit 1; } ;;
  unpause) ;;
  exec)
    case "$*" in
      *pg_dump*)
        db=""; prev=""
        for a; do [ "$prev" = -d ] && db=$a; prev=$a; done
        echo "PGDMP-FAKE:$2:$db" ;;
      *pg_restore*) n=$(ls "$FAKE_STDIN" | wc -l); cat > "$FAKE_STDIN/pg-$n" ;;
      *"python -c"*)
        case "$2" in *dxos-restore*) ph=POST ;; *) ph=PRE ;; esac
        for last; do :; done
        case "$*" in
          *ObjectStore*) what=OBJECTS ;; *"/verify/v1/keys"*) what=KEYS ;; *) what="" ;;
        esac
        [ -z "$what" ] || [ -z "$(printenv "FAKE_FAIL_${what}_${ph}")" ] || exit 1
        case "$*" in
          *ObjectStore*) printenv "FAKE_${ph}_OBJECTS"; exit 0 ;;
          *"/verify/v1/keys"*) printenv "FAKE_${ph}_KEYS"; exit 0 ;;
          *"/sth/latest"*) printenv "FAKE_${ph}_STH" ;;
          *) printenv "FAKE_${ph}_BUNDLE_STH" ;;
        esac
        echo "{\"fake\":\"$ph\"}" ;;
      *"bao status"*) [ -z "${FAKE_BAO_SEALED:-}" ] || exit 2 ;;
      *"operator unseal"*)
        [ -n "$BAO_DXOS_UNSEAL" ] && echo "unseal-env-present" >> "$FAKE_LOG.env" ;;
    esac ;;
  run)
    case "$*" in
      *" -i "*) n=$(ls "$FAKE_STDIN" | wc -l); cat > "$FAKE_STDIN/run-$n"
                [ -z "${FAKE_FAIL_EXTRACT:-}" ] || exit 1 ;;
      *"tar -cf -"*)
        for a; do
          case $a in
            --volumes-from) next=1 ;;
            *) [ -n "${next:-}" ] && { vf=$a; next=; } ;;
          esac
        done
        case " ${FAKE_FAIL_TAR:-} " in *" $vf "*) echo "tar failed" >&2; exit 1 ;; esac
        case " ${FAKE_TAR_SLEEP:-} " in *" $vf "*) sleep 30 ;; esac
        echo "TAR-FAKE:$vf" ;;
    esac ;;
  compose)
    case "$*" in
      *" up "*) [ -z "${FAKE_FAIL_UP:-}" ] || { echo "container x is unhealthy" >&2; exit 1; } ;;
    esac ;;
esac
exit 0
"""
FAKE_OPENSSL = """#!/bin/sh
echo "openssl $*" >> "$FAKE_LOG.openssl"
echo "${MSYS_NO_PATHCONV:-unset}" >> "$FAKE_LOG.msys-openssl"
if [ -n "${FAKE_OPENSSL_FAIL:-}" ]; then cat > /dev/null 2>&1 || true; exit 1; fi
exec "$REAL_OPENSSL" "$@"
"""
FAKE_WITNESS = """#!/bin/sh
echo "dxos-witness $*" >> "$FAKE_LOG"
case " ${FAKE_WITNESS_FAIL:-} " in *" $(basename "$2") "*) echo "INVALID x"; exit 2 ;; esac
echo "VALID ok"
exit 0
"""
FAKE_BACKUP = """#!/bin/bash
echo "backup.sh $*" >> "$FAKE_LOG"
[ -z "${FAKE_BACKUP_FAIL:-}" ] || exit 3
mkdir -p "$1"
printf 'x' > "$1/dxos-backup-20261023T000000Z.tar.enc"
printf 'y  dxos-backup-20261023T000000Z.tar.enc\\n' > "$1/dxos-backup-20261023T000000Z.tar.enc.sha256"
"""
FAKE_RESTORE = """#!/bin/bash
echo "restore.sh $* DXOS_DOMAIN=${DXOS_DOMAIN:-}" >> "$FAKE_LOG"
[ -z "${FAKE_RESTORE_FAIL:-}" ] || exit 4
"""


class Result:
    def __init__(self, proc: subprocess.CompletedProcess, world: "World"):
        self.returncode, self.stdout, self.stderr = proc.returncode, proc.stdout, proc.stderr
        self.out = proc.stdout + proc.stderr
        self.calls = world.log.read_text(encoding="utf-8").splitlines() if world.log.exists() else []
        self.text = "\n".join(self.calls)
        self.docker = [c for c in self.calls if c.startswith("docker ")]
        self.openssl = world.openssl_calls()

    def order(self, needles: list[str]) -> bool:
        i = 0
        for call in self.calls:
            if i < len(needles) and needles[i] in call:
                i += 1
        return i == len(needles)

    def index(self, needle: str) -> int:
        return next(i for i, c in enumerate(self.calls) if needle in c)


class World:
    """Một bản sao repo tạm có ``ops/``, ``.secrets/``, ``.env`` và PATH giả."""

    def __init__(self, tmp_path: Path):
        self.root = tmp_path
        self.repo = (tmp_path / "repo").resolve()
        self.bin = tmp_path / "bin"
        self.tmp = tmp_path / "tmp"
        self.out = tmp_path / "out"
        self.stdin = tmp_path / "stdin"
        self.log = tmp_path / "calls.log"
        self.env_extra: dict[str, str] = {}
        (self.repo / "ops").mkdir(parents=True)
        (self.repo / "deploy").mkdir()
        (self.repo / ".secrets").mkdir()
        for p in (self.bin, self.tmp, self.stdin):
            p.mkdir()
        for name in (*SCRIPTS, LIB):
            shutil.copy2(ROOT / "ops" / name, self.repo / "ops" / name)
        (self.repo / ".env").write_text("DXOS_DOMAIN=dxos.example.test\n", encoding="utf-8")
        for f in ("compose.yaml", "compose.p16.yaml", "compose.p8.yaml"):
            (self.repo / "deploy" / f).write_text("services: {}\n", encoding="utf-8")
        self.set_passphrase(PASSPHRASE)
        real = shutil.which("openssl")
        assert real, "cần openssl thật"
        self.real_openssl = real
        fakes = (("docker", FAKE_DOCKER), ("openssl", FAKE_OPENSSL), ("dxos-witness", FAKE_WITNESS))
        for name, body in fakes:
            (self.bin / name).write_text(body, encoding="utf-8")
            (self.bin / name).chmod(0o755)

    def set_passphrase(self, text: str | None) -> None:
        p = self.repo / ".secrets/backup-passphrase"
        p.unlink(missing_ok=True)
        if text is not None:
            p.write_text(text + "\n", encoding="utf-8")

    def fake_steps(self) -> None:
        """Thay backup.sh, restore.sh bằng bản giả: kiểm riêng thứ tự và đối số của at21_drill.sh."""
        for name, body in (("backup.sh", FAKE_BACKUP), ("restore.sh", FAKE_RESTORE)):
            (self.repo / "ops" / name).write_text(body, encoding="utf-8")

    def openssl_calls(self) -> list[str]:
        p = Path(str(self.log) + ".openssl")
        return p.read_text(encoding="utf-8").splitlines() if p.exists() else []

    def run(self, script: str, *args: str, **env: str) -> Result:
        self.log.unlink(missing_ok=True)
        for suffix in (".openssl", ".env", ".msys", ".msys-openssl"):
            Path(str(self.log) + suffix).unlink(missing_ok=True)
        base = {k: v for k, v in os.environ.items() if not k.startswith(("DXOS_", "FAKE_", "BAO_"))}
        base.update({"PATH": f"{self.bin}{os.pathsep}{base['PATH']}", "FAKE_LOG": str(self.log),
                     "FAKE_STDIN": str(self.stdin), "REAL_OPENSSL": self.real_openssl,
                     "TMPDIR": str(self.tmp),
                     "FAKE_PRE_STH": PRE_STH, "FAKE_POST_STH": POST_STH,
                     "FAKE_PRE_BUNDLE_STH": PRE_STH, "FAKE_POST_BUNDLE_STH": POST_STH,
                     "FAKE_PRE_KEYS": KEYS, "FAKE_POST_KEYS": KEYS,
                     "FAKE_PRE_OBJECTS": OBJECTS, "FAKE_POST_OBJECTS": OBJECTS,
                     **self.env_extra, **env})
        proc = subprocess.run(["bash", str(self.repo / "ops" / script), *args], env=base,  # noqa: S603, S607
                              capture_output=True, text=True, check=False, timeout=120, cwd=self.repo)
        return Result(proc, self)

    def backup(self, out: Path | None = None, **env: str) -> Result:
        return self.run("backup.sh", str(out or self.out), **env)

    def bundle(self) -> Path:
        found = sorted(self.out.glob("dxos-backup-*.tar.enc"))
        assert len(found) == 1, found
        return found[0]

    def restore(self, bundle: Path, *args: str, **env: str) -> Result:
        return self.run("restore.sh", str(bundle), *args, **env)

    def seed_stdin_clear(self) -> None:
        for f in self.stdin.iterdir():
            f.unlink()

    def leftover_staging(self) -> list[str]:
        return sorted(p.name for p in self.tmp.iterdir())


@pytest.fixture
def world(tmp_path):
    if shutil.which("bash") is None or shutil.which("openssl") is None:
        pytest.skip("cần bash và openssl")
    return World(tmp_path)


def make_bundle(world: World, passphrase: str = PASSPHRASE) -> Path:
    world.set_passphrase(passphrase)
    r = world.backup()
    assert r.returncode == 0, r.out
    return world.bundle()


def reencrypt(world: World, bundle: Path, members: dict[str, bytes], passphrase: str = PASSPHRASE,
              links: dict[str, tuple[bytes, str]] | None = None) -> None:
    """Thay nội dung gói bằng một tar khác (mã hóa đúng khóa) và sửa .sha256: kẻ sửa gói biết mật khẩu."""
    tar_path = world.root / "forged.tar"
    with tarfile.open(tar_path, "w") as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        for name, (kind, target) in (links or {}).items():      # kind: tarfile.SYMTYPE hoặc LNKTYPE
            info = tarfile.TarInfo(name)
            info.type, info.linkname = kind, target
            tf.addfile(info)
    pf = world.root / "forged.pass"
    pf.write_text(passphrase + "\n", encoding="utf-8")
    subprocess.run([world.real_openssl, "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "600000", "-salt",  # noqa: S603
                    "-pass", f"file:{pf}", "-in", str(tar_path), "-out", str(bundle)], check=True)
    Path(str(bundle) + ".sha256").write_text(
        f"{hashlib.sha256(bundle.read_bytes()).hexdigest()}  {bundle.name}\n", encoding="utf-8")


# ============================================================ backup.sh
def test_backup_encrypts_and_writes_checksum(world):
    r = world.backup()
    assert r.returncode == 0, r.out
    names = sorted(p.name for p in world.out.iterdir())
    enc = world.bundle()
    assert re.fullmatch(r"dxos-backup-\d{8}T\d{6}Z\.tar\.enc", enc.name)
    assert names == [enc.name, enc.name + ".sha256"]              # không còn tệp nào khác ở thư mục đích
    raw = enc.read_bytes()
    assert raw.startswith(b"Salted__")                            # openssl enc có muối
    assert b"PGDMP-FAKE" not in raw and b"TAR-FAKE" not in raw    # nội dung không nằm trần trong gói
    sums = (world.out / (enc.name + ".sha256")).read_text(encoding="utf-8")
    assert sums == f"{hashlib.sha256(raw).hexdigest()}  {enc.name}\n"
    # đúng lệnh P4-D9, mật khẩu qua -pass file: trỏ .secrets/backup-passphrase của repo
    enc_calls = [c for c in r.openssl if ENC_FLAGS in c]
    assert len(enc_calls) == 1
    assert f"{ENC_FLAGS}{world.repo}/.secrets/backup-passphrase" in enc_calls[0]
    # mật khẩu không bao giờ nằm trên dòng lệnh hay trong đầu ra
    assert PASSPHRASE not in r.text + "\n".join(r.openssl) + r.out
    assert world.leftover_staging() == []                         # thư mục tạm đã xóa


def test_backup_bundle_decrypts_to_the_expected_members(world):
    r = world.backup()
    assert r.returncode == 0, r.out
    plain = world.root / "plain.tar"
    pf = world.repo / ".secrets/backup-passphrase"
    subprocess.run([world.real_openssl, "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "600000",  # noqa: S603
                    "-pass", f"file:{pf}", "-in", str(world.bundle()), "-out", str(plain)], check=True)
    with tarfile.open(plain) as tf:
        assert sorted(tf.getnames()) == sorted(MEMBERS)
        assert tf.extractfile("pg/core-db.dump").read() == b"PGDMP-FAKE:cid-dxos-core-db:dxos\n"
        assert tf.extractfile("pg/kc-db.dump").read() == b"PGDMP-FAKE:cid-dxos-kc-db:keycloak\n"
        assert tf.extractfile("pg/flowable-db.dump").read() == b"PGDMP-FAKE:cid-dxos-flowable-db:flowable\n"
        assert tf.extractfile("volumes/seaweedfs-data.tar").read() == b"TAR-FAKE:cid-dxos-seaweedfs:ro\n"
        assert tf.extractfile("volumes/openbao-data.tar").read() == b"TAR-FAKE:cid-dxos-openbao:ro\n"
        manifest = tf.extractfile("MANIFEST.txt").read().decode()
        assert "format=dxos-backup/1" in manifest and "source_project=dxos" in manifest
        sums = tf.extractfile("SHA256SUMS").read().decode().splitlines()
        assert len(sums) == 5
        for line in sums:
            digest, name = line.split("  ")
            assert digest == hashlib.sha256(tf.extractfile(name).read()).hexdigest()


def test_backup_reads_databases_and_volumes_read_only_from_project_dxos(world):
    r = world.backup()
    assert r.returncode == 0, r.out
    for svc, user, db in (("core-db", "dxos_owner", "dxos"), ("kc-db", "keycloak", "keycloak"),
                          ("flowable-db", "flowable", "flowable")):
        assert f"docker exec cid-dxos-{svc} pg_dump -Fc -U {user} -d {db}" in r.text
    runs = [c for c in r.docker if c.startswith("docker run ")]
    assert len(runs) == 2
    for run, svc in zip(runs, ("seaweedfs", "openbao"), strict=True):
        assert f"--volumes-from cid-dxos-{svc}:ro" in run         # chỉ đọc
        assert "--network none" in run and "--rm" in run
        assert re.search(r" busybox:[0-9.]+@sha256:[0-9a-f]{64} tar -cf - -C ", run), run
    # mọi lời gọi chỉ nhắm project dxos và chỉ đọc: không compose, không tạo/xóa gì
    assert not any(c.startswith(("docker compose", "docker volume", "docker rm", "docker stop"))
                   for c in r.docker)
    assert all("project=dxos" in c for c in r.docker if c.startswith("docker ps"))


def test_backup_refuses_missing_passphrase_exit_3(world):
    world.set_passphrase(None)
    r = world.backup()
    assert r.returncode == 3, r.out
    assert "backup-passphrase" in r.stderr
    assert r.docker == [] and r.openssl == []                     # chưa đụng tới docker hay openssl
    assert not world.out.exists() or list(world.out.iterdir()) == []
    assert world.leftover_staging() == []


@pytest.mark.parametrize("content", ["", "\n", "short"])
def test_backup_refuses_empty_or_short_passphrase_exit_3(world, content):
    p = world.repo / ".secrets/backup-passphrase"
    p.write_text(content, encoding="utf-8")
    r = world.backup()
    assert r.returncode == 3 and r.docker == [], r.out
    assert not world.out.exists() or list(world.out.iterdir()) == []


def test_backup_bad_arguments_exit_2(world):
    for args in ((), ("",), ("a", "b"), ("-x",)):
        r = world.run("backup.sh", *args)
        assert r.returncode == 2 and r.docker == [], (args, r.out)
    f = world.root / "afile"
    f.write_text("x", encoding="utf-8")
    r = world.backup(f)                                           # thư mục ra là một tệp
    assert r.returncode == 2 and r.docker == []


def test_backup_service_not_running_exit_3_and_writes_nothing(world):
    r = world.backup(FAKE_NO_SERVICE="kc-db")
    assert r.returncode == 3 and "kc-db" in r.stderr, r.out
    assert list(world.out.iterdir()) == []
    assert world.leftover_staging() == []


def test_backup_encryption_failure_leaves_no_file_in_destination(world):
    r = world.backup(FAKE_OPENSSL_FAIL="1")
    assert r.returncode == 3, r.out
    assert list(world.out.iterdir()) == []                        # kể cả .partial
    assert world.leftover_staging() == []


# ============================================================ restore.sh
@pytest.mark.parametrize("project", ["dxos", "DXOS", "Dxos", "dxos ", " dxos", "dxos/", "", "-p", "d$xos",
                                     "dxos_restore;ls"])
def test_restore_refuses_project_dxos_exit_2(world, project):
    bundle = make_bundle(world)
    r = world.restore(bundle, "--project", project)
    assert r.returncode == 2, (project, r.out)
    assert r.docker == [] and r.openssl == []                     # từ chối trước mọi docker / giải mã
    assert world.leftover_staging() == []


def test_restore_requires_project_and_known_options(world):
    bundle = make_bundle(world)
    for args in ((), ("--bogus", "x"), ("--project",), ("--project", "dxos-restore", "--profile", "p4"),
                 ("--project", "dxos-restore", "extra")):
        r = world.restore(bundle, *args)
        assert r.returncode == 2 and r.docker == [], (args, r.out)
    assert world.run("restore.sh").returncode == 2


def test_restore_bad_checksum_stops_before_any_docker_call(world):
    bundle = make_bundle(world)
    sums = Path(str(bundle) + ".sha256")
    sums.write_text(f"{'0' * 64}  {bundle.name}\n", encoding="utf-8")
    r = world.restore(bundle, "--project", "dxos-restore")
    assert r.returncode == 2, r.out
    assert "sha256" in r.stderr
    assert r.docker == [] and r.openssl == []                     # chưa giải mã, chưa gọi docker
    sums.unlink()                                                 # thiếu tệp .sha256 cũng bị từ chối
    r = world.restore(bundle, "--project", "dxos-restore")
    assert r.returncode == 2 and r.docker == []
    sums.write_text("not-a-hash\n", encoding="utf-8")
    r = world.restore(bundle, "--project", "dxos-restore")
    assert r.returncode == 2 and r.docker == []


def test_restore_tampered_bundle_with_stale_checksum_is_refused(world):
    bundle = make_bundle(world)
    raw = bytearray(bundle.read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    bundle.write_bytes(bytes(raw))
    r = world.restore(bundle, "--project", "dxos-restore")
    assert r.returncode == 2 and r.docker == [], r.out


def test_restore_wrong_passphrase_stops_before_volume_create(world):
    bundle = make_bundle(world)
    world.set_passphrase(OTHER_PASSPHRASE)
    r = world.restore(bundle, "--project", "dxos-restore")
    assert r.returncode == 2, r.out
    assert any("-d -aes-256-cbc" in c or "enc -d" in c for c in r.openssl)    # đã thử giải mã thật
    assert r.docker == []                                         # không volume create, compose, gì cả
    assert not any("volume create" in c or "compose" in c for c in r.calls)
    assert world.leftover_staging() == []


@pytest.mark.parametrize("flip", ["header", "middle", "tail"])
def test_restore_tampered_bundle_with_fixed_checksum_stops_before_volume_create(world, flip):
    """Kẻ sửa gói sửa luôn .sha256 (P4-D9: không có MAC riêng) thì nội dung phải bị bắt ở bước kiểm gói."""
    bundle = make_bundle(world)
    raw = bytearray(bundle.read_bytes())
    pos = {"header": 20, "middle": len(raw) // 2, "tail": len(raw) - 5}[flip]
    raw[pos] ^= 0x55
    bundle.write_bytes(bytes(raw))
    Path(str(bundle) + ".sha256").write_text(
        f"{hashlib.sha256(bytes(raw)).hexdigest()}  {bundle.name}\n", encoding="utf-8")
    r = world.restore(bundle, "--project", "dxos-restore")
    assert r.returncode == 2, r.out
    assert r.docker == []
    assert world.leftover_staging() == []


def test_restore_truncated_bundle_is_refused(world):
    bundle = make_bundle(world)
    raw = bundle.read_bytes()[:-37]
    bundle.write_bytes(raw)
    Path(str(bundle) + ".sha256").write_text(
        f"{hashlib.sha256(raw).hexdigest()}  {bundle.name}\n", encoding="utf-8")
    r = world.restore(bundle, "--project", "dxos-restore")
    assert r.returncode == 2 and r.docker == [], r.out


@pytest.mark.parametrize("extra", ["../evil", "/etc/cron.d/x", "pg/other.dump", "volumes/clamav-db.tar"])
def test_restore_refuses_archive_with_unexpected_member(world, extra):
    bundle = make_bundle(world)
    ok = {m: b"x" for m in MEMBERS}
    reencrypt(world, bundle, {**ok, extra: b"x"})
    r = world.restore(bundle, "--project", "dxos-restore")
    assert r.returncode == 2 and r.docker == [], r.out


def test_restore_refuses_archive_whose_member_hash_does_not_match(world):
    bundle = make_bundle(world)
    good = {"MANIFEST.txt": b"format=dxos-backup/1\nsource_project=dxos\n",
            "pg/core-db.dump": b"a", "pg/kc-db.dump": b"b", "pg/flowable-db.dump": b"c",
            "volumes/seaweedfs-data.tar": b"d", "volumes/openbao-data.tar": b"e"}
    sums = "".join(f"{hashlib.sha256(v).hexdigest()}  {k}\n" for k, v in good.items() if k != "MANIFEST.txt")
    reencrypt(world, bundle, {**good, "SHA256SUMS": sums.encode()})
    r = world.restore(bundle, "--project", "dxos-restore")
    assert r.returncode == 0, r.out                               # gói hợp lệ chạy được (đối chứng)
    world.seed_stdin_clear()
    reencrypt(world, bundle, {**good, "pg/kc-db.dump": b"TAMPERED", "SHA256SUMS": sums.encode()})
    r = world.restore(bundle, "--project", "dxos-restore2")
    assert r.returncode == 2 and r.docker == [], r.out


def test_restore_happy_path_only_touches_the_given_project(world):
    bundle = make_bundle(world)
    r = world.restore(bundle, "--project", "dxos-restore")
    assert r.returncode == 0, r.out
    assert r.order([
        "docker ps -aq --filter label=com.docker.compose.project=dxos-restore",
        "docker volume ls -q --filter label=com.docker.compose.project=dxos-restore",
        "docker volume create --label com.docker.compose.project=dxos-restore "
        "--label com.docker.compose.volume=seaweedfs-data dxos-restore_seaweedfs-data",
        "docker run --rm -i --network none -v dxos-restore_seaweedfs-data:/data busybox:",
        "docker volume create --label com.docker.compose.project=dxos-restore "
        "--label com.docker.compose.volume=openbao-data dxos-restore_openbao-data",
        "docker run --rm -i --network none -v dxos-restore_openbao-data:/data busybox:",
        "docker compose -p dxos-restore --env-file .env",
        "docker exec cid-dxos-restore-core-db psql -U dxos_owner -d dxos -v ON_ERROR_STOP=1 -c",
        "docker exec -i cid-dxos-restore-core-db pg_restore -U dxos_owner -d dxos --exit-on-error",
        "docker exec -i cid-dxos-restore-kc-db pg_restore -U keycloak -d keycloak --exit-on-error",
        "docker exec -i cid-dxos-restore-flowable-db pg_restore -U flowable -d flowable --exit-on-error",
    ]), r.text
    up = next(c for c in r.docker if " up " in c)
    assert up.endswith(" up -d --wait --wait-timeout 300 core-db kc-db flowable-db")
    assert "-f deploy/compose.yaml -f deploy/compose.p16.yaml" in up
    # Không lời gọi nào chạm project dxos: không `-p dxos `, không volume `dxos_...`, không cid project đó.
    for c in r.docker:
        assert not re.search(r"-p dxos( |$)", c), c
        assert not re.search(r"\bdxos_(seaweedfs|openbao|core-db|kc-db|flowable-db)", c), c
        assert "cid-dxos-" not in c.replace("cid-dxos-restore-", ""), c
        assert "project=dxos " not in c + " " and "project=dxos\n" not in c
    assert not any({"rm", "stop", "kill", "down", "prune"} & set(c.split()) for c in r.docker)
    assert "dxos-restore" in r.stdout and "MỞ KHÓA" in r.stdout            # dặn bước tiếp theo
    assert world.leftover_staging() == []
    # nội dung đã khôi phục đúng là nội dung đã sao lưu, theo thứ tự volume rồi DB
    stdin = {f.name: f.read_bytes() for f in sorted(world.stdin.iterdir())}
    assert sorted(stdin.values()) == sorted([
        b"TAR-FAKE:cid-dxos-seaweedfs:ro\n", b"TAR-FAKE:cid-dxos-openbao:ro\n",
        b"PGDMP-FAKE:cid-dxos-core-db:dxos\n", b"PGDMP-FAKE:cid-dxos-kc-db:keycloak\n",
        b"PGDMP-FAKE:cid-dxos-flowable-db:flowable\n"])


def test_restore_creates_the_core_app_role_before_pg_restore(world):
    bundle = make_bundle(world)
    r = world.restore(bundle, "--project", "dxos-restore")
    assert r.returncode == 0, r.out
    psql = next(c for c in r.docker if " psql " in c)
    assert "CREATE ROLE dxos_core LOGIN" in psql and "NOSUPERUSER" in psql
    assert r.index(" psql ") < r.index("pg_restore")


def test_restore_accepts_profile_and_env_file(world):
    bundle = make_bundle(world)
    envf = world.root / "other.env"
    envf.write_text("DXOS_DOMAIN=x.example.test\n", encoding="utf-8")
    r = world.restore(bundle, "--project", "dxos-restore", "--profile", "p8", "--env-file", str(envf))
    assert r.returncode == 0, r.out
    up = next(c for c in r.docker if " up " in c)
    assert f"--env-file {envf}" in up and "compose.p8.yaml" in up
    r = world.restore(bundle, "--project", "dxos-restore", "--env-file", str(world.root / "missing.env"))
    assert r.returncode == 3 and r.docker == []


def test_restore_uses_release_overlay_when_the_live_stack_does(world):
    bundle = make_bundle(world)
    (world.repo / "deploy/release.env").write_text("DXOS_TRUST_CORE_DIGEST=x\n", encoding="utf-8")
    (world.repo / "deploy/compose.release.yaml").write_text("services: {}\n", encoding="utf-8")
    r = world.restore(bundle, "--project", "dxos-restore")
    assert r.returncode == 0, r.out
    up = next(c for c in r.docker if " up " in c)
    assert "--env-file deploy/release.env" in up and "-f deploy/compose.release.yaml" in up


def test_restore_refuses_a_project_that_already_has_resources(world):
    bundle = make_bundle(world)
    for env in ({"FAKE_EXISTING_VOLUMES": "dxos-restore_core-db-data\n"},
                {"FAKE_EXISTING_CONTAINERS": "abc123\n"}):
        r = world.restore(bundle, "--project", "dxos-restore", **env)
        assert r.returncode == 2, r.out
        assert "down -v" in r.stderr and "dxos-restore" in r.stderr
        changes = ("docker volume create", "docker compose", "docker run")
        assert not any(c.startswith(changes) for c in r.docker)


def test_restore_failure_after_start_exits_4_and_names_the_cleanup(world):
    bundle = make_bundle(world)
    for env in ({"FAKE_FAIL_VOLUME": "1"}, {"FAKE_FAIL_EXTRACT": "1"}, {"FAKE_FAIL_UP": "1"}):
        r = world.restore(bundle, "--project", "dxos-restore", **env)
        assert r.returncode == 4, (env, r.out)
        assert "docker compose -p dxos-restore" in r.stderr and "down -v" in r.stderr
        assert world.leftover_staging() == []


def test_restore_rejects_missing_prerequisites_exit_3(world):
    bundle = make_bundle(world)
    world.set_passphrase(None)
    r = world.restore(bundle, "--project", "dxos-restore")
    assert r.returncode == 3 and r.docker == [] and "backup-passphrase" in r.stderr


def test_backup_then_restore_roundtrip_with_real_openssl_is_bit_exact(world):
    """Đối chứng: gói do backup.sh tạo giải mã được bằng restore.sh với cùng mật khẩu (không giả openssl)."""
    bundle = make_bundle(world)
    r = world.restore(bundle, "--project", "drill-a1")
    assert r.returncode == 0, r.out
    assert any("openssl" in c and " -d " in c for c in r.openssl)


# ============================================================ at21_drill.sh
def drill_args(world: World, *extra: str) -> tuple[str, ...]:
    anchor = world.root / "anchor"
    anchor.mkdir(exist_ok=True)
    keyf = world.root / "unseal.key"
    keyf.write_text("# khóa mở khóa hư cấu\nunseal-key-one\nunseal-key-two\n", encoding="utf-8")
    return ("--seal-id", SEAL, "--anchor-dir", str(anchor), "--unseal-key-file", str(keyf), *extra)


def test_drill_compares_tree_size_and_root(world):
    world.fake_steps()
    r = world.run("at21_drill.sh", *drill_args(world))
    assert r.returncode == 0, r.out
    assert "42" in r.stdout and "ab" * 32 in r.stdout             # in tree_size và root đã so
    assert "ĐẠT" in r.stdout
    # thứ tự: chọn niêm phong và kiểm TRƯỚC khi sao lưu; khôi phục rồi mới dựng stack; kiểm lại sau
    assert r.order([
        f"{SEAL}/bundle", "dxos-witness verify-bundle", "backup.sh ", "down -v",
        "restore.sh ", " up -d --wait", "operator unseal", f"{SEAL}/bundle", "dxos-witness verify-bundle",
    ]), r.text
    verifies = [c for c in r.calls if c.startswith("dxos-witness verify-bundle")]
    assert len(verifies) == 2 and all("--anchor-dir" in v for v in verifies)
    assert r.index("dxos-witness verify-bundle") < r.index("backup.sh ")
    assert world.leftover_staging() == []


@pytest.mark.parametrize("which", ["FAKE_POST_STH", "FAKE_POST_BUNDLE_STH"])
@pytest.mark.parametrize("post", ["41 " + "ab" * 32, "42 " + "cd" * 32])
def test_drill_fails_when_tree_size_or_root_differs(world, which, post):
    world.fake_steps()
    r = world.run("at21_drill.sh", *drill_args(world), **{which: post})
    assert r.returncode == 1, r.out
    assert "KHÔNG ĐẠT" in r.stdout + r.stderr
    assert "ĐẠT" not in (r.stdout + r.stderr).replace("KHÔNG ĐẠT", "")
    assert "dxos-restore" in r.out and "down -v" in r.out         # dặn cách dọn


def test_drill_stops_when_the_seal_does_not_verify_before_the_backup(world):
    world.fake_steps()
    r = world.run("at21_drill.sh", *drill_args(world), FAKE_WITNESS_FAIL="before.json")
    assert r.returncode == 1, r.out
    assert not any(c.startswith("backup.sh") for c in r.calls)    # chưa sao lưu
    assert not any("dxos-restore" in c for c in r.docker)


def test_drill_fails_when_the_restored_seal_does_not_verify(world):
    world.fake_steps()
    r = world.run("at21_drill.sh", *drill_args(world), FAKE_WITNESS_FAIL="after.json")
    assert r.returncode == 1, r.out


def test_drill_only_touches_project_dxos_restore_on_another_hostname(world):
    world.fake_steps()
    r = world.run("at21_drill.sh", *drill_args(world))
    assert r.returncode == 0, r.out
    restore = next(c for c in r.calls if c.startswith("restore.sh "))
    assert "--project dxos-restore" in restore and "DXOS_DOMAIN=restore.localhost" in restore
    compose = [c for c in r.docker if c.startswith("docker compose")]
    assert compose and all(c.startswith("docker compose -p dxos-restore ") for c in compose), compose
    up = [c for c in compose if " up " in c]
    # chỉ phần lõi dữ liệu: không caddy (cổng 80/443 của stack thật), không Keycloak/Flowable (RAM)
    assert up and all("caddy" not in c and "apisix" not in c and "keycloak" not in c for c in up)
    assert any(c.endswith(" trust-core-api") for c in up)
    assert not any(re.search(r"-p dxos( |$)", c) for c in r.calls)
    # đọc stack thật chỉ bằng `docker exec` (đọc), không bao giờ sửa nó
    live = [c for c in r.docker if "cid-dxos-trust-core-api" in c or re.search(r"project=dxos( |$)", c)]
    assert live and all(c.startswith(("docker ps", "docker exec")) for c in live)
    # mở khóa OpenBao của bản khôi phục, khóa không nằm trên dòng lệnh
    unseal = [c for c in r.docker if "operator unseal" in c]
    assert len(unseal) == 2 and all("cid-dxos-restore-openbao" in c for c in unseal)
    assert "unseal-key-one" not in r.text and "unseal-key-two" not in r.text
    assert Path(str(world.log) + ".env").read_text(encoding="utf-8").count("unseal-env-present") == 2
    # dọn project diễn tập khi đạt
    assert "docker compose -p dxos-restore" in compose[-1] and " down -v" in compose[-1]


def test_drill_keep_leaves_the_restore_stack(world):
    world.fake_steps()
    r = world.run("at21_drill.sh", *drill_args(world, "--keep"))
    assert r.returncode == 0, r.out
    downs = [c for c in r.docker if " down " in c]
    # chỉ lần xóa project cũ, trước khi khôi phục
    assert len(downs) == 1 and r.index(" down ") < r.index("restore.sh ")


def test_drill_posts_the_file_hash_for_require_file_seals(world):
    world.fake_steps()
    f = world.root / "ho-so.pdf"
    f.write_bytes(b"%PDF-fictional")
    sha = hashlib.sha256(b"%PDF-fictional").hexdigest()
    objects = f"1 {sha}"
    r = world.run("at21_drill.sh", *drill_args(world, "--file", str(f)),
                  FAKE_PRE_OBJECTS=objects, FAKE_POST_OBJECTS=objects)
    assert r.returncode == 0, r.out
    posts = [c for c in r.docker if f"/verify/v1/seals/{SEAL}:bundle {sha}" in c]
    assert len(posts) == 4                          # gói và đối tượng kho, trước và sau
    verifies = [c for c in r.calls if c.startswith("dxos-witness verify-bundle")]
    assert all(f"--file {f}" in v for v in verifies)
    # băm của tệp gốc phải nằm trong các đối tượng đọc được; không có thì từ chối trước khi sao lưu
    r = world.run("at21_drill.sh", *drill_args(world, "--file", str(f)))
    assert r.returncode == 3 and not any(c.startswith("backup.sh") for c in r.calls), r.out


def test_drill_argument_and_prerequisite_errors(world):
    world.fake_steps()
    ok = drill_args(world)
    missing_anchor = ("--seal-id", SEAL, "--anchor-dir", str(world.root / "no-such-anchor"), *ok[4:])
    cases = {
        "no args": (), "no seal": ok[2:], "no anchor": ("--seal-id", SEAL, *ok[4:]),
        "no unseal key": ok[:4], "unknown": (*ok, "--bogus"), "bad seal id": ("--seal-id", "a b;ls", *ok[2:]),
        "missing anchor": missing_anchor,
    }
    for name, args in cases.items():
        r = world.run("at21_drill.sh", *args)
        assert r.returncode == 2, (name, r.out)
        assert r.docker == [], name
    r = world.run("at21_drill.sh", *ok[:5], str(world.root / "no-such-file"))
    assert r.returncode == 2
    r = world.run("at21_drill.sh", *ok, FAKE_NO_SERVICE="trust-core-api")        # stack thật không chạy
    assert r.returncode == 3 and not any(c.startswith("backup.sh") for c in r.calls)
    world.set_passphrase(None)
    r = world.run("at21_drill.sh", *ok)
    assert r.returncode == 3, r.out


def test_drill_step_failure_exits_4_and_names_how_to_clean_up(world):
    world.fake_steps()
    for env in ({"FAKE_BACKUP_FAIL": "1"}, {"FAKE_RESTORE_FAIL": "1"}, {"FAKE_FAIL_UP": "1"}):
        r = world.run("at21_drill.sh", *drill_args(world), **env)
        assert r.returncode == 4, (env, r.out)
        assert world.leftover_staging() == []
    r = world.run("at21_drill.sh", *drill_args(world), FAKE_RESTORE_FAIL="1")
    assert "docker compose -p dxos-restore" in r.out and "down -v" in r.out


# ============================================================ tĩnh: tiêu đề, shellcheck, ghim, tài liệu
@pytest.mark.parametrize("name", [*SCRIPTS, LIB])
def test_script_header_syntax_and_shellcheck(name):
    path = ROOT / "ops" / name
    text = path.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/bash\n")
    assert "SPDX-" + "License-Identifier: Apache-2.0" in text
    assert "SPDX-" + "FileCopyrightText: 2026 PSA_OVNCR" in text
    if name != LIB:
        assert "set -euo pipefail" in text
        assert os.access(path, os.X_OK)
    assert subprocess.run(["bash", "-n", str(path)], check=False).returncode == 0  # noqa: S603, S607
    exe = shutil.which("shellcheck") or (str(ROOT / ".venv/bin/shellcheck")
                                         if (ROOT / ".venv/bin/shellcheck").exists() else None)
    if exe:
        proc = subprocess.run([exe, "-S", "warning", "-x", str(path)],  # noqa: S603
                              capture_output=True, text=True, check=False, cwd=ROOT)
        assert proc.returncode == 0, proc.stdout


def test_busybox_image_is_pinned_once_and_matches_compose():
    lib = (ROOT / "ops" / LIB).read_text(encoding="utf-8")
    refs = re.findall(r"^BUSYBOX_IMAGE=(\S+)$", lib, re.M)
    assert len(refs) == 1 and re.fullmatch(r"busybox:[0-9.]+@sha256:[0-9a-f]{64}", refs[0]), refs
    compose = (ROOT / "deploy/compose.yaml").read_text(encoding="utf-8")
    assert f"image: {refs[0]}" in compose                          # cùng digest với net-probe-app
    for name in SCRIPTS:                                           # không script nào tự định nghĩa image khác
        text = (ROOT / "ops" / name).read_text(encoding="utf-8")
        assert not re.search(r"busybox:[0-9]", text) and "BUSYBOX_IMAGE=" not in text


def test_scripts_never_pass_secrets_on_argv_or_remove_user_paths():
    for name in (*SCRIPTS, LIB):
        text = (ROOT / "ops" / name).read_text(encoding="utf-8")
        assert "-pass pass:" not in text and "-pass env:" not in text
        for line in text.splitlines():
            if re.match(r"\s*#", line):
                continue
            for m in re.finditer(r"\brm\s+-[a-z]*r[a-z]*f?\s+(\S+)", line):      # rm -rf: chỉ thư mục mktemp
                assert re.fullmatch(r'"\$\{?(STAGE|WORK)\}?"', m[1].rstrip(";")), (name, line)


def test_runbook_backup_documents_timer_passphrase_and_restore():
    text = (ROOT / "docs/runbook-backup.md").read_text(encoding="utf-8")
    for needle in ("dxos-backup.timer", "dxos-backup.service", "OnCalendar", "không bật mặc định",
                   ".secrets/backup-passphrase", "chmod 600",
                   "openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt", "ops/backup.sh", "ops/restore.sh",
                   "--project dxos-restore", "ops/at21_drill.sh", "AT-21", "V43", "V21", "TMPDIR", "mở khóa",
                   "docker compose -p dxos-restore", "Mã thoát"):
        assert needle in text, needle
    assert "Không có xác thực MAC riêng" in text or "không có MAC" in text.lower() or "MAC" in text
    assert "có giá trị pháp lý" not in text.replace("không có giá trị pháp lý", "")


def test_pii_runbook_keeps_the_retention_blank_for_v21():
    text = (ROOT / "docs/runbook-pii-erasure.md").read_text(encoding="utf-8")
    assert "Đã chốt: ……… ngày" in text                              # để trống, trưởng nhóm điền (V21)
    assert "V21" in text and "runbook-backup.md" in text
    assert not re.search(r"Đã chốt:\s*\d+\s*ngày", text)


def test_acceptance_row_for_at21_points_to_tests_drill_and_v43():
    text = (ROOT / "docs/acceptance.md").read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| AT-21 "))
    for needle in ("Thủ công", "tests/ops/test_backup_restore.py", "ops/at21_drill.sh",
                   "docs/runbook-backup.md", "V43"):
        assert needle in row, needle


# ============================================================ vòng sửa 1 (review Task 12)
# ---- R25: tạm dừng object store trong lúc tar
def test_backup_pauses_seaweedfs_only_around_its_own_tar(world):
    r = world.backup()
    assert r.returncode == 0, r.out
    assert r.order(["docker pause cid-dxos-seaweedfs",
                    "docker run --rm --network none --volumes-from cid-dxos-seaweedfs:ro",
                    "docker unpause cid-dxos-seaweedfs",
                    "docker run --rm --network none --volumes-from cid-dxos-openbao:ro"]), r.text
    assert [c for c in r.docker if " pause " in c or " unpause " in c] == [
        "docker pause cid-dxos-seaweedfs", "docker unpause cid-dxos-seaweedfs"]     # OpenBao không bị dừng


def test_backup_unpauses_seaweedfs_when_tar_fails(world):
    r = world.backup(FAKE_FAIL_TAR="cid-dxos-seaweedfs:ro")
    assert r.returncode == 3, r.out
    assert r.order(["docker pause cid-dxos-seaweedfs", "docker unpause cid-dxos-seaweedfs"]), r.text
    assert list(world.out.iterdir()) == []


def test_backup_unpauses_seaweedfs_when_it_cannot_complete_the_pause(world):
    r = world.backup(FAKE_FAIL_PAUSE="1")
    assert r.returncode == 3 and "pause" in r.stderr, r.out
    assert not any(c.startswith("docker run") for c in r.docker)              # chưa tar gì khi chưa dừng được
    assert list(world.out.iterdir()) == []


def test_backup_unpauses_seaweedfs_on_sigterm(world):
    import signal
    import time
    env = {**os.environ, "PATH": f"{world.bin}{os.pathsep}{os.environ['PATH']}", "FAKE_LOG": str(world.log),
           "FAKE_STDIN": str(world.stdin), "REAL_OPENSSL": world.real_openssl, "TMPDIR": str(world.tmp),
           "FAKE_TAR_SLEEP": "cid-dxos-seaweedfs:ro"}
    for suffix in ("", ".openssl", ".env", ".msys", ".msys-openssl"):
        Path(str(world.log) + suffix).unlink(missing_ok=True)
    proc = subprocess.Popen(["bash", str(world.repo / "ops/backup.sh"), str(world.out)],  # noqa: S603, S607
                            env=env, cwd=world.repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if world.log.exists() and "volumes-from cid-dxos-seaweedfs" in world.log.read_text(encoding="utf-8"):
            break
        time.sleep(0.05)
    os.killpg(proc.pid, signal.SIGTERM)
    proc.communicate(timeout=30)
    calls = world.log.read_text(encoding="utf-8").splitlines()
    assert "docker pause cid-dxos-seaweedfs" in calls and "docker unpause cid-dxos-seaweedfs" in calls
    assert world.leftover_staging() == [] and list(world.out.iterdir()) == []


# ---- TMPDIR không được nằm trong thư mục ra
@pytest.mark.parametrize("where", ["same", "inside", "symlink"])
def test_backup_refuses_tmpdir_inside_the_output_directory(world, where):
    world.out.mkdir()
    if where == "same":
        tmp = world.out
    elif where == "inside":
        tmp = world.out / "tmp"
        tmp.mkdir()
    else:
        (world.out / "tmp").mkdir()
        tmp = world.root / "link"
        tmp.symlink_to(world.out / "tmp")
    r = world.backup(TMPDIR=str(tmp))
    assert r.returncode == 2, (where, r.out)
    assert "TMPDIR" in r.stderr
    assert r.docker == [] and r.openssl == []
    assert [p.name for p in world.out.iterdir()] in ([], ["tmp"])           # không ghi gì thêm


def test_backup_allows_tmpdir_outside_the_output_directory(world):
    r = world.backup()
    assert r.returncode == 0, r.out


def test_backup_warns_about_stale_staging_directories_and_keeps_them(world):
    stale = world.tmp / "dxos-backup.OLD123"
    stale.mkdir()
    (stale / "secret.dump").write_bytes(b"x")
    r = world.backup()
    assert r.returncode == 0, r.out
    assert "dxos-backup.OLD123" in r.stderr and "chưa mã hóa" in r.stderr
    assert (stale / "secret.dump").exists()                       # không tự xóa thứ của lần chạy khác


# ---- mật khẩu CRLF; MSYS_NO_PATHCONV chỉ cho docker
def test_backup_refuses_a_passphrase_file_with_crlf_exit_3(world):
    (world.repo / ".secrets/backup-passphrase").write_bytes(PASSPHRASE.encode() + b"\r\n")
    r = world.backup()
    assert r.returncode == 3 and "CRLF" in r.stderr and r.docker == [], r.out


def test_msys_no_pathconv_is_scoped_to_docker_calls(world):
    for name in (*SCRIPTS, LIB):
        text = (ROOT / "ops" / name).read_text(encoding="utf-8")
        assert not re.search(r"^\s*export\s+MSYS_NO_PATHCONV", text, re.M), name
    r = world.backup()
    assert r.returncode == 0, r.out
    docker_msys = Path(str(world.log) + ".msys").read_text(encoding="utf-8").split()
    openssl_msys = Path(str(world.log) + ".msys-openssl").read_text(encoding="utf-8").split()
    assert docker_msys and set(docker_msys) == {"1"}                         # mọi lời gọi docker có biến này
    assert openssl_msys and set(openssl_msys) == {"unset"}                    # openssl thì không


# ---- restore: thành viên không phải tệp thường; volume có sẵn không nhãn
def _good_members() -> dict[str, bytes]:
    good = {"pg/core-db.dump": b"a", "pg/kc-db.dump": b"b", "pg/flowable-db.dump": b"c",
            "volumes/seaweedfs-data.tar": b"d", "volumes/openbao-data.tar": b"e"}
    sums = "".join(f"{hashlib.sha256(v).hexdigest()}  {k}\n" for k, v in good.items())
    manifest = b"format=dxos-backup/1\nsource_project=dxos\n"
    return {"MANIFEST.txt": manifest, "SHA256SUMS": sums.encode(), **good}


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_restore_refuses_a_non_regular_member_before_any_docker_call(world, kind):
    bundle = make_bundle(world)
    members = _good_members()
    passwd = Path("/etc/passwd").read_bytes()
    victim = "volumes/openbao-data.tar"
    del members[victim]
    # SHA256SUMS khai băm của /etc/passwd cho thành viên này: nếu script đi theo liên kết thì băm sẽ khớp
    sums = members["SHA256SUMS"].decode().splitlines()
    sums.append(f"{hashlib.sha256(passwd).hexdigest()}  {victim}")
    members["SHA256SUMS"] = ("\n".join(sums) + "\n").encode()
    link = {victim: (tarfile.SYMTYPE, "/etc/passwd")} if kind == "symlink" else {
        victim: (tarfile.LNKTYPE, "pg/core-db.dump")}
    reencrypt(world, bundle, members, links=link)
    r = world.restore(bundle, "--project", "dxos-restore")
    assert r.returncode == 2 and r.docker == [], r.out
    assert "không phải tệp thường" in r.stderr
    assert world.leftover_staging() == []


def test_restore_accepts_the_regular_forged_bundle_as_a_control(world):
    """Đối chứng của hai test trên: cùng gói, thành viên là tệp thường thì qua."""
    bundle = make_bundle(world)
    reencrypt(world, bundle, _good_members())
    r = world.restore(bundle, "--project", "dxos-restore")
    assert r.returncode == 0, r.out


def test_restore_refuses_an_existing_unlabelled_volume_before_any_write(world):
    bundle = make_bundle(world)
    r = world.restore(bundle, "--project", "dxos-restore",
                      FAKE_EXISTING_VOLUME_NAMES="dxos-restore_openbao-data")
    assert r.returncode == 2, r.out
    assert "dxos-restore_openbao-data" in r.stderr
    assert not any(c.startswith(("docker volume create", "docker run", "docker compose", "docker exec"))
                   for c in r.docker)
    r = world.restore(bundle, "--project", "dxos-restore")
    assert r.returncode == 0 and any(c.startswith("docker volume inspect dxos-restore_seaweedfs-data")
                                     for c in r.docker)


# ---- drill: khóa OpenBao, kho đối tượng, trạng thái unseal
def test_drill_compares_the_public_keys_and_reads_storage_objects(world):
    world.fake_steps()
    r = world.run("at21_drill.sh", *drill_args(world))
    assert r.returncode == 0, r.out
    keys = [c for c in r.docker if "/verify/v1/keys" in c]
    objects = [c for c in r.docker if "ObjectStore" in c]
    assert len(keys) == 2 and len(objects) == 2                  # một lần ở stack thật, một ở bản khôi phục
    assert "cid-dxos-trust-core-api" in keys[0] and "cid-dxos-restore-trust-core-api" in keys[1]
    assert r.index("/verify/v1/keys") < r.index("backup.sh ")                 # lấy khóa TRƯỚC khi sao lưu
    assert r.index("bao status") < r.index("cid-dxos-restore-trust-core-api")     # unseal xong mới đọc
    assert "khóa công khai" in r.stdout and "tệp đính kèm" in r.stdout


@pytest.mark.parametrize("env", [
    {"FAKE_POST_KEYS": "01" * 32}, {"FAKE_FAIL_KEYS_POST": "1"},
    {"FAKE_POST_OBJECTS": "1 " + "ee" * 32}, {"FAKE_FAIL_OBJECTS_POST": "1"},
], ids=["keys-differ", "keys-unreadable", "objects-differ", "objects-unreadable"])
def test_drill_fails_when_keys_or_storage_do_not_survive_the_restore(world, env):
    world.fake_steps()
    r = world.run("at21_drill.sh", *drill_args(world), **env)
    assert r.returncode == 1, r.out
    assert "KHÔNG ĐẠT" in r.stdout + r.stderr and "down -v" in r.out


@pytest.mark.parametrize("env", [
    {"FAKE_FAIL_KEYS_PRE": "1"}, {"FAKE_FAIL_OBJECTS_PRE": "1"}, {"FAKE_PRE_OBJECTS": "0"},
    {"FAKE_PRE_KEYS": "not-a-hash"},
], ids=["keys", "objects", "no-attachments", "bad-keys"])
def test_drill_needs_keys_and_an_object_before_the_backup(world, env):
    world.fake_steps()
    r = world.run("at21_drill.sh", *drill_args(world), **env)
    assert r.returncode == 3, r.out
    assert not any(c.startswith("backup.sh") for c in r.calls)


def test_drill_stops_when_openbao_is_still_sealed_after_unseal(world):
    world.fake_steps()
    r = world.run("at21_drill.sh", *drill_args(world), FAKE_BAO_SEALED="1")
    assert r.returncode == 4, r.out
    assert "khóa" in r.stderr
    assert not any("up -d" in c and c.endswith(" trust-core-api") for c in r.docker)


def test_drill_unseal_key_comment_does_not_overclaim():
    text = (ROOT / "ops/at21_drill.sh").read_text(encoding="utf-8")
    assert "không bao giờ nằm trên dòng lệnh" not in text
    assert "argv" in text                                                    # nói rõ chỗ khóa còn lộ


def test_runbook_backup_matches_the_fixed_behaviour():
    text = (ROOT / "docs/runbook-backup.md").read_text(encoding="utf-8")
    for needle in ("docker pause", "docker unpause", "/var/lib/dxos-backup/tmp", "**nằm ngoài thư mục ra**",
                   "CRLF", "/verify/v1/keys", "SeaweedFS", "bao status", "argv"):
        assert needle in text, needle
    assert "TMPDIR=/var/backups/dxos/tmp" not in text                    # TMPDIR không nằm trong nơi để gói
    assert "không lên dòng lệnh)" not in text
