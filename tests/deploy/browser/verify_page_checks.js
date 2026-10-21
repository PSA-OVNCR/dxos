// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
//
// Kiểm trang đối soát tối giản bằng Chromium thật (Plan 02 Task 10). Opt-in: do
// core/tests/integration/test_verify_page_browser.py dựng niêm phong thật + Caddy + API rồi gọi script này.
// Biến môi trường: DXOS_BROWSER_DIR (ids.json, original.pdf, modified.pdf), DXOS_SHOT_DIR (nơi ghi ảnh chụp),
// NODE_PATH trỏ tới node_modules có `playwright`.
// Trang thật qua Caddy (CSP thật); ảnh chụp ghi vào DXOS_SHOT_DIR.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");
const DIR = process.env.DXOS_BROWSER_DIR;
const ids = JSON.parse(fs.readFileSync(path.join(DIR, "ids.json"), "utf8"));
const OUT = process.env.DXOS_SHOT_DIR;
const BASE = `${ids.base}/apps/verify-lite/`;
const log = (...a) => console.log(...a);
let failed = 0;
const crypto = require("crypto");
const sha256File = async (f) => crypto.createHash("sha256").update(fs.readFileSync(f)).digest("hex");
const check = (name, ok, extra) => { log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 760, height: 1100 }, acceptDownloads: true });
  const page = await ctx.newPage();
  const cspViolations = [], consoleErrors = [], requests = [];
  page.on("console", (m) => { if (m.type() === "error") { if (!/Failed to load resource: the server responded with a status of (404|503)/.test(m.text())) consoleErrors.push(m.text()); }; });
  page.on("pageerror", (e) => consoleErrors.push("pageerror " + e.message));
  page.on("request", (r) => requests.push({ url: r.url(), method: r.method(), post: r.postDataBuffer() }));
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => (window.__csp = (window.__csp || []).concat(e.violatedDirective + " " + e.blockedURI)));
  });
  const text = async (sel) => (await page.locator(sel).innerText()).trim();
  const open = async (sid) => { await page.goto("about:blank"); await page.goto(BASE + (sid ? "#" + sid : "")); await page.locator("#result:not([hidden]), #seal-error:not([hidden]), #seal-input").first().waitFor(); };
  const waitBadge = async (re) => { await page.waitForFunction((s) => new RegExp(s).test(document.getElementById("status-badge").textContent), re.source); };

  // 1) Tiêu đề, CSP header, không vi phạm
  await open(null);
  check("tiêu đề", (await page.title()) === "Kiểm tra tính xác thực và toàn vẹn văn bản điện tử");
  check("h1", (await text("h1")) === "Kiểm tra tính xác thực và toàn vẹn văn bản điện tử");
  check("không có kết quả khi chưa có mã", await page.locator("#result").isHidden());

  // 2) Niêm phong require_file: Hợp lệ, nhãn, đơn vị
  await open(ids.file);
  await waitBadge(/Hợp lệ/);
  log("  badge:", await text("#status-badge"), "| issuer:", await text("#issuer"));
  log("  fields:", JSON.stringify((await page.locator("#fields").innerText()).split("\n")));
  log("  ledger:", await text("#ledger-line"), "| anchor:", await text("#anchor-line"));
  // Niêm phong thật của test thuộc sổ cái nhưng STH chưa neo (không có repo neo): không phải "Hợp lệ" trần.
  check("Hợp lệ — chưa neo công khai (lớp unanchored, không ok)",
    (await text("#status-badge")) === "Hợp lệ — chưa neo công khai" && (await page.locator("#status-badge.unanchored").count()) === 1 && (await page.locator("#status-badge.ok").count()) === 0);
  check("Đơn vị niêm phong hiển thị", /^Đơn vị niêm phong: /.test(await text("#issuer")));
  check("Thời điểm niêm phong", (await page.locator("#fields dt", { hasText: "Thời điểm niêm phong" }).count()) === 1);
  check("nhãn Tiêu đề thay cho title / tên trường khi không có nhãn", (await page.locator("#fields dt", { hasText: /^ref$/ }).count()) === 1);
  check("ô chọn tệp hiện", await page.locator("#file-check").isVisible());
  check("chưa có nút gói trước khi khớp tệp", await page.locator("#bundle-go").isHidden());
  await page.screenshot({ path: path.join(OUT, "verify-page-1-valid-needs-file.png"), fullPage: true });

  // 2a) tệp đúng
  const before = requests.length;
  await page.setInputFiles("#file-input", path.join(DIR, "original.pdf"));
  await page.waitForFunction(() => /Khớp|Không khớp/.test(document.getElementById("file-result").textContent));
  check("tệp đúng: Khớp", (await text("#file-result")).startsWith("Khớp"), await text("#file-result"));
  check("nút gói hiện sau khi khớp", await page.locator("#bundle-go").isVisible());
  await page.screenshot({ path: path.join(OUT, "verify-page-2-file-match.png"), fullPage: true });
  const orig = fs.readFileSync(path.join(DIR, "original.pdf"));
  const checkReqs = requests.slice(before).filter((r) => r.url.includes(":check"));
  check("đúng 1 request :check, thân chỉ là {sha256}", checkReqs.length === 1 && /^\{"sha256":"[0-9a-f]{64}"\}$/.test(checkReqs[0].post.toString()), checkReqs.map((r) => r.post.toString()).join());
  const leaked = requests.slice(before).some((r) => r.post && r.post.length >= 64 && (r.post.includes(orig.subarray(0, 64)) || r.post.length > 300));
  check("không request nào mang nội dung tệp (thân < 300 byte, không chứa byte đầu của tệp)", !leaked);
  // tải gói
  const [dl] = await Promise.all([page.waitForEvent("download"), page.locator("#bundle-go").click()]);
  const bpath = path.join(DIR, "downloaded-bundle.json");
  await dl.saveAs(bpath);
  const bundle = JSON.parse(fs.readFileSync(bpath, "utf8"));
  check("tải gói: tên tệp như máy chủ đặt", dl.suggestedFilename() === `dxos-seal-${ids.file}.json`, dl.suggestedFilename());
  check("gói là JSON có chữ ký + sth", !!bundle && typeof bundle === "object" && (bundle.sth || bundle.seal), Object.keys(bundle).join(","));
  const bundleReq = requests.filter((r) => r.url.includes(":bundle"));
  check("POST :bundle chỉ mang hash", bundleReq.length === 1 && /^\{"sha256":"[0-9a-f]{64}"\}$/.test(bundleReq[0].post.toString()));

  // 2b) tệp sửa 1 byte
  await page.setInputFiles("#file-input", path.join(DIR, "modified.pdf"));
  await page.waitForFunction(() => /Không khớp/.test(document.getElementById("file-result").textContent));
  check("tệp sửa 1 byte: Không khớp", (await text("#file-result")).startsWith("Không khớp"), await text("#file-result"));
  check("nút gói ẩn khi không khớp", await page.locator("#bundle-go").isHidden());
  await page.screenshot({ path: path.join(OUT, "verify-page-3-file-mismatch.png"), fullPage: true });

  // 3) không cần tệp: nút gói GET
  await open(ids.nofile);
  await waitBadge(/Hợp lệ/);
  check("không cần tệp: không có ô chọn tệp", await page.locator("#file-check").isHidden());
  check("không cần tệp: có nút gói", await page.locator("#bundle-go").isVisible());
  const [dl2] = await Promise.all([page.waitForEvent("download"), page.locator("#bundle-go").click()]);
  check("GET bundle tải về dxos-seal-<id>.json", dl2.suggestedFilename() === `dxos-seal-${ids.nofile}.json`, dl2.suggestedFilename());
  log("  anchor-line:", await text("#anchor-line"));
  await page.screenshot({ path: path.join(OUT, "verify-page-4-valid-no-file.png"), fullPage: true });

  // 4) đã thu hồi, chờ niêm phong, chưa có STH phủ, mã lạ, sai dạng
  await open(ids.revoked); await waitBadge(/Đã thu hồi/);
  check("Đã thu hồi", (await text("#status-badge")) === "Đã thu hồi");
  await page.screenshot({ path: path.join(OUT, "verify-page-5-revoked.png"), fullPage: true });
  await open(ids.waiting); await waitBadge(/đang chờ công bố vào sổ cái/);
  check("chưa có STH phủ: không phải 'Hợp lệ' trần, có lớp wait riêng",
    (await text("#status-badge")) === "Chữ ký hợp lệ — đang chờ công bố vào sổ cái" && (await page.locator("#status-badge.wait").count()) === 1 && (await page.locator("#status-badge.ok").count()) === 0);
  check("chưa có STH phủ: dòng chờ STH, không nút gói", /Gói bằng chứng sẵn sàng sau lần công bố STH kế tiếp/.test(await text("#bundle-note")) && await page.locator("#bundle-go").isHidden(), await text("#bundle-note") + " | " + await text("#ledger-line"));
  await page.screenshot({ path: path.join(OUT, "verify-page-6-valid-waiting-sth.png"), fullPage: true });
  await open("A".repeat(26)); await waitBadge(/Không tìm thấy/);
  check("Không tìm thấy", true);
  await open("abc"); await page.locator("#seal-error:not([hidden])").waitFor();
  check("sai dạng: báo lỗi, không gọi API", /không đúng dạng/.test(await text("#seal-error")) && !requests.some((r) => r.url.includes("/seals/abc") || r.url.includes("/seals/ABC")));

  // 5) giả lập phản hồi độc hại: mọi giá trị chỉ là văn bản (XSS)
  await page.route("**/verify/v1/seals/" + "B".repeat(26), async (route) => {
    const evil = '<img src=x onerror="window.__pwned=1"><script>window.__pwned=2</script>';
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      seal_id: "B".repeat(26), status: "VALID", app_id: "x", issued_at: evil, key_version: 1,
      public_fields: { [evil]: evil, so_hieu: "12/QĐ" }, require_file: false, attachments_count: 0, signature_valid: true,
      inclusion: { leaf_index: 1, tree_size: 2, verified: true, anchored: { tree_size: 2, repo: evil, commit_sha: evil } },
      issuer: { name: evil, id: evil }, public_labels: { so_hieu: evil } }) });
  });
  await open("B".repeat(26)); await waitBadge(/Hợp lệ/);
  check("XSS: không tạo phần tử img/script từ dữ liệu", (await page.locator("#result img, #result script").count()) === 0 && !(await page.evaluate(() => window.__pwned)));
  check("XSS: chuỗi hiện nguyên văn", (await page.locator("#fields").innerText()).includes("<img src=x"));
  check("đã neo công khai → Hợp lệ trần, lớp ok", (await text("#status-badge")) === "Hợp lệ" && (await page.locator("#status-badge.ok").count()) === 1 && (await page.locator("#status-badge.unanchored").count()) === 0);
  await page.unroute("**/verify/v1/seals/" + "B".repeat(26));

  // 6) 503 và lỗi mạng
  await page.route("**/verify/v1/seals/" + "C".repeat(26), (route) => route.fulfill({ status: 503, contentType: "application/problem+json", body: '{"type":"keys-unavailable"}' }));
  await open("C".repeat(26)); await waitBadge(/Chưa kiểm được/);
  check("503: thông báo thử lại, không phải Không hợp lệ", /Tạm thời chưa kiểm được chữ ký, thử lại sau/.test(await text("#status-note")) && !/Không hợp lệ/.test(await text("#status-badge")));
  await page.unroute("**/verify/v1/seals/" + "C".repeat(26));
  // 7) chữ ký sai / inclusion sai -> Không hợp lệ
  await page.route("**/verify/v1/seals/" + "D".repeat(26), (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
    seal_id: "D".repeat(26), status: "VALID", app_id: "x", issued_at: "2026-10-21T01:00:00Z", key_version: 1, public_fields: { so_hieu: "BI-LOI-1" }, require_file: true,
    attachments_count: 1, signature_valid: false, inclusion: { leaf_index: 1, tree_size: 2, verified: true, anchored: { tree_size: 2, repo: "r", commit_sha: "c" } }, issuer: { name: "Cong ty gia mao", id: null }, public_labels: { so_hieu: "So hieu" } }) }));
  await open("D".repeat(26)); await waitBadge(/Không hợp lệ/);
  const onlyBadgeAndReason = async () =>
    (await text("#issuer")) === "" && (await page.locator("#fields dt").count()) === 0 && (await text("#ledger-line")) === "" &&
    (await text("#anchor-line")) === "" && await page.locator("#bundle").isHidden() && await page.locator("#file-check").isHidden() &&
    (await text("#status-note")).length > 0;
  check("signature_valid=false → Không hợp lệ chỉ có huy hiệu + lý do (không issuer, trường, sổ cái, ô tệp, gói)", await onlyBadgeAndReason(), await text("#status-note"));
  check("lý do nêu chữ ký sai", /chữ ký niêm phong không khớp/.test(await text("#status-note")));
  await page.unroute("**/verify/v1/seals/" + "D".repeat(26));
  await page.route("**/verify/v1/seals/" + "E".repeat(26), (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
    seal_id: "E".repeat(26), status: "VALID", app_id: "x", issued_at: "2026-10-21T01:00:00Z", key_version: 1, public_fields: { so_hieu: "BI-LOI-2" }, require_file: false,
    attachments_count: 1, signature_valid: true, inclusion: { leaf_index: 1, tree_size: 2, verified: false, anchored: null }, issuer: { name: "Cong ty gia mao", id: null }, public_labels: { so_hieu: "So hieu" } }) }));
  await open("E".repeat(26)); await waitBadge(/Không hợp lệ/);
  check("inclusion.verified=false (có STH) → Không hợp lệ, chỉ huy hiệu + lý do", await onlyBadgeAndReason() && /không kiểm được chứng minh/.test(await text("#status-note")));
  await page.unroute("**/verify/v1/seals/" + "E".repeat(26));

  await page.route("**/verify/v1/seals/" + "F".repeat(26), (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
    seal_id: "F".repeat(26), status: "VALID", app_id: "x", issued_at: "2026-10-21T01:00:00Z", key_version: 1, public_fields: {}, require_file: false,
    attachments_count: 0, signature_valid: true, inclusion: { leaf_index: 1, tree_size: null, verified: false, anchored: null }, issuer: null, public_labels: {} }) }));
  await open("F".repeat(26)); await waitBadge(/đang chờ công bố/);
  check("signature_valid=true + tree_size=null → chờ công bố, không Hợp lệ", !/^Hợp lệ$/.test(await text("#status-badge")) && await page.locator("#bundle-go").isHidden());
  await page.unroute("**/verify/v1/seals/" + "F".repeat(26));
  // inclusion.verified=true nhưng anchored null → "Hợp lệ — chưa neo công khai", không phải "Hợp lệ" trần
  await page.route("**/verify/v1/seals/" + "H".repeat(26), (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
    seal_id: "H".repeat(26), status: "VALID", app_id: "x", issued_at: "2026-10-21T01:00:00Z", key_version: 1, public_fields: {}, require_file: false,
    attachments_count: 0, signature_valid: true, inclusion: { leaf_index: 1, tree_size: 2, verified: true, anchored: null }, issuer: null, public_labels: {} }) }));
  await open("H".repeat(26)); await waitBadge(/chưa neo công khai/);
  check("verified=true + anchored=null → Hợp lệ — chưa neo công khai", (await text("#status-badge")) === "Hợp lệ — chưa neo công khai" && (await page.locator("#status-badge.unanchored").count()) === 1);
  await page.unroute("**/verify/v1/seals/" + "H".repeat(26));
  // thiếu inclusion → Không hợp lệ (không tin phản hồi thiếu kết quả kiểm)
  await page.route("**/verify/v1/seals/" + "G".repeat(26), (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
    seal_id: "G".repeat(26), status: "VALID", app_id: "x", issued_at: "2026-10-21T01:00:00Z", key_version: 1, public_fields: {}, require_file: false,
    attachments_count: 0, signature_valid: true, issuer: null, public_labels: {} }) }));
  await open("G".repeat(26)); await waitBadge(/Không hợp lệ/);
  check("thiếu inclusion → Không hợp lệ", true);
  await page.unroute("**/verify/v1/seals/" + "G".repeat(26));

  // 8) nhập tay mã
  await open(null);
  await page.fill("#seal-input", ids.nofile.toLowerCase());
  await page.press("#seal-input", "Enter");
  await waitBadge(/Hợp lệ/);
  check("nhập tay mã + Enter → đặt location.hash", page.url().endsWith("#" + ids.nofile));

  // 8b) tệp chọn sau ghi đè tệp chọn trước: phản hồi :check cũ về muộn không được hiện "Khớp"
  await open(ids.file); await waitBadge(/Hợp lệ/);
  let held = null, seen = 0, releaseFirst;
  const firstHeld = new Promise((res) => (releaseFirst = res));
  await page.route(/:check$/, async (route) => {
    seen++;
    if (seen === 1) { held = route; releaseFirst(); } else { await route.continue(); }
  });
  await page.setInputFiles("#file-input", path.join(DIR, "original.pdf"));      // :check thứ nhất bị giữ lại
  await firstHeld;
  await page.setInputFiles("#file-input", path.join(DIR, "modified.pdf"));      // :check thứ hai chạy bình thường
  await page.waitForFunction(() => /Không khớp/.test(document.getElementById("file-result").textContent));
  await held.continue();                                                         // phản hồi cũ (match: true) về muộn
  await page.waitForTimeout(700);
  check("pick cũ về muộn không đổi kết quả: vẫn Không khớp, không nút gói, hash của tệp sau",
    (await text("#file-result")).startsWith("Không khớp") && await page.locator("#bundle-go").isHidden() &&
    (await text("#file-hash")).includes((await sha256File(path.join(DIR, "modified.pdf")))), await text("#file-result"));
  await page.unroute(/:check$/);

  // 9) CSP
  const csp = await page.evaluate(() => window.__csp || []);
  check("không vi phạm CSP nào trong cả phiên", csp.length === 0, JSON.stringify(csp));
  check("không lỗi console/trang", consoleErrors.length === 0, JSON.stringify(consoleErrors));
  const resp = await page.request.get(BASE, { ignoreHTTPSErrors: true });
  log("  CSP header:", resp.headers()["content-security-policy"]);
  // thử chèn script nội tuyến phải bị chặn
  await open(null);
  const blocked = await page.evaluate(() => new Promise((res) => {
    document.addEventListener("securitypolicyviolation", () => res(true), { once: true });
    const s = document.createElement("script"); s.textContent = "window.__inline=1"; document.head.append(s);
    setTimeout(() => res(false), 1000);
  }));
  check("CSP chặn script nội tuyến", blocked && !(await page.evaluate(() => window.__inline)));
  // 10) di động
  await page.setViewportSize({ width: 375, height: 800 });
  await open(ids.file); await waitBadge(/Hợp lệ/);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  check("375px: không cuộn ngang", !overflow);
  await page.screenshot({ path: path.join(OUT, "verify-page-7-mobile.png"), fullPage: true });
  await browser.close();
  log(failed ? `FAILED ${failed}` : "ALL PASS");
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
