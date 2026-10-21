# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Installer ứng dụng Tầng 2 (spec 9.5, 12.3; Plan 02 Task 12): nộp, diff quyền, duyệt, vô hiệu hóa.

Nộp (``submit``): kiểm manifest, tệp đi kèm, BPMN và luật nâng cấp (P2-D14) rồi lưu ``PENDING`` cùng lá
``app.submitted`` (body có ``files: {path: sha256}``) trong một transaction. Chưa duyệt thì app chưa dùng
được.

Duyệt (``approve``): mọi bước idempotent, chạy lại được sau lỗi giữa chừng. Cả lần duyệt chạy dưới khóa
advisory **phiên** ``(LOCK_INSTALL, hashtext(app_id))`` trên một kết nối riêng (nhả trong ``finally``), vì
``FlowableClient.deploy`` là tra-rồi-tạo: hai lần duyệt đồng thời có thể tạo hai deployment. Khóa lấy bằng
``pg_try_advisory_*``: đang có thao tác cài khác của cùng app (nộp, duyệt, vô hiệu hóa) → 409
``install-in-progress`` ngay, không giữ kết nối chờ. Không transaction nào mở trong lúc gọi Keycloak hay
Flowable. Thứ tự:

1. phiên bản phải tồn tại; đã ACTIVE thì trả 200 ngay; khác PENDING → 409;
2. bốn mắt (P2-D21), trước mọi kiểm tra nội dung: người duyệt khác người nộp, trừ khi ``allow_self_approval``;
3. kiểm lại manifest, BPMN, phiên bản mới hơn mốc (semver, 409 ``version-not-newer``) và luật nâng cấp so với
   mốc **lúc này**: bản ACTIVE, hoặc khi app đang bị vô hiệu hóa thì bản từng ACTIVE cao nhất
   (``upgrade_baseline``);
4. tạo realm role ``app:<id>:<role>`` (Keycloak, service account ``dxos-installer``);
5. có workflow: deploy đúng ``render_bpmn(check_against_manifest(xml, m))`` (P2-D2), ghi ``app_deployments``
   (bảng chỉ-thêm: đã có dòng cùng ``rendered_sha256`` thì dùng lại, khác hash → 409);
6. ``save_manifest(ACTIVE)``: tự ``DISABLED`` bản cũ và ghi ``app.installed``.

Lỗi ở bước 4–5 → 503, phiên bản vẫn ``PENDING``, chưa có ``app.installed``. BPMN đã deploy mà chưa kích hoạt
không bao giờ chạy: ``workflow:start`` chỉ dùng ``app_deployments`` của bản ACTIVE (P2-D19).

Tên deployment Flowable là ``<id>@<version>#<16 hex đầu của rendered_sha256>``: ``deploy`` trả deployment cũ
cùng tên, nên tên phải gắn với nội dung (Flowable có thể sống lâu hơn DB của lõi).

Ledger chỉ nhận ``actor_ref`` (HMAC của ``sub``) và các hash; ``sub`` thật chỉ nằm ở bảng ``apps``.
"""

import hashlib
import json
import logging
import re
import unicodedata
from pathlib import PurePosixPath
from typing import Any

import asyncpg
from dxos_proof.canonical import CanonicalError, canonical_bytes, sha256_hex

from dxos_core.errors import ProblemError
from dxos_core.identity.jwt import Principal
from dxos_core.ledger.log import actor_ref, append
from dxos_core.policy.pdp import deny
from dxos_core.registry.bpmn import MAX_BPMN_BYTES, check_against_manifest, render_bpmn
from dxos_core.registry.keycloak_admin import IdpAdminUnavailable
from dxos_core.registry.model import CollectionSpec, FieldSpec, Manifest
from dxos_core.registry.store import (
    get_active,
    get_deployment,
    get_files,
    get_version,
    save_files,
    save_manifest,
)
from dxos_core.registry.upgrade import check_upgrade, sealed_before
from dxos_core.registry.validator import ManifestError, validate_manifest
from dxos_core.workflow.flowable import WorkflowUnavailable

log = logging.getLogger("dxos_core.registry.installer")

# Khóa advisory hai số nguyên (LOCK_INSTALL, hashtext(app_id)): nộp, duyệt và vô hiệu hóa của một app chạy nối
# tiếp. Khác 724000 (migrate), 724001 (ledger), 724100 (LOCK_WF), 724101 (LOCK_KEYSTMT).
LOCK_INSTALL = 724102

APP_ID = re.compile(r"[a-z][a-z0-9-]{1,62}")                # như domain app_slug của DB
VERSION = re.compile(r"\d{1,9}\.\d{1,9}\.\d{1,9}")
_DRIVE = re.compile(r"[A-Za-z]:")


# ---------------------------------------------------------------- lỗi
def manifest_problem(exc: ManifestError) -> ProblemError:
    """422 ``manifest-invalid`` với extension ``code`` và ``path`` (AT-11, AT-12 qua API)."""
    return ProblemError(422, "manifest-invalid", "Manifest invalid", exc.message, code=exc.code,
                        path=exc.path)


def _conflict(type_: str, detail: str) -> ProblemError:
    return ProblemError(409, type_, "Conflict", detail)


def _not_found() -> ProblemError:
    return ProblemError(404, "app-version-not-found", "Application version not found")


def _idp_unavailable(detail: str = "Keycloak admin API unavailable") -> ProblemError:
    return ProblemError(503, "idp-admin-unavailable", "Identity provider admin unavailable", detail)


def _esc(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def _loads(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _semver(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in version.split("."))


def _require_newer(base: Manifest, m: Manifest) -> None:
    """Không hạ cấp: phiên bản mới phải lớn hơn mốc (``upgrade_baseline``) theo semver (``x.y.z``) → 409."""
    if _semver(m.app.version) <= _semver(base.app.version):
        raise _conflict("version-not-newer",
                        f"{m.app.version} không mới hơn bản {base.app.version} (ACTIVE hoặc từng ACTIVE);"
                        " hãy tăng version")


async def upgrade_baseline(conn: asyncpg.Connection, app_id: str) -> Manifest | None:
    """Mốc so sánh khi nâng cấp (P2-D14, không hạ cấp): bản ACTIVE; không có thì bản **từng ACTIVE** có semver
    cao nhất (trạng thái ``DISABLED``: chỉ bản đã ACTIVE mới thành DISABLED). Chưa từng ACTIVE → None.

    Nhờ vậy ``:disable`` không phải đường vòng qua luật chỉ-thêm hay luật không hạ cấp (rà soát cuối, I2).
    """
    active = await get_active(conn, app_id)
    if active is not None:
        return active
    versions = [r["version"] for r in await conn.fetch(
        "SELECT version FROM core.apps WHERE id=$1 AND status='DISABLED'", app_id)]
    if not versions:
        return None
    return await get_version(conn, app_id, max(versions, key=_semver))


async def _check_against_baseline(conn: asyncpg.Connection, m: Manifest) -> None:
    """``_require_newer`` + ``check_upgrade`` so với ``upgrade_baseline`` lúc này (nộp và duyệt)."""
    base = await upgrade_baseline(conn, m.app.id)
    if base is not None:
        _require_newer(base, m)
        check_upgrade(base, m, sealed_before=await sealed_before(conn, m.app.id))


async def _try_lock(conn: asyncpg.Connection, app_id: str, *, xact: bool) -> None:
    """Khóa ``(LOCK_INSTALL, hashtext(app_id))`` không chờ: đang có thao tác cài khác → 409
    ``install-in-progress`` ngay (không giữ kết nối của pool để chờ)."""
    fn = "pg_try_advisory_xact_lock" if xact else "pg_try_advisory_lock"
    if not await conn.fetchval(f"SELECT {fn}($1, hashtext($2))", LOCK_INSTALL, app_id):  # noqa: S608
        raise _conflict("install-in-progress", f"{app_id}: đang có thao tác cài đặt khác; thử lại sau")


# ---------------------------------------------------------------- tệp đi kèm
def _path_error(path: str) -> str | None:
    if not path:
        return "đường dẫn rỗng"
    if unicodedata.normalize("NFC", path) != path:
        return "đường dẫn phải ở dạng Unicode NFC"
    if path.startswith(("/", "\\")) or "\\" in path or _DRIVE.match(path):
        return "đường dẫn phải là đường dẫn POSIX tương đối"
    if any(part in ("", ".", "..") for part in path.split("/")):
        return "đường dẫn không được chứa '..', '.' hay '//'"
    return None


def check_files(m: Manifest, files: object) -> dict[str, bytes]:
    """``files`` phải chứa **đúng** các tệp manifest tham chiếu (hiện chỉ ``workflow.bpmn``), đường dẫn tương
    đối POSIX, NFC, không ``..``; nội dung là chuỗi, tối đa ``MAX_BPMN_BYTES`` byte UTF-8. Trả path → bytes.

    Lỗi → ``ManifestError("SCHEMA_INVALID", "/files…")``.
    """
    if not isinstance(files, dict):
        raise ManifestError("SCHEMA_INVALID", "/files", "files phải là object {đường dẫn: nội dung}")
    for path, content in files.items():
        where = f"/files/{_esc(path)}"
        why = _path_error(path)
        if why:
            raise ManifestError("SCHEMA_INVALID", where, why)
        if not isinstance(content, str):
            raise ManifestError("SCHEMA_INVALID", where, "nội dung tệp phải là chuỗi")
    expected = {m.workflow.bpmn} if m.workflow is not None else set()
    missing = sorted(expected - files.keys())
    if missing:
        raise ManifestError("SCHEMA_INVALID", "/files", f"thiếu tệp manifest tham chiếu: {missing}")
    extra = sorted(files.keys() - expected)
    if extra:
        raise ManifestError("SCHEMA_INVALID", f"/files/{_esc(extra[0])}",
                            "tệp không được manifest tham chiếu")
    out: dict[str, bytes] = {}
    for path, content in files.items():
        try:
            data = content.encode("utf-8")
        except UnicodeEncodeError:
            raise ManifestError("SCHEMA_INVALID", f"/files/{_esc(path)}",
                                "nội dung tệp không phải UTF-8 hợp lệ") from None
        if len(data) > MAX_BPMN_BYTES:
            raise ManifestError("SCHEMA_INVALID", f"/files/{_esc(path)}",
                                f"tệp vượt quá {MAX_BPMN_BYTES} byte")
        out[path] = data
    return out


# ---------------------------------------------------------------- diff quyền
def _access(col: CollectionSpec) -> dict[str, list[str]]:
    a = col.access
    return {"read": list(a.read), "create": list(a.create), "update": list(a.update)}


def _sequence(f: FieldSpec | None) -> dict[str, Any] | None:
    return {"format": f.format, "reset": f.reset} if f is not None and f.type == "sequence" else None


def permission_diff(old: Manifest | None, new: Manifest, *, bpmn_sha256: str | None) -> dict[str, Any]:
    """Diff quyền của ``new`` so với bản ACTIVE ``old`` (hoặc rỗng) — "xem diff quyền" của spec 9.5.

    Danh sách đã sắp xếp; ``access``, ``tasks``, ``labels``, ``sequences`` chỉ gồm mục mới hoặc đã đổi
    (``access``/``tasks`` mang giá trị mới; ``labels``/``sequences`` mang ``{old, new}``); chính sách PII,
    niêm phong và đối soát luôn có ``{old, new}`` (``old`` là ``None`` khi chưa có bản ACTIVE).
    """
    ocols = old.collections if old is not None else {}
    fields_added: dict[str, list[str]] = {}
    access: dict[str, dict[str, list[str]]] = {}
    labels: dict[str, dict[str, dict[str, str | None]]] = {}
    sequences: dict[str, dict[str, dict[str, Any]]] = {}
    for cname, col in sorted(new.collections.items()):
        ocol = ocols.get(cname)
        ofields = ocol.fields if ocol is not None else {}
        added = sorted(set(col.fields) - set(ofields))
        if added:
            fields_added[cname] = added
        if ocol is None or ocol.access != col.access:
            access[cname] = _access(col)
        for fname, f in sorted(col.fields.items()):
            of = ofields.get(fname)
            olabel = of.label if of is not None else None
            if f.label != olabel:
                labels.setdefault(cname, {})[fname] = {"old": olabel, "new": f.label}
            nseq, oseq = _sequence(f), _sequence(of)
            if nseq is not None and nseq != oseq:
                sequences.setdefault(cname, {})[fname] = {"old": oseq, "new": nseq}
    otasks = old.workflow.tasks if old is not None and old.workflow is not None else {}
    ntasks = new.workflow.tasks if new.workflow is not None else {}
    tasks = {t: {"role": spec.role, "guards": list(spec.guards)}
             for t, spec in sorted(ntasks.items()) if otasks.get(t) != spec}

    def pair(get) -> dict[str, Any]:
        return {"old": get(old) if old is not None else None, "new": get(new)}

    def dump(model) -> dict[str, Any] | None:
        return None if model is None else model.model_dump(mode="json")

    return {
        "app_id": new.app.id,
        "version": new.app.version,
        "against": old.app.version if old is not None else None,
        "roles_added": sorted(set(new.roles) - set(old.roles if old is not None else ())),
        "collections_added": sorted(set(new.collections) - set(ocols)),
        "fields_added": fields_added,
        "access": access,
        "pii_reveal_roles": pair(lambda m: list(m.policies.pii.reveal_roles)),
        "pii_erase_roles": pair(lambda m: list(m.policies.pii.erase_roles)),
        "seal": pair(lambda m: dump(m.policies.seal)),
        "verify": pair(lambda m: dump(m.policies.verify)),
        "tasks": tasks,
        "labels": labels,
        "sequences": sequences,
        "bpmn_sha256": bpmn_sha256,
    }


# ---------------------------------------------------------------- nộp
def _check_submission(body: object) -> tuple[Manifest, dict, str, dict[str, bytes], dict[str, str]]:
    """Bước 1–3 (không cần DB). Trả (manifest, raw, manifest_sha256, path → bytes, path → văn bản)."""
    if not isinstance(body, dict) or set(body) != {"manifest", "files"}:
        raise ProblemError(422, "invalid-request", "Request validation failed",
                           'body must be {"manifest": {...}, "files": {...}}')
    raw = body["manifest"]
    try:
        m = validate_manifest(raw)
        try:
            digest = sha256_hex(canonical_bytes(raw))
        except (CanonicalError, UnicodeError) as exc:
            # số thực, khóa không phải chuỗi, surrogate lẻ (không mã hóa UTF-8 được): không băm chuẩn hóa được
            raise ManifestError("SCHEMA_INVALID", "",
                                f"manifest không chuẩn hóa được ({type(exc).__name__})") from None
        data = check_files(m, body["files"])
        if m.workflow is not None:
            check_against_manifest(data[m.workflow.bpmn], m)
    except ManifestError as exc:
        raise manifest_problem(exc) from None
    except RecursionError:
        raise manifest_problem(ManifestError("SCHEMA_INVALID", "", "manifest lồng quá sâu")) from None
    return m, raw, digest, data, {p: body["files"][p] for p in data}


async def submit(pool: asyncpg.Pool, body: object, *, actor: Principal, hmac_key: bytes) -> dict[str, Any]:
    """``POST /admin/v1/apps``: lưu phiên bản ``PENDING``. Nộp lại y hệt bản đang PENDING → cùng kết quả."""
    m, raw, digest, data, texts = _check_submission(body)
    hashes = {p: _sha(b) for p, b in sorted(data.items())}
    result = {"app_id": m.app.id, "version": m.app.version, "status": "PENDING", "manifest_sha256": digest,
              "files": hashes}
    async with pool.acquire() as conn, conn.transaction():
        await _try_lock(conn, m.app.id, xact=True)
        row = await conn.fetchrow("SELECT manifest_sha256, status FROM core.apps WHERE id=$1 AND version=$2",
                                  m.app.id, m.app.version)
        if row is not None:
            stored = {r["path"]: r["sha256"] for r in await conn.fetch(
                "SELECT path, sha256 FROM core.app_files WHERE app_id=$1 AND version=$2",
                m.app.id, m.app.version)}
            if row["manifest_sha256"] != digest or stored != hashes:
                raise _conflict("app-version-conflict",
                                f"{m.app.id} {m.app.version} đã được nộp với nội dung khác; hãy tăng version")
            if row["status"] != "PENDING":
                raise _conflict("app-version-conflict", f"{m.app.id} {m.app.version} đã {row['status']}")
            return result
        try:
            await _check_against_baseline(conn, m)
        except ManifestError as exc:
            raise manifest_problem(exc) from None
        await save_manifest(conn, m, raw, "PENDING", actor.sub, hmac_key=hmac_key,
                            extra_body={"files": hashes})
        await save_files(conn, m.app.id, m.app.version, texts)
    return result


# ---------------------------------------------------------------- đọc
def _ref(sub: str | None, hmac_key: bytes) -> str | None:
    return None if sub is None else actor_ref(sub, hmac_key)


async def list_apps(pool: asyncpg.Pool, *, hmac_key: bytes) -> list[dict[str, Any]]:
    """Mọi phiên bản của mọi app; người nộp/duyệt chỉ ở dạng ``actor_ref`` (không bao giờ ``sub`` thật)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, version, status, manifest_sha256, submitted_by, approved_by, created_at"
            " FROM core.apps"
            " ORDER BY id, created_at, version")
    return [{"app_id": r["id"], "version": r["version"], "status": r["status"],
             "manifest_sha256": r["manifest_sha256"], "submitted_by_ref": _ref(r["submitted_by"], hmac_key),
             "approved_by_ref": _ref(r["approved_by"], hmac_key), "created_at": r["created_at"].isoformat()}
            for r in rows]


async def version_diff(pool: asyncpg.Pool, app_id: str, version: str) -> dict[str, Any]:
    """Diff quyền của một phiên bản (mọi trạng thái) so với bản ACTIVE hiện tại."""
    if not APP_ID.fullmatch(app_id) or not VERSION.fullmatch(version):
        raise _not_found()
    async with pool.acquire() as conn:
        raw = await conn.fetchval("SELECT manifest FROM core.apps WHERE id=$1 AND version=$2",
                                  app_id, version)
        if raw is None:
            raise _not_found()
        try:
            m = validate_manifest(_loads(raw))
            active = await get_active(conn, app_id)
        except ManifestError as exc:
            raise manifest_problem(exc) from None
        files = await get_files(conn, app_id, version)
    text = files.get(m.workflow.bpmn) if m.workflow is not None else None
    return permission_diff(active, m, bpmn_sha256=None if text is None else _sha(text.encode("utf-8")))


# ---------------------------------------------------------------- duyệt
async def _installed_view(conn: asyncpg.Connection, app_id: str, version: str) -> dict[str, Any]:
    row = await conn.fetchrow("SELECT status, manifest_sha256, submitted_by, approved_by FROM core.apps"
                              " WHERE id=$1 AND version=$2", app_id, version)
    dep = await get_deployment(conn, app_id, version)
    return {"app_id": app_id, "version": version, "status": row["status"],
            "manifest_sha256": row["manifest_sha256"],
            "self_approved": row["submitted_by"] is not None and row["submitted_by"] == row["approved_by"],
            "deployment_id": None if dep is None else dep["deployment_id"],
            "rendered_sha256": None if dep is None else dep["rendered_sha256"]}


async def _deploy(conn: asyncpg.Connection, state: Any, m: Manifest, rendered: bytes) -> str:
    """Bước 5: deploy bản dựng lại (hoặc dùng lại dòng ``app_deployments`` đã có); trả ``deployment_id``."""
    rsha = _sha(rendered)
    dep = await get_deployment(conn, m.app.id, m.app.version)
    if dep is not None:
        if dep["rendered_sha256"] != rsha:
            raise _conflict("deployment-mismatch",
                            "phiên bản đã có bản deploy khác (app_deployments chỉ thêm); hãy tăng version")
        return dep["deployment_id"]
    flowable = state.flowable
    if flowable is None:
        raise ProblemError(503, "workflow-unavailable", "Workflow engine unavailable",
                           "Flowable not configured")
    name = f"{m.app.id}@{m.app.version}#{rsha[:16]}"
    filename = f"{PurePosixPath(m.workflow.bpmn).stem}.bpmn20.xml"
    try:
        deployment_id = await flowable.deploy(name, filename, rendered)
        definition_id = await flowable.definition_id(deployment_id)
    except WorkflowUnavailable as exc:
        log.error("deploy BPMN của %s@%s thất bại: %s", m.app.id, m.app.version, exc)
        raise ProblemError(503, "workflow-unavailable", "Workflow engine unavailable") from None
    await conn.execute(
        "INSERT INTO core.app_deployments(app_id, version, deployment_id, process_definition_id,"
        " rendered_sha256)"
        " VALUES ($1, $2, $3, $4, $5)", m.app.id, m.app.version, deployment_id, definition_id, rsha)
    return deployment_id


async def _approve_locked(conn: asyncpg.Connection, state: Any, app_id: str, version: str,
                          approver: Principal) -> dict[str, Any]:
    settings, hmac_key = state.settings, state.hmac_key
    row = await conn.fetchrow("SELECT manifest, status, submitted_by FROM core.apps"
                              " WHERE id=$1 AND version=$2",
                              app_id, version)
    if row is None:
        raise _not_found()
    if row["status"] == "ACTIVE":
        return await _installed_view(conn, app_id, version)
    if row["status"] != "PENDING":
        raise _conflict("app-version-not-pending",
                        f"{app_id} {version} đang {row['status']}, không duyệt được")
    # Bước 2: bốn mắt (P2-D21), trước mọi kiểm tra nội dung của phiên bản.
    self_approved = approver.sub == row["submitted_by"]
    if self_approved and not settings.allow_self_approval:
        await deny(conn, approver, app_id, action="approve", reason="self_approval",
                   subject=f"{app_id}@{version}", hmac_key=hmac_key)
        raise ProblemError(403, "forbidden", "Forbidden", "approver must differ from submitter (four eyes)",
                           reason="self_approval")
    # Bước 3: kiểm lại manifest, BPMN, phiên bản mới hơn và luật nâng cấp so với mốc lúc này (bản ACTIVE,
    # hoặc bản từng ACTIVE cao nhất nếu app đang bị vô hiệu hóa).
    raw = _loads(row["manifest"])
    rendered = bpmn_sha256 = None
    try:
        m = validate_manifest(raw)
        if m.workflow is not None:
            text = (await get_files(conn, app_id, version)).get(m.workflow.bpmn)
            if text is None:
                raise ManifestError("BPMN_INVALID", "/workflow/bpmn", "thiếu tệp BPMN đã nộp")
            xml = text.encode("utf-8")
            bpmn_sha256 = _sha(xml)
            rendered = render_bpmn(check_against_manifest(xml, m))
        await _check_against_baseline(conn, m)
    except ManifestError as exc:
        raise manifest_problem(exc) from None
    # Bước 4: realm role (Keycloak). Không transaction nào đang mở.
    try:
        kc = state.kc_admin.get(settings)
        if kc is None:
            raise _idp_unavailable("installer client not configured")
        await kc.ensure_app_roles(app_id, list(m.roles))
    except IdpAdminUnavailable as exc:
        log.error("tạo role Keycloak cho %s@%s thất bại: %s", app_id, version, exc)
        raise _idp_unavailable() from None
    # Bước 5: deploy BPMN đã dựng lại.
    deployment_id = None
    if rendered is not None:
        deployment_id = await _deploy(conn, state, m, rendered)
    # Bước 6: kích hoạt (DISABLED bản cũ + app.installed, một transaction).
    await save_manifest(conn, m, raw, "ACTIVE", approver.sub, hmac_key=hmac_key, extra_body={
        "bpmn_sha256": bpmn_sha256, "rendered_sha256": None if rendered is None else _sha(rendered),
        "deployment_id": deployment_id, "self_approved": self_approved})
    return await _installed_view(conn, app_id, version)


async def approve(state: Any, app_id: str, version: str, *, approver: Principal) -> dict[str, Any]:
    """``POST /admin/v1/apps/{id}:approve`` dưới khóa phiên ``LOCK_INSTALL`` (xem docstring mô-đun)."""
    if not APP_ID.fullmatch(app_id) or not VERSION.fullmatch(version):
        raise _not_found()
    pool: asyncpg.Pool = state.pool
    conn = await pool.acquire()
    try:
        await _try_lock(conn, app_id, xact=False)
        try:
            return await _approve_locked(conn, state, app_id, version, approver)
        finally:
            try:
                await conn.execute("SELECT pg_advisory_unlock($1, hashtext($2))", LOCK_INSTALL, app_id)
            except BaseException as exc:
                # Hủy kết nối thì phiên mất, khóa phiên mất theo: không bao giờ treo lại trong pool.
                log.exception("không nhả được khóa cài đặt của %s; hủy kết nối", app_id)
                conn.terminate()
                if not isinstance(exc, Exception):
                    raise
    finally:
        await pool.release(conn)


# ---------------------------------------------------------------- vô hiệu hóa
async def disable(pool: asyncpg.Pool, app_id: str, *, actor: Principal, hmac_key: bytes) -> dict[str, Any]:
    """``POST /admin/v1/apps/{id}:disable``: bản ACTIVE → ``DISABLED`` + lá ``app.disabled``.

    Dữ liệu, ledger, role Keycloak và deployment Flowable giữ nguyên; bản ghi đã ghim phiên bản vẫn đọc được
    manifest của mình (P2-D19). Không có bản ACTIVE → 404 ``app-not-active``; đang có lần nộp/duyệt/vô hiệu
    hóa khác của cùng app (khóa ``LOCK_INSTALL``) → 409 ``install-in-progress`` ngay. Không kiểm lại manifest
    (vô hiệu hóa luôn phải làm được) và body lá giống ``save_manifest``: ``{manifest_sha256, status}``.
    """
    if not APP_ID.fullmatch(app_id):
        raise ProblemError(404, "app-not-active", "Application not active")
    async with pool.acquire() as conn, conn.transaction():
        await _try_lock(conn, app_id, xact=True)
        row = await conn.fetchrow("SELECT version, manifest_sha256 FROM core.apps"
                                  " WHERE id=$1 AND status='ACTIVE'"
                                  " FOR UPDATE", app_id)
        if row is None:
            raise ProblemError(404, "app-not-active", "Application not active")
        await conn.execute("UPDATE core.apps SET status='DISABLED', updated_at=now()"
                           " WHERE id=$1 AND version=$2",
                           app_id, row["version"])
        await append(conn, type="app.disabled", subject=f"{app_id}@{row['version']}",
                     body={"manifest_sha256": row["manifest_sha256"], "status": "DISABLED"},
                     hmac_key=hmac_key, app_id=app_id, actor_sub=actor.sub)
    return {"app_id": app_id, "version": row["version"], "status": "DISABLED"}

