// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
//
// Trang đối soát tối giản (Plan 02 Task 10; spec 13.3, 25.1, 25.4; R-2).
// - Không build, không thư viện ngoài. CSP: script-src 'self', connect-src 'self', không có mã nội tuyến.
// - Mã niêm phong chỉ lấy từ location.hash và phải khớp ^[A-Z2-7]{26}$ trước khi dùng vào URL.
// - Tệp được băm bằng WebCrypto TẠI TRÌNH DUYỆT; chỉ {"sha256": hex} (JSON) được gửi đi.
// - Mọi giá trị từ API (nhãn từ manifest, giá trị do người dùng nhập) chỉ gán bằng textContent.
"use strict";

(function () {
  const SEAL_ID = /^[A-Z2-7]{26}$/;
  const SHA256_HEX = /^[0-9a-f]{64}$/;
  const API = "/verify/v1/seals/";

  const $ = (id) => document.getElementById(id);
  const el = {
    input: $("seal-input"), go: $("seal-go"), error: $("seal-error"),
    result: $("result"), badge: $("status-badge"), note: $("status-note"), issuer: $("issuer"),
    fields: $("fields"), ledger: $("ledger-line"), anchor: $("anchor-line"),
    fileCheck: $("file-check"), fileInput: $("file-input"), fileHash: $("file-hash"),
    fileResult: $("file-result"),
    bundle: $("bundle"), bundleNote: $("bundle-note"), bundleGo: $("bundle-go"), bundleError: $("bundle-error"),
  };

  let sealId = null;       // mã đã kiểm dạng; chỉ đặt trong load()
  let view = null;         // thân JSON của GET /verify/v1/seals/{id}
  let matchedDigest = null; // sha256 của tệp đã khớp, dùng cho POST :bundle
  let generation = 0;      // bỏ kết quả của lần tải cũ khi người dùng đổi mã
  let pickToken = 0;       // tăng mỗi lần chọn tệp; phản hồi của lần chọn cũ không được đổi kết quả

  // ---------------------------------------------------------------- tiện ích DOM
  function setText(node, text, tone) {
    node.textContent = text;
    node.classList.remove("ok", "warn", "bad", "wait", "unanchored");
    if (tone) node.classList.add(tone);
  }

  function show(node, visible) {
    node.hidden = !visible;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function addRow(list, label, value) {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = label;
    dd.textContent = value;
    list.append(dt, dd);
  }

  function valueText(value) {
    if (typeof value === "string") return value;
    if (value === null || value === undefined) return "";
    return JSON.stringify(value);
  }

  function issuedAtText(iso) {
    const d = new Date(iso);
    if (typeof iso !== "string" || Number.isNaN(d.getTime())) return valueText(iso);
    const vn = d.toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh", hour12: false });
    return vn + " (giờ Việt Nam) — " + iso;
  }

  // ---------------------------------------------------------------- gọi API (cùng nguồn)
  function sealUrl(suffix) {
    return API + encodeURIComponent(sealId) + suffix;
  }

  // GET cố định, không thân.
  const GET_INIT = {
    method: "GET", cache: "no-store", credentials: "omit", headers: { Accept: "application/json" },
  };

  // Chỉ có hai dạng gọi: api(url) là GET cố định, api(url, jsonPost(hex)) là POST thân {"sha256"}.
  async function api(url, init) {
    const resp = await fetch(url, init === undefined ? GET_INIT : init);
    return resp;
  }

  function jsonPost(hex) {
    return {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sha256: hex }),
      cache: "no-store",
      credentials: "omit",
    };
  }

  // ---------------------------------------------------------------- trạng thái
  function resetResult() {
    show(el.result, false);
    show(el.fileCheck, false);
    show(el.bundle, false);
    show(el.bundleGo, false);
    show(el.bundleError, false);
    show(el.fileHash, false);
    clear(el.fields);
    setText(el.badge, "");
    setText(el.note, "");
    setText(el.issuer, "");
    setText(el.ledger, "");
    setText(el.anchor, "");
    setText(el.fileResult, "");
    el.fileInput.value = "";
    matchedDigest = null;
    view = null;
  }

  function showStatus(label, tone, note) {
    show(el.result, true);
    setText(el.badge, label, tone);
    setText(el.note, note || "");
  }

  // Kết quả kiểm phía máy chủ (signature_valid, inclusion.verified): phải là true đúng nghĩa đen mới được tin.
  function checks(v) {
    const inc = v.inclusion && typeof v.inclusion === "object" ? v.inclusion : null;
    return {
      sigOk: v.signature_valid === true,
      verifiedOk: inc !== null && inc.verified === true,
      // Đã neo công khai: STH phủ lá đã có trong repo neo (máy chủ báo). null/thiếu/khác object → chưa neo.
      anchoredOk: inc !== null && inc.anchored !== null && typeof inc.anchored === "object",
      // Chưa có STH nào phủ lá (tree_size null): chưa thể kiểm inclusion, không phải "Không hợp lệ".
      treeKnown: inc !== null && inc.tree_size !== null && inc.tree_size !== undefined,
      hasInclusion: inc !== null,
    };
  }

  function isInvalid(v) {
    const c = checks(v);
    return !c.sigOk || !c.hasInclusion || (c.treeKnown && !c.verifiedOk);
  }

  function invalidReason(v) {
    const c = checks(v);
    const reasons = [];
    if (!c.sigOk) reasons.push("chữ ký niêm phong không khớp nội dung đã niêm phong");
    if (!c.hasInclusion) reasons.push("phản hồi của máy chủ thiếu kết quả kiểm sổ cái");
    if (c.hasInclusion && c.treeKnown && !c.verifiedOk) {
      reasons.push("không kiểm được chứng minh niêm phong thuộc sổ cái (STH)");
    }
    return "Không đáng tin: " + reasons.join("; ") + ".";
  }

  function renderIssuer(v) {
    const issuer = v.issuer;
    let text = "Đơn vị niêm phong: ";
    if (issuer && typeof issuer.name === "string" && issuer.name !== "") {
      text += issuer.name;
      if (issuer.id !== null && issuer.id !== undefined && issuer.id !== "") {
        text += " (mã định danh: " + valueText(issuer.id) + ")";
      }
    } else {
      text += "(không xác định)";
    }
    setText(el.issuer, text);
  }

  function renderFields(v) {
    clear(el.fields);
    const labels = v.public_labels && typeof v.public_labels === "object" ? v.public_labels : {};
    const fields = v.public_fields && typeof v.public_fields === "object" ? v.public_fields : {};
    for (const name of Object.keys(fields)) {
      const label = Object.prototype.hasOwnProperty.call(labels, name) ? labels[name] : name;
      addRow(el.fields, valueText(label), valueText(fields[name]));
    }
    addRow(el.fields, "Thời điểm niêm phong", issuedAtText(v.issued_at));
    addRow(el.fields, "Mã niêm phong", valueText(v.seal_id));
    addRow(el.fields, "Số tệp đính kèm", valueText(v.attachments_count));
  }

  function renderLedger(v) {
    const inc = v.inclusion || {};
    if (inc.tree_size === null || inc.tree_size === undefined) {
      setText(el.ledger, "Sổ cái: chưa có STH phủ niêm phong này (chờ lần công bố STH kế tiếp).", "warn");
    } else if (inc.verified === true) {
      setText(el.ledger, "Sổ cái: đã kiểm niêm phong nằm ở vị trí " + valueText(inc.leaf_index) +
        " của cây có " + valueText(inc.tree_size) + " mục (máy chủ kiểm).", "ok");
    } else {
      setText(el.ledger, "Sổ cái: không kiểm được chứng minh thuộc cây (máy chủ kiểm).", "bad");
    }
    const anchored = inc.anchored;
    if (anchored && typeof anchored === "object") {
      setText(el.anchor, "Đã neo công khai (" + valueText(anchored.repo) + ", commit " +
        valueText(anchored.commit_sha) + ", cây " + valueText(anchored.tree_size) + " mục).", "ok");
    } else {
      setText(el.anchor, "Chưa neo công khai.", "warn");
    }
  }

  function renderBundle(v) {
    const inc = v.inclusion || {};
    show(el.bundleError, false);
    if (isInvalid(v)) {
      show(el.bundle, false);
      return;
    }
    show(el.bundle, true);
    if (inc.verified !== true) {
      setText(el.bundleNote, "Gói bằng chứng sẵn sàng sau lần công bố STH kế tiếp.");
      show(el.bundleGo, false);
      return;
    }
    if (v.require_file === true) {
      if (matchedDigest === null) {
        setText(el.bundleNote, "Chọn đúng tệp ở mục Đối chiếu tệp để tải gói bằng chứng.");
        show(el.bundleGo, false);
      } else {
        setText(el.bundleNote, "Gói chứa chữ ký, chứng minh thuộc sổ cái và STH, để kiểm lại ngoại tuyến.");
        show(el.bundleGo, true);
      }
    } else {
      setText(el.bundleNote, "Gói chứa chữ ký, chứng minh thuộc sổ cái và STH, để kiểm lại ngoại tuyến.");
      show(el.bundleGo, true);
    }
  }

  function renderView(v) {
    view = v;
    if (v.status === "SEAL_PENDING") {
      showStatus("Chờ niêm phong", "warn",
        "Văn bản đã được duyệt, niêm phong đang được hoàn tất. Thử lại sau ít phút.");
      return;
    }
    if (isInvalid(v)) {
      // Không đáng tin thì không hiển thị gì khác (đơn vị, trường, sổ cái, ô tệp, gói): chỉ huy hiệu và lý do.
      showStatus("Không hợp lệ", "bad", invalidReason(v));
      return;
    } else if (v.status === "REVOKED") {
      showStatus("Đã thu hồi", "bad", "Niêm phong này đã bị thu hồi: không dùng làm căn cứ xác nhận văn bản.");
    } else if (v.status === "VALID") {
      const { sigOk, verifiedOk, anchoredOk } = checks(v);
      if (sigOk && verifiedOk && anchoredOk) {
        showStatus("Hợp lệ", "ok", "Chữ ký niêm phong khớp nội dung đã niêm phong, niêm phong đã nằm trong sổ cái và STH phủ nó đã được neo công khai (máy chủ kiểm).");
        // Đã thuộc sổ cái nhưng STH chưa neo công khai: chưa có mốc bên ngoài để đối chiếu, không báo "Hợp lệ" trần.
      } else if (sigOk && verifiedOk) {
        showStatus("Hợp lệ — chưa neo công khai", "unanchored",
          "Chữ ký niêm phong khớp nội dung và niêm phong đã nằm trong sổ cái (máy chủ kiểm), nhưng STH phủ nó chưa được neo công khai. Thử lại sau lần neo kế tiếp.");
      } else {
        // Chữ ký đúng nhưng chưa có STH phủ lá: không báo "Hợp lệ" trần.
        showStatus("Chữ ký hợp lệ — đang chờ công bố vào sổ cái", "wait",
          "Chữ ký niêm phong khớp nội dung, nhưng niêm phong chưa nằm trong STH nào đã công bố. Thử lại sau lần công bố STH kế tiếp.");
      }
    } else {
      showStatus("Không hợp lệ", "bad", "Trạng thái niêm phong không nhận diện được.");
      return;
    }
    renderIssuer(v);
    renderFields(v);
    renderLedger(v);
    show(el.fileCheck, v.require_file === true && !isInvalid(v));
    renderBundle(v);
  }

  // ---------------------------------------------------------------- tải trạng thái niêm phong
  async function load() {
    const mine = ++generation;
    resetResult();
    show(el.error, false);
    const raw = location.hash.replace(/^#/, "").trim().toUpperCase();
    el.input.value = raw;
    if (raw === "") {
      sealId = null;
      return;
    }
    if (!SEAL_ID.test(raw)) {
      sealId = null;
      setText(el.error, "Mã niêm phong không đúng dạng (26 ký tự gồm chữ A–Z và số 2–7).", "bad");
      show(el.error, true);
      return;
    }
    sealId = raw;
    showStatus("Đang kiểm tra…", "warn", "");
    let resp;
    try {
      resp = await api(sealUrl(""));
    } catch (_err) {
      if (mine !== generation) return;
      showStatus("Chưa kiểm được", "warn", "Không kết nối được máy chủ, thử lại sau.");
      return;
    }
    if (mine !== generation) return;
    if (resp.status === 404) {
      showStatus("Không tìm thấy", "bad", "Mã niêm phong không tồn tại hoặc không được công khai.");
      return;
    }
    if (resp.status === 503) {
      showStatus("Chưa kiểm được", "warn", "Tạm thời chưa kiểm được chữ ký, thử lại sau");
      return;
    }
    if (resp.status === 429) {
      showStatus("Chưa kiểm được", "warn", "Quá nhiều lượt kiểm tra, thử lại sau ít phút.");
      return;
    }
    if (!resp.ok) {
      showStatus("Chưa kiểm được", "warn", "Máy chủ trả lỗi " + String(resp.status) + ", thử lại sau.");
      return;
    }
    let body;
    try {
      body = await resp.json();
    } catch (_err) {
      if (mine !== generation) return;
      showStatus("Chưa kiểm được", "warn", "Phản hồi của máy chủ không đọc được.");
      return;
    }
    if (mine !== generation) return;
    if (body === null || typeof body !== "object") {
      showStatus("Chưa kiểm được", "warn", "Phản hồi của máy chủ không đọc được.");
      return;
    }
    renderView(body);
  }

  // ---------------------------------------------------------------- băm tệp tại trình duyệt, gửi :check
  async function sha256Hex(picked) {
    const buffer = await picked.arrayBuffer();
    const digest = await crypto.subtle.digest("SHA-256", buffer);
    return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  }

  async function onFilePicked() {
    const mine = generation;
    const pick = ++pickToken;
    matchedDigest = null;
    show(el.fileHash, false);
    setText(el.fileResult, "");
    if (view !== null) renderBundle(view);
    const picked = el.fileInput.files && el.fileInput.files[0];
    if (!picked || sealId === null) return;
    if (!(window.crypto && crypto.subtle)) {
      setText(el.fileResult, "Trình duyệt không có WebCrypto (cần mở trang qua https): không băm được tệp.", "bad");
      return;
    }
    let hex;
    try {
      setText(el.fileResult, "Đang tính mã băm…");
      hex = await sha256Hex(picked);
    } catch (_err) {
      if (pick !== pickToken) return;
      setText(el.fileResult, "Không đọc được tệp này để tính mã băm.", "bad");
      return;
    }
    if (mine !== generation || pick !== pickToken) return;
    if (!SHA256_HEX.test(hex)) return;
    setText(el.fileHash, "SHA-256: " + hex);
    show(el.fileHash, true);
    let resp;
    try {
      resp = await api(sealUrl(":check"), jsonPost(hex));
    } catch (_err) {
      if (mine !== generation || pick !== pickToken) return;
      setText(el.fileResult, "Không kết nối được máy chủ, thử lại sau.", "warn");
      return;
    }
    if (mine !== generation || pick !== pickToken) return;
    if (!resp.ok) {
      setText(el.fileResult, resp.status === 429 ? "Quá nhiều lượt kiểm tra, thử lại sau ít phút."
        : "Chưa đối chiếu được (máy chủ trả lỗi " + String(resp.status) + ").", "warn");
      return;
    }
    let body = null;
    try {
      body = await resp.json();
    } catch (_err) {
      body = null;
    }
    if (mine !== generation || pick !== pickToken) return;
    if (body && body.status === "SEAL_PENDING") {
      setText(el.fileResult, "Niêm phong đang chờ hoàn tất: chưa đối chiếu được, thử lại sau.", "warn");
    } else if (body && body.match === true) {
      matchedDigest = hex;
      setText(el.fileResult, "Khớp: tệp này đúng là tệp đã được niêm phong.", "ok");
    } else {
      setText(el.fileResult,
        "Không khớp: tệp này khác tệp đã được niêm phong (đã bị sửa hoặc là tệp khác).", "bad");
    }
    if (view !== null) renderBundle(view);
  }

  // ---------------------------------------------------------------- tải gói bằng chứng
  function saveText(text, name) {
    const blob = new Blob([text], { type: "application/json" });
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = name;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(function () { URL.revokeObjectURL(href); }, 10000);
  }

  // Tên tệp do máy chủ đặt (Content-Disposition); chỉ nhận đúng dạng dxos-seal-<seal_id>.json của mã đang xem,
  // ngược lại tự dựng đúng tên đó.
  function bundleName(resp) {
    const expected = "dxos-seal-" + sealId + ".json";
    const disposition = resp.headers.get("Content-Disposition") || "";
    const m = /filename="([^"]+)"/.exec(disposition);
    return m !== null && m[1] === expected ? m[1] : expected;
  }

  async function onBundle() {
    if (view === null || sealId === null) return;
    const mine = generation;
    const pick = pickToken;
    const needsFile = view.require_file === true;
    const digest = matchedDigest;
    if (needsFile && digest === null) return;
    show(el.bundleError, false);
    el.bundleGo.disabled = true;
    try {
      const resp = needsFile ? await api(sealUrl(":bundle"), jsonPost(digest)) : await api(sealUrl("/bundle"));
      if (mine !== generation || pick !== pickToken) return;
      if (!resp.ok) {
        setText(el.bundleError, resp.status === 503 ? "Tạm thời chưa dựng được gói (chưa kiểm được khóa), thử lại sau."
          : "Chưa tải được gói bằng chứng (máy chủ trả lỗi " + String(resp.status) + ").", "bad");
        show(el.bundleError, true);
        return;
      }
      const text = await resp.text();
      if (mine !== generation || pick !== pickToken) return;
      saveText(text, bundleName(resp));
    } catch (_err) {
      if (mine !== generation || pick !== pickToken) return;
      setText(el.bundleError, "Không kết nối được máy chủ, thử lại sau.", "bad");
      show(el.bundleError, true);
    } finally {
      el.bundleGo.disabled = false;
    }
  }

  // ---------------------------------------------------------------- nhập tay mã niêm phong
  function onGo() {
    const wanted = el.input.value.trim().toUpperCase();
    const next = wanted === "" ? "" : "#" + wanted;
    if (location.hash === next || (location.hash === "" && next === "")) {
      load();
    } else {
      location.hash = next;                    // kích hoạt hashchange → load()
    }
  }

  el.go.addEventListener("click", onGo);
  el.input.addEventListener("keydown", function (ev) {
    if (ev.key === "Enter") onGo();
  });
  el.fileInput.addEventListener("change", onFilePicked);
  el.bundleGo.addEventListener("click", onBundle);
  window.addEventListener("hashchange", load);
  load();
})();
