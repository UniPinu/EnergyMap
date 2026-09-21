# Northern European Electricity Balance Terminal — MVP Specification

> **Thesis.** This application is **not a map of power plants**. It is a **live, spatial balance sheet for electricity**: a node–edge network in which every node declares how much it _injects_ or _withdraws_, and the whole system is presented as a conservation identity that must (physically) close. The product is the _art of abstraction_ over that identity — a clean high-level summary of grid state that the user can drill into.

**Status:** formalized spec (rewrite of the original free-form MVP note).
**Scope:** Northern Europe, DK-centric, with cross-border context (DE, NO, SE, NL, PL, FI, Baltics).
**Reading order:** §1 identity → §2 feasibility → §3 formal model → §4 LOD → §5 schema → §6 sources → §7 pipeline → §8 frontend → §9 scope.

---

## 1. Product identity and invariant

The grid is modeled as a directed graph $\mathcal{N} = (V, E)$ evolving over discrete time $t$. Each node carries a signed **net injection**; each edge carries a signed **power flow**. The application's defining invariant is nodal power balance (Kirchhoff / Tellegen). Everything the UI shows is a projection of that invariant at some level of abstraction.

The user is greeted with the coarsest projection (a few zone-level super-nodes summarizing the region), and descends into finer projections (buses, then individual plants) on demand. Detail is _earned by zooming_, never dumped up front.

---

## 2. Feasibility assessment

Verdict: **feasible as an academic / portfolio MVP, provided the scope is cut along the lines below.** The ambition ("live per-node balance sheet for all of Northern Europe") exceeds what public live data supports at full resolution; the achievable version is a **zonal balance sheet with DK at fine granularity and neighbors at zone granularity**, rendered through a level-of-detail engine.

### 2.1 Component-by-component (RAG)

| Component                                      | Rating                   | Notes                                                                                                                                                                                                                                                                                          |
| ---------------------------------------------- | ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Static topology (buses, lines, links, coords)  | 🟢                       | PyPSA-Eur ships an open, coordinate-carrying transmission network (AC ≥ 220 kV + all HVDC) as a `netCDF` PyPSA object; export once to GeoJSON/JSON. It is a **model network, not an authoritative engineering grid** — fine for a schematic.                                                   |
| Danish live data (gen/load/price/exchange)     | 🟢                       | Energinet _Energi Data Service_: free, no auth, REST/JSON, DK1/DK2 price areas, 5-min–hourly. Clean and reliable.                                                                                                                                                                              |
| Rendering the network (React Flow + LIAM look) | 🟢                       | React Flow handles hundreds of nodes comfortably; LIAM (Apache-2.0) is a React-Flow ERD tool whose node/edge/sidebar styling is directly reusable/forkable.                                                                                                                                    |
| shadcn charts in sidebar (24h/week/month)      | 🟢                       | shadcn "Charts" are Recharts wrappers; timescale switching is a client-side window filter over one series.                                                                                                                                                                                     |
| ENTSO-E integration (neighbours)               | 🟡                       | Token by email, **~3 working-day lead time**; XML (IEC-62325) keyed by **EIC domain codes**; **hard limit 60 req/min** (→ 10-min ban). Use `entsoe-py` to parse to DataFrames. **A backend cache is mandatory** (Energinet also explicitly states the API is _not_ a live application source). |
| Topology ↔ live-data join                      | 🟡                       | Live data is **zonal/aggregated**, PyPSA-Eur topology is **per-bus**. They do not share keys; you must build a bus→zone mapping and _distribute_ zonal quantities onto buses (or aggregate buses to zones).                                                                                    |
| "Always in equilibrium"                        | 🟡                       | True in physics, **false in the measured data** (heterogeneous timestamps, resolutions, coverage gaps). Must be handled with an explicit **residual $r(t)$ + reconciliation step** and surfaced as a data-quality signal, not hidden.                                                          |
| Region strain meter                            | 🟡                       | Definable as a heuristic index (§3.5), but needs **historical baselines** ($D^{\text{ref}}$, price/ramp distributions) → cold-start requires backfill.                                                                                                                                         |
| Per-line flow tracing / price provenance       | 🔴 (MVP: scope to zones) | Bialek proportional-sharing (§3.6) requires a **full flow solution on every edge**; live APIs expose flows only on **cross-border interconnectors**, not internal lines. Provenance is realistic at **zone/interconnector** granularity, not per transmission line.                            |
| Per-plant real-time balance for all countries  | 🔴 (cut)                 | Only DK exposes fine granularity live; ENTSO-E per-unit generation is partial and lagged. Non-DK nodes are **zone-aggregated** in the MVP.                                                                                                                                                     |
| Price = f(strain) model                        | 🔴 (post-MVP)            | A research/modeling task. MVP ships the **strain meter as the key regressor** and stops there.                                                                                                                                                                                                 |

### 2.2 Two clarifications on the original note

- **shadcn maps** ([shadcnmaps.com](https://www.shadcnmaps.com)) _is_ a real library — copy-in **SVG region maps** (installed via the shadcn CLI, not an npm dependency) with region-click, choropleth and marker support. It is the natural **geographic / choropleth layer**: at the coarsest LOD it draws Northern-Europe zones tinted by strain/price, with region-click into the sidebar. **React Flow is not a geographic map** (no basemap/tiles) and does not need to be — it is the node-edge canvas for the finer levels, with nodes placed at **projected** lat/lon (Web-Mercator) so geography is _suggested_. The two compose (see §8): shadcn maps for the coarse choropleth, React Flow for the abstracted balance graph. ⚠️ Bidding zones (DK1/DK2, NO/SE zones) are sub-country, so a zone-level choropleth needs a **custom SVG map-data file** (or a country-level approximation for v1); stock shadcn maps are country/continent granularity.
- **"Nodes immovable once loaded"** is a one-line React Flow config (`nodesDraggable={false}` / `draggable: false` per node). Trivial.

### 2.3 Recommended MVP cut

1. **Region:** DK1 + DK2 at bus granularity; DE, NO2/NO5, SE3/SE4, NL, PL, FI as single zone super-nodes.
2. **Balance:** enforced at the **zonal** level; residual surfaced.
3. **Provenance:** at **interconnector** level (who is DK importing from, at what neighbouring price) — not per line.
4. **Strain:** shipped as an index; price model deferred.
5. **History:** ingest continuously from day 1 to build baselines; backfill DK from Energinet (multi-year available).

---

## 3. Formal model

### 3.1 Network

$$\mathcal{N} = (V, E), \qquad V = V_S \,\dot\cup\, V_G \,\dot\cup\, V_C \,\dot\cup\, V_B$$

- $V_S$ — **source** nodes (nuclear, hydro, thermal, offshore/onshore wind, solar farms)
- $V_G$ — **grid** nodes (substations / PyPSA buses where generation, demand and transmission meet)
- $V_C$ — **consumption** nodes (cities, industry, aggregated regional load)
- $V_B$ — **storage** nodes (batteries, pumped hydro — bidirectional)

$E \subseteq V \times V$ are directed transmission corridors (AC lines, HVDC links, interconnectors). Let $A \in \{-1,0,+1\}^{|V|\times|E|}$ be the **node–edge incidence matrix**: $A_{i,e} = +1$ if $e$ leaves $i$, $-1$ if $e$ enters $i$, $0$ otherwise.

Time is discretized on a canonical grid with step $\Delta t$ (§5); native source resolutions (5/15/60 min) are resampled onto it.

### 3.2 Node state vectors

Every node exposes exactly the three headline statistics from the original note, defined here.

**Source** $i \in V_S$ — measured output $P^{\text{gen}}_i(t) \ge 0$ [MW], available capacity $\overline{P}_i(t)$ (nameplate minus outages), carbon intensity $\kappa_i$ [tCO₂/MWh]:

$$
\underbrace{P^{\text{gen}}_i(t)}_{\text{primary}},\qquad
\underbrace{u_i(t) = \frac{P^{\text{gen}}_i(t)}{\overline{P}_i(t)} \in [0,1]}_{\text{secondary: utilization}},\qquad
\underbrace{\delta_i(t;\tau) = \frac{P^{\text{gen}}_i(t) - P^{\text{gen}}_i(t-\tau)}{P^{\text{gen}}_i(t-\tau)}}_{\text{tertiary: recent change}}
$$

> _Example (from note):_ Horns Rev → $P^{\text{gen}} = 842$ MW, $u = 0.68$, $\delta(\tau{=}1\text{h}) = +0.12$.

**Consumption** $j \in V_C$ — demand $D_j(t) \ge 0$, baseline $D^{\text{ref}}_j(t)$ (§3.5):

$$
D_j(t),\qquad
\rho_j(t) = \frac{D_j(t)}{D^{\text{ref}}_j(t)}\ \text{(demand vs. normal)},\qquad
\delta^D_j(t;\tau)\ \text{(recent change)}
$$

**Grid** $g \in V_G$ — through-flow, rating $\overline{T}_g$:

$$
T_g(t) = \tfrac12\!\!\sum_{e \ni g} |F_e(t)|,\qquad
\lambda_g(t) = \frac{T_g(t)}{\overline{T}_g} \in [0,1]\ \text{(loading)},\qquad
\operatorname{sgn}\big(n_g(t)\big)\ \text{(net direction)}
$$

**Storage** $b \in V_B$ — power $P_b(t)$ (sign convention: **discharge > 0**, charge < 0), energy $E_b(t)$, capacity $E^{\max}_b$, round-trip efficiency $\eta_b$:

$$
P_b(t),\qquad
\text{SoC}_b(t) = \frac{E_b(t)}{E^{\max}_b} \in [0,1],\qquad
\text{duration}\ =
\begin{cases}
E_b(t)/P_b(t) & P_b(t) > 0\ \text{(time to empty)}\\[4pt]
\big(E^{\max}_b - E_b(t)\big)/|P_b(t)| & P_b(t) < 0\ \text{(time to full)}
\end{cases}
$$

with $\dot{E}_b(t) = -P_b(t)$ when discharging and $-\eta_b P_b(t)$ when charging.

### 3.3 Edges

Each edge $e$ carries a signed flow $F_e(t)$ [MW] with rating (thermal limit or cross-border NTC) $\overline{F}_e$; loading $\ell_e(t) = |F_e(t)|/\overline{F}_e$. HVDC links additionally carry a controllable set-point; interconnectors carry the neighbouring zone's clearing price for provenance (§3.6).

### 3.4 The balance invariant + residual reconciliation

**Net injection** at node $i$ (generation and storage discharge in; load and storage charge out):

$$
n_i(t) = g_i(t) - d_i(t),\qquad
g_i = P^{\text{gen}}_i + \max(P_b,0),\quad
d_i = D_i + \max(-P_b,0).
$$

**Nodal conservation (KCL):** injections equal the net outflow on incident edges,

$$
\boxed{\,A\,F(t) = n(t)\,}\qquad\Longrightarrow\qquad \mathbf{1}^\top n(t) = 0\ \text{(system balance, lossless)}.
$$

With losses $L(t)$ and net export $X(t)$ across the region boundary, the system identity is

$$
\sum_{i\in V_S} P^{\text{gen}}_i(t) + \sum_{b} \max(P_b,0)
\;=\;
\sum_{j\in V_C} D_j(t) + \sum_b \max(-P_b,0) + L(t) + X(t).
$$

**The honest part.** Measured data will _not_ satisfy this. Define the **reconciliation residual**

$$
r(t) \;=\; \underbrace{\Big(\textstyle\sum \text{gen} - \sum \text{load} - X(t) - L(t)\Big)}_{\text{from raw measurements}},
\qquad
\hat{r}(t) = \frac{r(t)}{\sum_j D_j(t)}\ \text{(fraction of load)}.
$$

$\hat r(t)$ is a **first-class UI signal** (data-quality gauge), not something to hide.

**Reconciliation (MVP form).** Given noisy nodal injections $\tilde n$, produce a balanced state by minimal adjustment:

$$
n^\star(t) = \arg\min_{n}\ \|W^{1/2}(n - \tilde n(t))\|_2^2 \quad \text{s.t.}\quad \mathbf 1^\top n = 0,
$$

a weighted projection whose closed form redistributes $-r(t)$ across nodes in proportion to their inverse trust weights $W^{-1}$ (or onto a single **slack node** representing "unaccounted/boundary"). **Rigorous form (post-MVP):** full weighted-least-squares state estimation $x^\star = \arg\min_x \|z - h(x)\|^2_{W}$ over the measurement set $z$.

### 3.5 Region strain meter

Goal: a per-region scalar $S_R(t) \in [0,1]$ estimating supply–demand tightness (surges), later the key regressor of the price model.

**Baseline** (normal demand) by time-of-week seasonal profile:

$$
D^{\text{ref}}_R(t) = \operatorname{median}\big\{ D_R(t') : t' \equiv t \ (\mathrm{mod}\ \text{week}),\ t' \in \text{trailing } K \text{ weeks}\big\}.
$$

**Headroom instantiation (concrete MVP):** residual dispatchable capacity plus remaining import capability, relative to demand,

$$
H_R(t) = \Big(C^{\text{avail}}_R(t) + I^{\text{imp,avail}}_R(t)\Big) - D_R(t),
\qquad
S_R^{\text{head}}(t) = \operatorname{clip}\!\Big(1 - \tfrac{H_R(t)}{D_R(t)},\,0,\,1\Big).
$$

$S = 0$ when headroom equals demand; $S \to 1$ as headroom vanishes.

**Composite index (general form).** Standardize $m$ tightness signals against their trailing distributions and squash:

$$
S_R(t) = \sigma\!\Big(\textstyle\sum_{k=1}^{m} w_k\,\hat z_k(t)\Big),\qquad
\hat z_k = \frac{x_k - \mu_k}{\varsigma_k},\quad \sum_k w_k = 1,
$$

with candidate signals $x_k$: demand anomaly $\rho_R-1$; inverse reserve margin; interconnector saturation $|X_R|/\text{NTC}_R$; net-load ramp $\tfrac{d}{dt}(D_R - \text{VRE}_R)$; price percentile of $\pi_R(t)$. $\sigma$ = logistic.

**Downstream price model (post-MVP target).** With $S_R$ as principal feature,

$$
\pi_R(t) = \phi\big(S_R(t),\,\text{fuel prices},\,\widehat{\text{VRE}}_R(t),\dots\big),
\qquad \text{e.g. merit-order form}\ \ \pi_R = \pi_0\,e^{\beta S_R(t)}.
$$

### 3.6 Flow tracing and price provenance

_"Do not treat power as power — track where it came from and what was paid."_ Formalized as **power-flow tracing** under Bialek's proportional-sharing principle.

Let $P_i$ be the total through-flow at node $i$ (gross inflows + local generation). Define the **upstream distribution matrix** $A_u$:

$$
[A_u]_{ii} = 1,\qquad
[A_u]_{ik} = -\frac{|F_{k\to i}(t)|}{P_k(t)}\ \text{for } k \text{ feeding } i.
$$

Then nodal through-flows attributable to generators are $P = A_u^{-1} P_G$, and the **source-mix** of load $j$ (fraction of $D_j$ originating at source $i$) is read off as

$$
\Theta_{j,i}(t) = \frac{[A_u^{-1}]_{j,i}\,P^{\text{gen}}_i(t)}{\sum_{i'} [A_u^{-1}]_{j,i'}\,P^{\text{gen}}_{i'}(t)},
\qquad \sum_i \Theta_{j,i}(t) = 1.
$$

**Price provenance.** In a _zonal_ market each zone $z$ has one clearing price $\pi_z(t)$. The volume-weighted **origin price** paid by load $j$ is

$$
\pi^{\text{orig}}_j(t) = \sum_i \Theta_{j,i}(t)\,\pi_{z(i)}(t),
$$

and the provenance record for $j$ is the set $\big\{(i,\ \Theta_{j,i},\ \pi_{z(i)})\big\}_i$.

> **Modeling caveat (state honestly in-app).** Proportional sharing is a _convention_ (electrons are fungible), not a physical law; and financial provenance in a zonal market is really about **cross-zone flows and clearing-price differences**, not per-electron cost. **MVP scope:** compute $\Theta$ and $\pi^{\text{orig}}$ at **zone/interconnector** granularity (DK1↔{DE, NO2, SE3, NL, DK2}, etc.), where flows _are_ measured. Per-internal-line tracing requires a load-flow solve and is out of MVP scope.

---

## 4. Level-of-detail (LOD) abstraction engine

**Why it is mandatory.** React Flow renders each node as a DOM element and each edge as SVG — there is **no built-in virtualization or canvas batching**. Thousands of geographically accurate line geometries will not render at interactive frame rates. The abstraction _is_ the product, and it is also the performance strategy. React Flow's own levers: `React.memo` custom nodes/edges, `useCallback`/`useMemo` for props, the node `hidden` property to collapse subtrees, and simplified styles (avoid shadows/gradients/animation at scale).

### 4.1 Cluster hierarchy

A nested family of partitions of $V$ from coarse to fine:

$$
\Pi_0 \preceq \Pi_1 \preceq \cdots \preceq \Pi_L,
$$

- $\Pi_0$ — bidding zones / countries (a handful of super-nodes)
- $\Pi_\ell$ — PyPSA-Eur clustered buses at resolution $\ell$ (PyPSA-Eur clusters to a configurable bus count natively — reuse it)
- $\Pi_L$ — individual buses / plants

Each cluster $c$ is a **super-node** whose state aggregates its members. Aggregation is **balance-preserving** (net injection is additive):

$$
n_c(t) = \sum_{i \in c} n_i(t),\quad
P^{\text{gen}}_c = \sum_{i\in c} P^{\text{gen}}_i,\quad
D_c = \sum_{i\in c} D_i,\quad
\text{SoC}_c = \frac{\sum_{b\in c} E_b}{\sum_{b\in c} E^{\max}_b}.
$$

Inter-cluster edges are **bundled**: $F_{c\to c'}(t) = \sum_{e:\,i\in c,\,j\in c'} F_e(t)$.

### 4.2 Level selection and render budget

Zoom $z$ selects a base level via thresholds $z_0 < \cdots < z_L$: $\ell^\*(z) = \max\{\ell : z \ge z_\ell\}$. The rendered set is clusters at that level intersecting the viewport, **capped** by a hard DOM budget $N_{\max}$ (target 300–500 mounted nodes):

$$
\text{Rendered}(z,\text{vp}) = \Big\{\, c \in \Pi_{\ell^\*(z)} : \operatorname{bbox}(c) \cap \text{vp} \neq \varnothing \,\Big\},
\quad\text{decrement } \ell^\* \text{ until } |\text{Rendered}| \le N_{\max}.
$$

Everything outside the set is unmounted or `hidden`. Information density scales with level: coarse levels show only the **primary** statistic; secondary/tertiary and the sidebar chart appear on drill-in.

---

## 5. Canonical schema (the standardization layer)

All sources are normalized into one schema so conversion is trivial: **UTC** timestamps, SI-consistent units (MW, MWh, EUR/MWh), canonical $\Delta t$ via resampling, explicit quality flags.

### 5.1 Static entities

```
Node {
  id: string                     # stable canonical id
  kind: 'source'|'grid'|'consumption'|'storage'
  name: string
  zone: string                   # bidding zone, e.g. 'DK1'
  lat, lon: float                # for Mercator projection → immovable position
  cluster: { level:int -> cluster_id }   # membership in Π_0..Π_L
  capacity_mw: float|null        # nameplate / E_max for storage
  fuel: string|null              # nuclear|hydro|wind_offshore|solar|...
  co2_intensity: float|null      # tCO2/MWh
}
Edge {
  id: string
  from: node_id
  to: node_id
  kind: 'ac_line'|'hvdc_link'|'interconnector'
  rating_mw: float               # thermal limit / NTC
  length_km: float|null
}
```

### 5.2 Time series (long format — one shape for everything)

```
Sample {
  entity_id: string
  entity_kind: 'node'|'edge'
  quantity: 'p_gen'|'demand'|'flow'|'soc'|'price'|'strain'|'residual'|...
  t_utc: timestamp               # canonical grid
  value: float
  unit: string                   # MW | MWh | EUR/MWh | ratio
  source: string                 # energinet|entsoe|pypsa|derived
  resolution: string             # PT5M|PT15M|PT60M
  quality: 'measured'|'interpolated'|'estimated'|'missing'
}
```

Conversion between sources reduces to a **units map** + a **resampling operator** to $\Delta t$; joins are on `(entity_id, quantity, t_utc)`.

---

## 6. Data source mapping

| Canonical target                                        | Source                                | Raw handle                                                                  | Notes / limitation                                                                         |
| ------------------------------------------------------- | ------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Topology: `Node`(grid/source), `Edge`, coords, clusters | **PyPSA-Eur**                         | `netCDF` PyPSA network → export buses (`x,y`), lines, links                 | Model network, not authoritative; export once, version it.                                 |
| DK `p_gen` by fuel, `demand` (DK1/DK2)                  | **Energinet EDS**                     | `ProductionConsumptionSettlement` / production datasets                     | Free, no auth, JSON; 5-min–hourly.                                                         |
| DK `price` (spot)                                       | **Energinet EDS**                     | `Elspotprices` (DK1/DK2)                                                    | Hourly day-ahead.                                                                          |
| DK cross-border `flow`                                  | **Energinet EDS**                     | exchange / physical-flow datasets                                           | Signed per interconnector.                                                                 |
| Neighbour zone gen/load/price/flow                      | **ENTSO-E TP**                        | `A75` gen-per-type, `A65` load, `A44` day-ahead price, `A11` physical flows | XML + **EIC domain codes**; token (~3-day lead); **60 req/min** hard cap; use `entsoe-py`. |
| Plant capacity / fuel / coords                          | **PyPSA-Eur** powerplant DB (or OPSD) | table join to `Node`                                                        | Coverage varies by country.                                                                |
| Country generation mix (fallback)                       | **Ember / Energy-Charts**             | monthly/annual                                                              | Not physical topology; context only.                                                       |

**Ingestion constraints (hard):**

- Both providers forbid live client polling → **backend ingester + cache/DB is mandatory**; the client only ever reads your API.
- Respect cadence: 1 request per update-frequency with dynamic timestamps (Energinet: `start=now-3×freq`); throttle ENTSO-E to ≲ 27 req/min.
- Timestamps: Energinet exposes both UTC and DK-local columns; **store UTC**. ENTSO-E publishes in the area's local timezone with DST offsets — normalize on ingest.

---

## 7. Pipeline

```
[PyPSA-Eur .nc]                          (one-time / versioned)
      │  export
      ▼
① TOPOLOGY BUILD ──► Node/Edge graph + coords + cluster hierarchy Π₀…Π_L + zone map
                                   │
[Energinet EDS]  [ENTSO-E TP]      │
      │ scheduled pull (rate-limited, cached)
      ▼                            │
② INGEST (raw, per-source)         │
      │ UTC + units + resample Δt + quality flags
      ▼                            │
③ NORMALIZE ──► canonical `Sample` rows, mapped to Node/Edge ids ◄─┘
      │
      ▼
④ STATE COMPUTE ──► per-node state vectors (§3.2); reconcile A·F = n, residual r(t) (§3.4)
      │
      ▼
⑤ ANALYTICS ──► strain S_R (§3.5); flow-tracing Θ + provenance π_orig (§3.6); history store
      │
      ▼
⑥ SERVE (API) ──► level/viewport/time-window queries; time-series endpoints; all cached
      │
      ▼
⑦ RENDER (client) ──► React Flow + LIAM styling + LOD engine (§4) + sidebar charts + strain + calendar
```

Stages ①–⑥ are backend (scheduled jobs + API); ⑦ is the React client. The **calendar** feature = a query on the history store (⑤) parameterized by time; the shadcn sidebar charts = time-series endpoints (⑥) windowed to 24h/week/month.

---

## 8. Frontend specification

**Stack:** React + TypeScript, React Flow (`@xyflow/react`), **shadcn maps** (copy-in SVG region maps), Tailwind, shadcn/ui (Charts = Recharts). Node/edge/sidebar components adapted from **LIAM** (Apache-2.0).

**Two rendering layers (composed by LOD level):**

- **Geographic layer — shadcn maps.** At the coarse levels ($\Pi_0$, zone view) the region is an SVG **choropleth** of Northern-Europe bidding zones tinted by strain $S_R$ / price / residual, with region-click opening the sidebar. (Zone polygons need a **custom `map-data` SVG file**; stock maps are country-level — approximate at country granularity for v1.)
- **Balance-graph layer — React Flow.** At finer levels the canvas shows buses/plants as typed nodes and bundled corridors as edges, positioned by Web-Mercator projection of `(lat,lon)`.
- The LOD level function (§4.2) selects which layer is active for the current zoom; both feed the **same** sidebar.

**Aesthetic:** futuristic dark with green highlights (Supabase/Spotify register). LIAM default node styling as the base.

**Node visual encoding (color = type):**

| Node        | Color                        | Meaning                     |
| ----------- | ---------------------------- | --------------------------- |
| Source      | Emerald green (LIAM default) | Production                  |
| Grid        | Electric cyan                | Transmission / connectivity |
| Consumption | Amber / orange               | Demand / withdrawal         |
| Storage     | Violet                       | Stored / bidirectional      |

Each node face shows its three headline stats (§3.2). A secondary channel (border intensity / small gauge) encodes utilization $u$, loading $\lambda$, or SoC.

**Edges:** `step` / `smoothstep` (not straight, not geographically exact); highlight the full corridor when an incident node is selected (LIAM behavior). Edge thickness ∝ $|F_e|$, tint ∝ loading $\ell_e$.

**Behavior:**

- Nodes **immovable** once loaded (`nodesDraggable={false}`), positioned by Mercator projection of `(lat,lon)`.
- **Click → sidebar** (LIAM pattern): vital details not on the node face, a shadcn chart of consumption/price with user-switchable **24h (default) / week / month**, the node's balance contribution, and — for loads — the **provenance record** $\{(i,\Theta_{j,i},\pi_{z(i)})\}$.
- **Region strain meter:** per-zone gauge driven by $S_R(t)$; colored ramp.
- **Residual gauge:** $\hat r(t)$ shown as a small system-health indicator (honesty about data closure).
- **Calendar:** scrub to a past time; the whole network reloads to that historical state.
- **LOD:** zoom controls level per §4; open state = coarse zonal summary.

---

## 9. MVP scope, milestones, cut lines

**Milestones**

1. **M1 — Skeleton.** PyPSA-Eur export → static Node/Edge graph for DK + neighbours; React Flow render with LIAM styling, immovable Mercator-positioned nodes, step edges, 4 node types colored. _(No live data yet.)_
2. **M2 — DK live.** Energinet ingester + cache + canonical schema; DK1/DK2 gen/load/price/exchange wired to nodes; sidebar with shadcn 24h/week/month chart.
3. **M3 — Balance + LOD.** Zonal balance invariant + residual gauge; cluster hierarchy + zoom-driven LOD with $N_{\max}$ budget.
4. **M4 — Neighbours + strain.** ENTSO-E ingester (cached) for neighbour zones as super-nodes; strain meter $S_R$; calendar over history store.
5. **M5 — Provenance.** Interconnector-level flow tracing $\Theta$ + origin price $\pi^{\text{orig}}$ in the load sidebar.

**Explicitly out of MVP:** per-plant real-time balance for non-DK countries; per-internal-line flow tracing; the price = $f(\text{strain})$ predictive model; a real geographic basemap; full WLS state estimation.

## 10. Open questions / limitations to resolve

- **Bus↔zone distribution rule:** how to split a zone's aggregated gen/load onto its PyPSA buses (by capacity share? by population/GVA proxy for load?). Affects every per-node number for non-DK areas.
- **Bidding-zone boundaries** are not always available as clean polygons (may need manual construction from ENTSO-E/GISCO).
- **Loss & boundary term** $L(t), X(t)$ estimation quality directly drives the residual $\hat r(t)$.
- **Baseline cold-start:** $D^{\text{ref}}$ and strain distributions need weeks of history before the strain meter is trustworthy — backfill DK, accept a warm-up window for neighbours.
- **Reserve/available-capacity $C^{\text{avail}}$** for the strain headroom is not directly published live everywhere; may need an outage-adjusted nameplate proxy.
