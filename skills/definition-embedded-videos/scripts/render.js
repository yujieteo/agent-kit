// Frame renderer: bun + the installed Chrome over the DevTools protocol. No packages.
//   bun render.js JOBS.json OUT_DIR frame.html TABS
// JOBS.json is a list of {id, html}. Each job becomes OUT_DIR/<id>.png (1920x1080).
// TABS pages work at once; each page is its own renderer process.
import { mkdtempSync, readFileSync, rmSync, writeFileSync, renameSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [jobsFile, outDir, shell, tabsArg] = process.argv.slice(2);
const jobs = JSON.parse(readFileSync(jobsFile, "utf8"));
const tabs = Math.max(1, Math.min(Number(tabsArg) || 4, jobs.length));
const chrome = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const profile = mkdtempSync(join(tmpdir(), "defvid-"));
const proc = Bun.spawn([chrome, "--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profile}`,
  "--hide-scrollbars", "--allow-file-access-from-files", "--no-first-run", "--no-default-browser-check",
  "--disable-extensions", "--force-color-profile=srgb", "--window-size=1920,1080", "about:blank"],
  { stderr: "pipe", stdout: "ignore" });

async function endpoint() {
  const dec = new TextDecoder(); let buf = "";
  for await (const chunk of proc.stderr) {
    buf += dec.decode(chunk);
    const m = buf.match(/DevTools listening on (ws:\/\/\S+)/);
    if (m) return m[1];
  }
  throw new Error("Chrome did not start: " + buf.slice(0, 400));
}

const ws = new WebSocket(await endpoint());
await new Promise((ok, no) => { ws.onopen = ok; ws.onerror = no; });
let seq = 0; const waiting = new Map();
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.id && waiting.has(m.id)) {
    const [ok, no] = waiting.get(m.id); waiting.delete(m.id);
    m.error ? no(new Error(m.error.message)) : ok(m.result);
  }
};
const send = (method, params = {}, sessionId) => new Promise((ok, no) => {
  const id = ++seq; waiting.set(id, [ok, no]);
  ws.send(JSON.stringify({ id, method, params, sessionId }));
});

async function page() {
  const { targetId } = await send("Target.createTarget", { url: pathToFileURL(shell).href });
  const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
  await send("Emulation.setDeviceMetricsOverride", { width: 1920, height: 1080, deviceScaleFactor: 1, mobile: false }, sessionId);
  for (let i = 0; i < 200; i++) {
    const r = await send("Runtime.evaluate", { expression: "typeof setFrame === 'function' && document.readyState === 'complete'" }, sessionId);
    if (r.result.value) return sessionId;
    await Bun.sleep(25);
  }
  throw new Error("frame.html did not load");
}

let next = 0, tight = 0;
async function worker() {
  const s = await page();
  while (next < jobs.length) {
    const job = jobs[next++];
    const r = await send("Runtime.evaluate", { expression: `setFrame(${JSON.stringify(job.html)})`, awaitPromise: true }, s);
    if (r.exceptionDetails) throw new Error("setFrame failed: " + JSON.stringify(r.exceptionDetails).slice(0, 300));
    if (r.result.value === false) tight++;
    const shot = await send("Page.captureScreenshot", { format: "png", optimizeForSpeed: true }, s);
    const tmp = join(outDir, job.id + ".part");
    writeFileSync(tmp, Buffer.from(shot.data, "base64"));
    renameSync(tmp, join(outDir, job.id + ".png"));
  }
}

let code = 0;
try {
  await Promise.all(Array.from({ length: tabs }, worker));
  if (tight) console.log(`  warning: ${tight} frames do not fit at the smallest text size. Split those beats.`);
} catch (e) { console.error(String(e)); code = 1; }
try { await send("Browser.close"); } catch {}
proc.kill(); await proc.exited;
try { rmSync(profile, { recursive: true, force: true }); } catch {}
process.exit(code);
