// Runtime smoke test against a running backend + frontend, driving the *installed* Chrome via
// playwright-core (no browser download). Reports what is actually mounted and interactive.
//
//   node scripts/smoke.mjs [url]           default http://localhost:5174
//
// Exit code 1 on any failed check. Screenshots land in $EMAP_SHOTS (default: ./.smoke).
import { chromium } from 'playwright-core'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const url = process.argv[2] ?? 'http://localhost:5174'
const outDir = process.env.EMAP_SHOTS ?? path.resolve('.smoke')
mkdirSync(outDir, { recursive: true })
const failures = []
const check = (ok, msg) => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${msg}`)
  if (!ok) failures.push(msg)
}

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const consoleErrors = []
page.on('console', (m) => m.type() === 'error' && consoleErrors.push(m.text()))
page.on('pageerror', (e) => consoleErrors.push(String(e)))

await page.goto(url, { waitUntil: 'networkidle' })
await page.waitForSelector('.react-flow__node', { timeout: 20000 })
const requests = new Set()
page.on('request', (r) => requests.add(new URL(r.url()).host))

async function counts() {
  return page.evaluate(() => ({
    nodes: document.querySelectorAll('.react-flow__node').length,
    edges: document.querySelectorAll('.react-flow__edge').length,
    byType: Object.fromEntries(
      ['source', 'grid', 'consumption', 'storage', 'cluster'].map((t) => [
        t,
        document.querySelectorAll(`.react-flow__node-${t}`).length,
      ]),
    ),
  }))
}

for (const level of [0, 1, 2]) {
  await page.getByRole('radio', { name: new RegExp(`^Π${level} `) }).click()
  await page.waitForTimeout(600)
  const c = await counts()
  console.log(`level ${level}: mounted nodes=${c.nodes} edges=${c.edges} byType=${JSON.stringify(c.byType)}`)
  check(c.nodes > 0 && c.edges > 0, `level ${level} renders nodes and edges`)
  if (level === 2) {
    check(
      c.byType.source > 0 && c.byType.grid > 0 && c.byType.consumption > 0 && c.byType.storage > 0,
      'level 2 mounts all four typed node styles',
    )
  }
  await page.screenshot({ path: path.join(outDir, `level${level}.png`) })
}

// --- click selects (LIAM corridor highlight) ---------------------------------------------------
// Level 0 (zones) has no overlapping cards: a real hit-test click must select exactly that node.
await page.getByRole('radio', { name: /^Π0 / }).click()
await page.waitForTimeout(400)
const zone = page.locator('.react-flow__node[data-id="DK1"]')
await zone.click()
await page.waitForTimeout(300)
let readout = (await page.locator('text=selected').first().textContent().catch(() => '')) ?? ''
check(readout.includes('DK1'), `level 0: clicking DK1 selects it (readout: "${readout.trim()}")`)
let selectedIds = await page.$$eval('.react-flow__node.selected', (els) => els.map((e) => e.getAttribute('data-id')))
check(selectedIds.length === 1 && selectedIds[0] === 'DK1', `exactly the clicked node is selected (${selectedIds})`)
const lit = await page.$$eval('.react-flow__edge-path', (ps) => ps.filter((p) => getComputedStyle(p).opacity === '1').length)
const dim = await page.$$eval('.react-flow__edge-path', (ps) => ps.filter((p) => +getComputedStyle(p).opacity < 0.2).length)
check(lit === 6 && dim === 37 - 6, `DK1's 6 corridors highlighted, the other 31 dimmed (lit=${lit}, dim=${dim})`)
await page.screenshot({ path: path.join(outDir, 'selected-level0.png') })
// Level 2: cards may overlap at the fitted zoom; the node on top receives the click and the
// readout must agree with whichever node React Flow marked selected.
await page.getByRole('radio', { name: /^Π2 / }).click()
await page.waitForTimeout(600)
const node = page.locator('.react-flow__node').first()
await node.click({ force: true })
await page.waitForTimeout(300)
readout = (await page.locator('text=selected').first().textContent().catch(() => '')) ?? ''
selectedIds = await page.$$eval('.react-flow__node.selected', (els) => els.map((e) => e.getAttribute('data-id')))
check(selectedIds.length === 1 && readout.includes(selectedIds[0]), `level 2: click selects the hit node ${selectedIds[0]} and readout agrees`)
await page.screenshot({ path: path.join(outDir, 'selected-level2.png') })

// --- nodes immovable ----------------------------------------------------------------------------
const before = await node.boundingBox()
await page.mouse.move(before.x + 10, before.y + 10)
await page.mouse.down()
await page.mouse.move(before.x + 200, before.y + 150, { steps: 8 })
await page.mouse.up()
await page.waitForTimeout(200)
const draggable = await page.evaluate(() => document.querySelectorAll('.react-flow__node.draggable').length)
check(draggable === 0, `no node is draggable (${draggable} with .draggable)`)

// --- pan/zoom responsiveness --------------------------------------------------------------------
await page.getByRole('radio', { name: /^Π2 / }).click()
await page.waitForTimeout(600)
const pane = page.locator('.react-flow__pane')
const box = await pane.boundingBox()
const cx = box.x + box.width / 2
const cy = box.y + box.height / 2
const t0 = Date.now()
const frames = await page.evaluate(
  () =>
    new Promise((resolve) => {
      let n = 0
      const start = performance.now()
      const tick = () => {
        n++
        if (performance.now() - start < 1500) requestAnimationFrame(tick)
        else resolve(n / ((performance.now() - start) / 1000))
      }
      requestAnimationFrame(tick)
      window.__zoomBurst = true
    }),
)
for (let i = 0; i < 12; i++) await page.mouse.wheel(0, i < 6 ? -300 : 300)
await page.mouse.move(cx, cy)
await page.mouse.down()
for (let i = 0; i < 10; i++) await page.mouse.move(cx + i * 40, cy + i * 20)
await page.mouse.up()
const elapsed = Date.now() - t0
console.log(`pan/zoom burst: ~${frames.toFixed(0)} fps idle baseline; 12 wheel + 10 drag steps in ${elapsed} ms`)
check(elapsed < 4000, 'pan/zoom interactions complete promptly')
const after = await counts()
console.log(`after zoom-in: mounted nodes=${after.nodes} (onlyRenderVisibleElements culls off-screen)`)
await page.screenshot({ path: path.join(outDir, 'zoomed.png') })

// --- fine level, zoomed to Denmark: typed cards legible, culling keeps the DOM small ------------
await page.getByRole('radio', { name: /^Π2 / }).click()
await page.waitForTimeout(400)
await page.evaluate(() => {
  const f = window.__emapFlow
  const dk = f.getNodes().filter((n) => n.data.zone === 'DK1' && n.type === 'grid').map((n) => ({ id: n.id }))
  return f.fitView({ nodes: dk, padding: 0.05, duration: 0 })
})
await page.waitForTimeout(600)
const dk = await counts()
console.log(`level 2 fitted to DK1 buses: mounted nodes=${dk.nodes} edges=${dk.edges} byType=${JSON.stringify(dk.byType)}`)
check(dk.nodes < 280 && dk.byType.grid > 0 && dk.byType.source > 0, 'DK1 view mounts a subset with typed nodes')
await page.screenshot({ path: path.join(outDir, 'dk1-level2.png') })
await page.evaluate(() => {
  const f = window.__emapFlow
  const ids = f.getNodes().filter((n) => n.data.name === 'Kassø' || n.data.name.startsWith('Landerupgård')).map((n) => ({ id: n.id }))
  return f.fitView({ nodes: ids, padding: 0.6, duration: 0 })
})
await page.waitForTimeout(600)
await page.screenshot({ path: path.join(outDir, 'dk1-detail.png') })

// --- Phase 2: live DK numbers on node faces, sidebar with switchable chart --------------------
await page.waitForFunction(() => document.querySelector('[data-testid="live-status"]')?.textContent?.includes('DK1 live'), null, { timeout: 30000 })
const live = await page.locator('[data-testid="live-status"]').textContent()
console.log(`footer: ${live?.trim()}`)
check(/gen \d+ MW/.test(live ?? ''), 'footer shows live DK1 generation from /api/state')
await page.getByRole('radio', { name: /^Π2 / }).click()
await page.waitForTimeout(500)
await page.evaluate(() => {
  const f = window.__emapFlow
  const dk = f.getNodes().filter((n) => n.data.zone === 'DK1').map((n) => ({ id: n.id }))
  return f.fitView({ nodes: dk, padding: 0.05, duration: 0 })
})
await page.waitForTimeout(600)
// only DK entities are live in Phase 2; neighbour aggregates (zgen:/zload:) stay "—" until Phase 4
const faces = await page.$$eval('.react-flow__node-source', (els) =>
  els.filter((e) => /^(plant|dg|store):/.test(e.getAttribute('data-id') ?? '')).map((e) => e.textContent ?? '').filter((t) => /P_gen\s*[\d,]+ MW/.test(t)).length,
)
const facesTotal = await page.$$eval('.react-flow__node-source', (els) => els.filter((e) => /^(plant|dg|store):/.test(e.getAttribute('data-id') ?? '')).length)
console.log(`source faces with a numeric P_gen: ${faces} of ${facesTotal} mounted`)
check(faces === facesTotal && facesTotal > 50, 'every mounted DK1 source face shows a live P_gen number (not "—")')
const loadFaces = await page.$$eval('.react-flow__node-consumption', (els) =>
  els.filter((e) => (e.getAttribute('data-id') ?? '').startsWith('load:')).map((e) => e.textContent ?? '').filter((t) => /D\s*[\d,]+ MW/.test(t)).length,
)
const loadTotal = await page.$$eval('.react-flow__node-consumption', (els) => els.filter((e) => (e.getAttribute('data-id') ?? '').startsWith('load:')).length)
check(loadFaces === loadTotal && loadTotal > 20, `every mounted DK1 consumption face shows live demand (${loadFaces}/${loadTotal})`)
// click Horns Rev (offshore wind) via the dev hook -> sidebar with vitals + charts
const hornsId = await page.evaluate(() => window.__emapFlow.getNodes().find((n) => n.data.name.startsWith('Horns Rev'))?.id)
await page.evaluate((id) => window.__emapFlow.fitView({ nodes: [{ id }], padding: 2, duration: 0 }), hornsId)
await page.waitForTimeout(400)
await page.locator(`.react-flow__node[data-id="${hornsId}"]`).click({ force: true })
await page.waitForSelector('aside h2', { timeout: 5000 })
const title = await page.locator('aside h2').textContent()
check(title?.startsWith('Horns Rev') ?? false, `sidebar opens for the clicked source (${title})`)
await page.waitForFunction(() => document.querySelectorAll('aside .recharts-area-area').length >= 3, null, { timeout: 20000 })
let charts = await page.locator('aside .recharts-area-area').count()
check(charts >= 3, `sidebar renders shadcn/Recharts charts (${charts}: node P_gen, zone demand, zone price)`)
const vit = await page.locator('aside').textContent()
check(/P_gen\s*[\d,.]+ MW/.test(vit ?? '') && /residual r/.test(vit ?? ''), 'sidebar vitals show P_gen and the zone residual')
await page.screenshot({ path: path.join(outDir, 'sidebar-24h.png') })
for (const r of ['week', 'month']) {
  await page.getByRole('radio', { name: r, exact: true }).click()
  await page.waitForTimeout(600)
  const ticks = await page.$$eval('aside .recharts-cartesian-axis-tick-value', (els) => els.map((e) => e.textContent))
  console.log(`range ${r}: x-axis ticks ${JSON.stringify(ticks.slice(0, 4))}…`)
  check(ticks.some((t) => /[A-Z][a-z]{2}/.test(t ?? '')), `range ${r} re-windows the chart (date ticks)`)
  await page.screenshot({ path: path.join(outDir, `sidebar-${r}.png`) })
}

check(consoleErrors.length === 0, `no console errors (${consoleErrors.slice(0, 3).join(' | ')})`)
const foreign = [...requests].filter((h) => !/localhost|127\.0\.0\.1/.test(h))
check(foreign.length === 0, `browser only talks to our own hosts (foreign: ${foreign.join(', ') || 'none'})`)

await browser.close()
console.log(failures.length ? `\n${failures.length} check(s) failed` : '\nall checks passed')
process.exit(failures.length ? 1 : 0)
