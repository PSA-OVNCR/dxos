// SPDX-FileCopyrightText: 2026 PSA_OVNCR
// SPDX-License-Identifier: Apache-2.0
//
// Giai đoạn B của kiểm trình duyệt: niêm phong SEAL_PENDING. Opt-in: do
// core/tests/integration/test_verify_page_browser.py dựng niêm phong thật + Caddy + API rồi gọi script này.
// Cùng biến môi trường với verify_page_checks.js.
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path");
const DIR = process.env.DXOS_BROWSER_DIR;
const ids = JSON.parse(fs.readFileSync(path.join(DIR, "ids.json"), "utf8"));
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 760, height: 700 } });
  const page = await ctx.newPage();
  await page.goto(`${ids.base}/apps/verify-lite/#${ids.pending}`);
  await page.waitForFunction(() => /Chờ niêm phong/.test(document.getElementById("status-badge").textContent));
  const ok = (await page.locator("#fields dt").count()) === 0 && await page.locator("#bundle").isHidden() && await page.locator("#file-check").isHidden();
  console.log((ok ? "PASS" : "FAIL") + " Chờ niêm phong: không lộ trường, không ô tệp, không nút gói | " + (await page.locator("#status-note").innerText()));
  await page.screenshot({ path: path.join(process.env.DXOS_SHOT_DIR, "verify-page-8-pending.png"), fullPage: true });
  await b.close();
  process.exit(ok ? 0 : 1);
})();
