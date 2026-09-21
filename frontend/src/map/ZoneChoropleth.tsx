import { useCallback, useMemo } from 'react'
import { ViewportPortal } from '@xyflow/react'
import { Map as ShadcnMap } from '@/components/shadcnmaps/map'
import { northernEuropeMapData } from '@/components/shadcnmaps/map-data/northern-europe'
import type { RegionEvent, RegionOverride } from '@/components/shadcnmaps/types'
import { WORLD } from '@/lib/topology'
import { useLive } from '@/store/live'
import { useUi } from '@/store/ui'
import { residualBucket } from './choropleth'
import './map.css'

/**
 * The geographic layer (MVP.md §8, CONTEXT.md §1.3/§1.5): a shadcn-maps SVG choropleth of the
 * bidding zones, tinted by the reconciliation residual r̂, region-click → sidebar. It is mounted
 * inside React Flow's viewport in world coordinates, so it is only ever drawn at Π₀ yet stays
 * spatially continuous with the node layers when the zoom crosses into Π₁.
 */
export function ZoneChoropleth() {
  const level = useUi((s) => s.level)
  const selectedId = useUi((s) => s.selectedId)
  const select = useUi((s) => s.select)
  const zones = useLive((s) => s.state?.zones)

  const regions = useMemo<RegionOverride[]>(
    () =>
      northernEuropeMapData.regions.map((r) => {
        const z = zones?.[r.id]
        const b = residualBucket(z?.live ? z.residual_hat : null)
        return {
          id: r.id,
          className: b.cls,
          tooltipContent: z?.live ? `${r.name} · r̂ ${((z.residual_hat ?? 0) * 100).toFixed(1)} % (${b.label})` : `${r.name} · no live data`,
        }
      }),
    [zones],
  )
  const onRegionClick = useCallback((e: RegionEvent) => select(e.region.id), [select])
  const visible = level === 0

  return (
    <ViewportPortal>
      <div className="emap-map" data-visible={visible} style={{ width: WORLD.width, height: WORLD.height }} aria-hidden={!visible}>
        <ShadcnMap
          data={northernEuropeMapData}
          regions={regions}
          selectedRegion={selectedId}
          onRegionClick={onRegionClick}
          showLabels={false}
          showTooltips={visible}
          enableZoom={false}
          aria-label="Northern Europe bidding zones"
        />
      </div>
    </ViewportPortal>
  )
}
