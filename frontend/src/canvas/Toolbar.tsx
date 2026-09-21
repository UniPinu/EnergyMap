import { Panel, useReactFlow, useStore } from '@xyflow/react'
import { Layers, Maximize, Minus, Plus } from 'lucide-react'
import { useMemo, type ReactNode } from 'react'
import type { Topology } from '@/lib/api'
import { projection } from '@/lib/topology'
import { LEVEL_ZOOM } from '@/lod/lod'
import { useUi } from '@/store/ui'
import { cn } from '@/lib/utils'
import './toolbar.css'

/**
 * LIAM's DesktopToolbar (ZoomControls | FitviewButton | ShowModeMenu), ported. The "show mode"
 * slot shows the cluster level the LOD engine chose; its buttons zoom to a level's range
 * (centred on Denmark), the engine then picks the level for that zoom.
 */
export function Toolbar({ levels, topology }: { levels: Array<{ level: number; name: string; description: string }>; topology: Topology }) {
  const zoom = useStore((s) => s.transform[2])
  const { zoomIn, zoomOut, fitView, setCenter } = useReactFlow()
  const level = useUi((s) => s.level)
  const lod = useUi((s) => s.lod)
  const dkCenter = useMemo(() => {
    const dk = topology.nodes.filter((n) => n.kind === 'grid' && n.zone.startsWith('DK'))
    const lat = dk.reduce((a, n) => a + n.lat, 0) / dk.length
    const lon = dk.reduce((a, n) => a + n.lon, 0) / dk.length
    return projection.project({ lat, lon })
  }, [topology])
  const goToLevel = (l: number) => {
    if (l === 0) return void fitView({ padding: 0.05, duration: 300 })
    const z = (LEVEL_ZOOM[l] ?? 1) * 1.35 // comfortably inside the level's band
    void setCenter(dkCenter.x, dkCenter.y, { zoom: z, duration: 300 })
  }
  return (
    <Panel position="bottom-center" className="emap-toolbar-wrapper">
      <div className="emap-toolbar" role="toolbar" aria-label="canvas toolbar">
        <div className="emap-toolbar__buttons">
          <IconButton label="Zoom out" onClick={() => void zoomOut()}>
            <Minus />
          </IconButton>
          <span className="emap-toolbar__zoom" aria-label="Zoom level">
            {Math.floor(zoom * 100)}%
          </span>
          <IconButton label="Zoom in" onClick={() => void zoomIn()}>
            <Plus />
          </IconButton>
        </div>
        <div className="emap-toolbar__separator" />
        <div className="emap-toolbar__buttons">
          <IconButton label="Fit view" onClick={() => void fitView({ padding: 0.05 })}>
            <Maximize />
          </IconButton>
        </div>
        <div className="emap-toolbar__separator" />
        <div className="emap-toolbar__buttons" role="radiogroup" aria-label="cluster level">
          <Layers className="emap-toolbar__menu-icon" aria-hidden />
          <span className="emap-toolbar__label">level</span>
          {levels.map((l) => (
            <button
              key={l.level}
              type="button"
              role="radio"
              aria-checked={level === l.level}
              title={l.description}
              onClick={() => goToLevel(l.level)}
              className={cn('emap-toolbar__text-button', level === l.level && 'emap-toolbar__text-button--active')}
            >
              Π{l.level} {l.name}
            </button>
          ))}
          <span className="emap-toolbar__label" title="mounted nodes / render budget" data-testid="lod-budget">
            {lod.visible}/{400}
            {lod.demoted ? ' ▾' : ''}
          </span>
        </div>
      </div>
    </Panel>
  )
}

function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" className="emap-toolbar__icon-button" aria-label={label} title={label} onClick={onClick}>
      {children}
    </button>
  )
}
