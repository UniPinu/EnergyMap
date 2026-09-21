import { Panel, useReactFlow, useStore } from '@xyflow/react'
import { Layers, Maximize, Minus, Plus } from 'lucide-react'
import type { ReactNode } from 'react'
import { useUi } from '@/store/ui'
import { cn } from '@/lib/utils'
import './toolbar.css'

/**
 * LIAM's DesktopToolbar (ZoomControls | FitviewButton | ShowModeMenu), ported. The "show mode"
 * slot holds the cluster level Π₀…Π_L until the zoom→level function takes over in Phase 3.
 */
export function Toolbar({ levels }: { levels: Array<{ level: number; name: string; description: string }> }) {
  const zoom = useStore((s) => s.transform[2])
  const { zoomIn, zoomOut, fitView } = useReactFlow()
  const level = useUi((s) => s.level)
  const setLevel = useUi((s) => s.setLevel)
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
              onClick={() => setLevel(l.level)}
              className={cn('emap-toolbar__text-button', level === l.level && 'emap-toolbar__text-button--active')}
            >
              Π{l.level} {l.name}
            </button>
          ))}
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
