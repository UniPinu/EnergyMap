# CONTEXT.md — Library & API implementation reference

Purpose: give an experienced developer everything needed to build the Northern European Electricity Balance Terminal (see `MVP.md`) **without reading each library's docs individually**. Each section isolates the minimal usable surface, the code patterns to copy, and the gotchas that actually bite.

Conventions: 🟢 use directly · 🔁 replicate the *pattern*, don't depend on the package · ⚠️ gotcha.

---

## 0. Stack at a glance

| Concern | Library | Verdict | One-line role |
|---|---|---|---|
| Node–edge canvas (the balance graph) | **@xyflow/react** (React Flow v12) | 🟢 depend | Renders nodes/edges; owns pan/zoom/selection. |
| Node/edge/sidebar *look & interactions* | **LIAM** (`@liam-hq/erd-core`) | 🔁 replicate | ERD tool; copy its patterns, not its schema-bound component. |
| Geographic / choropleth backdrop | **shadcn maps** | 🟢 copy-in | SVG region maps (countries/zones), region-click, choropleth, markers. |
| Sidebar time-series charts | **shadcn/ui charts** (Recharts) | 🟢 copy-in | 24h/week/month consumption & price charts. |
| Static grid topology + coordinates | **PyPSA-Eur** | 🟢 preprocess | One-time export of buses/lines/links → GeoJSON/JSON. |
| DK live data | **Energinet EDS** | 🟢 ingest | Free JSON REST; DK1/DK2 gen/load/price/exchange. |
| Neighbour-zone live data | **ENTSO-E TP** | 🟢 ingest | XML REST; token-gated; use `entsoe-py`. |

Frontend baseline the copy-in libraries assume: **React 18+ (LIAM/shadcn-maps target React 19), Tailwind CSS v4, shadcn/ui configured.**

---

## 1. Frontend

### 1.1 React Flow — `@xyflow/react` v12 🟢

The whole interactive canvas. Everything else on the frontend hangs off this.

**Install & shell**
```bash
npm i @xyflow/react
```
```tsx
import { ReactFlow, Background, Controls, MiniMap, Panel } from '@xyflow/react'
import '@xyflow/react/dist/style.css'

<ReactFlow
  nodes={nodes} edges={edges}
  nodeTypes={nodeTypes} edgeTypes={edgeTypes}   // ⚠️ define OUTSIDE render / useMemo — see perf
  onNodeClick={onNodeClick}
  nodesDraggable={false}                          // ← MVP.md: nodes immovable once loaded
  onlyRenderVisibleElements                       // ← perf: skip off-viewport elements
  minZoom={0.2} maxZoom={8}
  fitView proOptions={{ hideAttribution: false }}
>
  <Background /> <Controls /> <MiniMap /> <Panel position="top-left">…</Panel>
</ReactFlow>
```

**Data model.** A node is `{ id, type, position:{x,y}, data:{…}, hidden? }`; an edge is `{ id, source, target, type, data?, hidden? }`. `type` keys into `nodeTypes`/`edgeTypes`. Our four node types (`source|grid|consumption|storage`) and edge types (`ac_line|hvdc_link|interconnector`) map straight onto these.

**Custom node** (this is where the LIAM look lives):
```tsx
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { memo } from 'react'

export const SourceNode = memo(({ data, selected }: NodeProps) => (
  <div className={cn('rf-node source', selected && 'ring-2 ring-emerald-400')}>
    <Handle type="target" position={Position.Left} />
    <div className="title">{data.name}</div>
    <div className="primary">{data.pGen} MW</div>
    <div className="secondary">{Math.round(data.u*100)}% capacity</div>
    <div className="tertiary">{data.delta>0?'↑':'↓'} {Math.abs(data.delta*100)}% / 1h</div>
    <Handle type="source" position={Position.Right} />
  </div>
))
const nodeTypes = { source: SourceNode, grid: GridNode, consumption: ConsumptionNode, storage: StorageNode }
```

**Custom edge** (step/smoothstep, highlight-on-select):
```tsx
import { BaseEdge, getSmoothStepPath, type EdgeProps } from '@xyflow/react'
export function FlowEdge({ sourceX,sourceY,targetX,targetY, data, selected }: EdgeProps) {
  const [path] = getSmoothStepPath({ sourceX,sourceY,targetX,targetY })
  return <BaseEdge path={path} style={{
    strokeWidth: data.thickness,                 // ∝ |F_e|
    stroke: loadingColor(data.loading),          // tint ∝ ℓ_e
    opacity: selected ? 1 : 0.6,
  }}/>
}
```
Built-in edge `type:'smoothstep'` or `'step'` needs no custom component if you don't need per-edge styling.

**Zoom-driven LOD (the core mechanism).** Read viewport, pick the cluster level, swap the node/edge arrays:
```tsx
import { useOnViewportChange, useReactFlow } from '@xyflow/react'
useOnViewportChange({ onChange: ({ zoom }) => setLevel(levelForZoom(zoom)) })
// then feed nodes/edges for that level; hide the rest with node.hidden=true
```
`useReactFlow()` gives `getViewport()`, `setViewport()`, `fitView()`, `getNodes()`. `useStore(selector)` reads internal state — **select narrowly** (see perf).

**Performance rules (non-negotiable at our scale — React Flow renders every node as DOM, every edge as SVG; no virtualization):**
1. `memo()` every custom node/edge; declare `nodeTypes`/`edgeTypes` outside render or via `useMemo`.
2. `useCallback` all handlers; `useMemo` objects passed as props (`defaultEdgeOptions`, `snapGrid`).
3. Never read the whole `nodes`/`edges` array inside a child component; keep derived state (e.g. `selectedIds`) in a separate store slice.
4. Collapse with the node `hidden` prop; render only the current LOD level + viewport (`onlyRenderVisibleElements`).
5. Keep node CSS cheap — avoid shadows/gradients/animations when many nodes are mounted.
6. Hard budget: target ≤ 300–500 mounted nodes; if a level exceeds it, drop to a coarser level (MVP.md §4.2).

**Useful extras:** React Flow *UI* (`reactflow.dev/ui`) ships copy-in components incl. a **Database Schema node** (LIAM-like), **Contextual Zoom** example, **Zoom Slider**, **Node Search** — direct references for our node + LOD work.

### 1.2 LIAM — patterns to replicate 🔁 (do **not** depend on `erd-core`)

LIAM (`liam-hq/liam`, Apache-2.0) is a TS monorepo; the diagram is `@liam-hq/erd-core`, exporting a single `ERDRenderer`, built on **@xyflow/react v12 + elkjs** auto-layout. `erd-core` is hard-bound to *database-schema* data (tables/columns/relationships), so it is the wrong dependency for an energy grid. Reimplement its **patterns** on React Flow directly and borrow its **visual style**.

| LIAM concept | Where it lives | Our analogue |
|---|---|---|
| `ERDRenderer` (owns `<ReactFlow>`, providers) | `erd-core` | Your `<GridCanvas>` wrapper. |
| Table node (header + rows, typed handles) | Table Node Components | 4 typed nodes (source/grid/consumption/storage), 3 stats each. |
| `useAutoLayout()` via **elkjs** | erd-core | Use elkjs **only** for abstracted/non-geographic layout; real nodes use projected lat/lon (§3). |
| Click table → detail panel | Session detail UI | Right sidebar: vital stats + shadcn charts + provenance. |
| Relationship edge highlight on hover/select | Diffing & Highlighting | Highlight full corridor + endpoints on node select. |
| Table visibility controls (show/hide) | Table Visibility Controls | LOD collapse / layer toggles. |
| Command palette (cmdk) | Command Palette | Node search / jump-to-zone (optional). |
| Theming: Tailwind + CSS variables (CSS Modules) | Styling & Theming | Same: token-based dark theme, emerald/cyan/amber/violet per node type. |

Stack to mirror: React 19, `@xyflow/react` 12.x, `elkjs` for layout, `valibot`/`zod` for validating incoming data, Tailwind + CSS variables. To study exact styling, read `frontend/packages/erd-core/src` in the repo; you're copying CSS/tokens and component structure, not importing.

⚠️ Don't `npm i @liam-hq/erd-core` and try to feed it grid data — its props are a parsed SQL schema. You'll fight it. Rebuild the ~4 components you need.

### 1.3 shadcn maps 🟢 (the geographic layer)

SVG region maps (**not** tile maps — no MapLibre/Mapbox). Copy-in via the shadcn CLI, like shadcn/ui. This is the coarse-LOD **choropleth backdrop** and zone selector.

**Install** (per map; browse maps at shadcnmaps.com/maps — continents, countries, US states, special):
```bash
npx shadcn@latest add @shadcnmaps/usa      # e.g. a country/region map
```
Drops files into `components/shadcnmaps/`: `map.tsx` (SVG renderer), `map-context.tsx` (state), `map-region.tsx`, `map-tooltip.tsx`, `map-marker.tsx`, `map-listbox.tsx` (a11y), `types.ts`, `maps/<name>.tsx` (the component, e.g. `USAMap`), `map-data/<name>.ts` (SVG path data).

**Usage — region click + choropleth:**
```tsx
'use client'
import { EuropeMap, type RegionId } from '@/components/shadcnmaps/maps/europe'

<EuropeMap
  onRegionClick={({ region }) => selectZone(region.id as RegionId)}
  // choropleth: color each region by strain S_R / price / residual
  regionProps={(id) => ({ fill: strainColor(strainByZone[id]) })}
/>
```
Interactive out of the box: hover, tooltip, full keyboard nav. Markers via `map-marker` (place source/storage points); see examples `/region-click`, `/choropleth`, `/markers`, `/zoom-pan`, `/controlled`. Theming = CSS variables (`/overview/theming`). There's an `llms.txt` at `/overview/llms` and a marker-generator tool.

⚠️ **Bidding zones are sub-country.** Standard maps exist at country/continent granularity; **DK1/DK2** (and NO/SE zones) won't ship as a stock map. Options: (a) approximate at country level for v1; (b) author a **custom `map-data/*.ts`** (it's just SVG `<path>` data + region ids) for zone polygons — build it from ENTSO-E/GISCO bidding-zone geometries projected to SVG. Custom maps are first-class here (the data file is the only map-specific piece).

### 1.4 shadcn/ui charts 🟢 (Recharts)

Sidebar consumption/price charts with 24h/week/month switching.

**Install:** `npx shadcn@latest add chart` → gives `ChartContainer`, `ChartTooltip`, `ChartTooltipContent`, `ChartLegend`, `ChartConfig`. Wraps **Recharts** (`npm i recharts`).

```tsx
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from '@/components/ui/chart'
import { Area, AreaChart, XAxis } from 'recharts'

const cfg = { demand:{label:'Demand (MW)',color:'var(--chart-1)'},
              price:{label:'Price (EUR/MWh)',color:'var(--chart-2)'} } satisfies ChartConfig

<ChartContainer config={cfg} className="h-48 w-full">
  <AreaChart data={series /* [{t, demand, price}] windowed to range */}>
    <XAxis dataKey="t" /* format by range */ />
    <Area dataKey="demand" stroke="var(--color-demand)" fill="var(--color-demand)" />
    <ChartTooltip content={<ChartTooltipContent />} />
  </AreaChart>
</ChartContainer>
```
**Timescale switch = pure client-side window filter** over one fetched series (`range ∈ {24h, week, month}` → slice/resample the array). No refetch needed if you fetch the widest window once. Theme via CSS vars `--chart-1..5` (dark theme → emerald/cyan/amber/violet to match node types).

### 1.5 How the three compose

- **Coarse LOD (`Π₀`, zone view):** shadcn-maps choropleth of Northern-Europe zones colored by strain/price + a residual gauge. Region click → sidebar.
- **Fine LOD (`Π_ℓ…Π_L`):** switch to the React Flow canvas — buses/plants as typed nodes, bundled flows as edges, positioned by projected lat/lon (§3). Node click → same sidebar (now with shadcn charts + provenance).
- **Sidebar** is one shared panel (LIAM detail-panel pattern) driven by the selected entity, whichever layer selected it.
- The LOD level function (MVP.md §4.2) decides which layer is active for the current zoom.

---

## 2. Data sources (backend ingesters — never call these from the browser)

⚠️ Both providers forbid live client polling and rate-limit hard. Run **scheduled server-side ingesters → cache/DB**; the browser only reads *your* API.

### 2.1 Energinet — Energi Data Service 🟢

Free, **no auth**, REST/JSON. Base: `https://api.energidataservice.dk/dataset/{Dataset}`.

**Query params:** `start`, `end` (Danish local time; supports dynamic `now`, `now-P1D`, `StartOfDay`…), `filter={"PriceArea":["DK1","DK2"]}` (JSON, equality only), `columns=`, `sort=col desc`, `limit=` (`0`=all; default 100), `offset=`. Response: `{ total, dataset, records:[ {...} ] }`. Also `/download?format=csv|json|XL`.

```bash
# DK1 spot price, last 24h
curl 'https://api.energidataservice.dk/dataset/Elspotprices?start=now-P1D&end=now&filter={"PriceArea":["DK1"]}'
```

**Datasets you need** (⚠️ confirm exact IDs in the catalog — names evolve):
| Need | Dataset (typical) | Resolution / keys |
|---|---|---|
| Near-real-time system state (prod by type, exchange, CO₂) | `PowerSystemRightNow` | ~5 min, DK1/DK2 |
| Settled production + consumption by type | `ProductionConsumptionSettlement` | hourly, `PriceArea` |
| Day-ahead spot price | `Elspotprices` | hourly, `PriceArea` (EUR & DKK) |
| CO₂ intensity | `CO2Emis` | 5 min, `PriceArea` |
| Cross-border physical exchange | exchange/flow dataset (catalog) | signed per interconnector |

**Caching cadence (their rule of thumb):** 1 request per update-frequency using a dynamic window, e.g. 5-min datasets → poll every 5 min with `start=now-PT15M`. Exceed limits → **HTTP 429** with a retry-after. Timestamps come in both UTC (`Minutes5UTC`/`HourUTC`) and DK (`…DK`) columns — **store UTC**.

### 2.2 ENTSO-E — Transparency Platform 🟢 (fiddlier)

Pan-European gen/load/price/flow, per bidding zone. XML (IEC-62325). Base: `https://web-api.tp.entsoe.eu/api`.

**Token (do this first — lead time):** register at transparency.entsoe.eu → email `transparency@entsoe.eu`, subject "RESTful API access", body = your account email → granted in ~3 working days → *My Account → generate token* (shown once).

**Request shape** (params are typed by code):
```
GET /api?securityToken=TOKEN
        &documentType=A75        # A44 day-ahead price · A65 load · A75 gen per type · A11 physical flow
        &processType=A16         # realised
        &in_Domain=10YDK-1--------W   # EIC code; DK2 = 10YDK-2--------M  (⚠️ verify)
        &periodStart=202609200000&periodEnd=202609210000   # yyyyMMddHHmm, area-local
```
Response = `…_MarketDocument` XML → `TimeSeries` → `Period`(`resolution` e.g. `PT60M`/`PT15M`) → `Point`(`position`,`quantity`/`price.amount`).

**Do not hand-parse XML — use `entsoe-py`:**
```python
from entsoe import EntsoePandasClient          # pip install entsoe-py
import pandas as pd
c = EntsoePandasClient(api_key=TOKEN)
start, end = pd.Timestamp('20260920', tz='Europe/Copenhagen'), pd.Timestamp('20260921', tz='Europe/Copenhagen')
gen   = c.query_generation('DK_1', start=start, end=end, psr_type=None)   # per production type
load  = c.query_load('DK_1', start=start, end=end)
price = c.query_day_ahead_prices('DK_1', start=start, end=end)
flow  = c.query_crossborder_flows('DK_1','DE_LU', start=start, end=end)   # per interconnector
```
**Limits (official):** ≤ **60 requests / minute** (breach → ~10-min IP ban; throttle to ~27/min); period ≤ 1 year/request; ≤ 100 `TimeSeries` per response. Data published in the area's local tz with DST — normalize to UTC on ingest. Domains are **EIC codes**, not ISO country codes.

### 2.3 PyPSA-Eur 🟢 (one-time topology export)

Open model of the European transmission grid (AC ≥ 220 kV + all HVDC, substations, power-plant DB, coordinates). Python + Snakemake; outputs a **PyPSA network as netCDF** (`.nc`). It is a **model**, not an authoritative engineering grid — perfect for a schematic.

**Get a network:** either run the Snakemake workflow (`base → simplified → clustered → composed → solved`; set cluster count in config) or load a released `.nc`. You want the **clustered** network at a few resolutions to seed the LOD hierarchy (`Π₀…Π_L`).

**PyPSA object model → our schema** (load with `pypsa`):
```python
import pypsa, json
n = pypsa.Network("clustered.nc")
# n.buses:      index, x (lon), y (lat), v_nom, country
# n.lines:      bus0, bus1, s_nom (rating), length
# n.links:      bus0, bus1, p_nom  → HVDC / interconnectors
# n.generators: bus, carrier (fuel), p_nom  → source nodes
# n.storage_units / n.stores: bus, p_nom, max_hours  → storage nodes
# n.loads:      bus, p_set  → consumption nodes
nodes = [{"id":b, "lat":r.y, "lon":r.x, "zone":r.country} for b,r in n.buses.iterrows()]
edges = [{"id":l, "from":r.bus0, "to":r.bus1, "kind":"ac_line", "rating_mw":r.s_nom}
         for l,r in n.lines.iterrows()] + \
        [{"id":k, "from":r.bus0, "to":r.bus1, "kind":"hvdc_link", "rating_mw":r.p_nom}
         for k,r in n.links.iterrows()]
json.dump({"nodes":nodes,"edges":edges}, open("topology.json","w"))
```
Buses carry `x,y` = lon,lat → project to screen coords for immovable React Flow positions. Clustering resolution is a config knob → generate one export per LOD level.

⚠️ **The join problem.** Live data (Energinet/ENTSO-E) is **zonal/aggregated**; PyPSA buses are **per-node**. There is no shared key. You must build a **bus→zone map** and a **distribution rule** to spread a zone's gen/load onto its buses (by capacity share, population/GVA proxy, etc.). This is the single most consequential modeling decision (MVP.md §10).

---

## 3. Cross-cutting

- **Canonical schema:** all sources normalize to the `Node`/`Edge`/`Sample` shapes in `MVP.md §5`. Everything is UTC, MW/MWh/EUR·MWh⁻¹, resampled to canonical Δt, with a `quality` flag.
- **Positioning:** node `position` in React Flow = Web-Mercator projection of `(lat,lon)`; shadcn-maps handles its own SVG viewBox. Keep one projection helper so both layers agree spatially.
- **Colour tokens (dark theme):** source = emerald, grid = electric cyan, consumption = amber, storage = violet; reuse as `--chart-*` so sidebar charts match node types.
- **Validation:** validate every ingested payload (valibot/zod) before it enters the canonical store — external feeds change shape without notice.

## 4. Cheat-sheet / gotchas

- React Flow has **no virtualization** → LOD + `hidden` + `onlyRenderVisibleElements` + memoization are mandatory, not optional.
- `nodeTypes`/`edgeTypes` defined inline = re-render storm. Hoist them.
- LIAM `erd-core` is schema-bound → replicate, don't import.
- shadcn-maps & shadcn-charts are **copy-in** (files land in your repo), not npm deps → no version lock, you own/edit them.
- Bidding-zone choropleth needs **custom SVG map-data**; stock maps are country-level.
- ENTSO-E token has a **~3-day lead** → request it on day 1. Throttle to ~27 req/min. EIC codes, not ISO.
- Energinet/ENTSO-E: **server-side cache only**; never fetch from the browser. Store UTC.
- PyPSA-Eur is a **model** and its buses don't key to zonal live data → build the bus→zone distribution rule early.
- "Equilibrium" never closes on raw data → always compute and display the residual (MVP.md §3.4).
