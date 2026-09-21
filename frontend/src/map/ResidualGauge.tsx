import { useLive } from '@/store/live'
import { residualBucket } from './choropleth'
import './gauge.css'

/**
 * The residual gauge (MVP.md §8): r̂(t) per DK zone as a small system-health indicator in the
 * app bar. It is the honesty signal about data closure and is never hidden — "—" when the
 * identity cannot be formed, never 0.
 */
export function ResidualGauge() {
  const zones = useLive((s) => s.state?.zones)
  const ids = ['DK1', 'DK2']
  return (
    <div className="emap-gauge" role="group" aria-label="reconciliation residual" data-testid="residual-gauge">
      <span className="emap-gauge__title" title="r̂ = (Σgen − Σload − X) / Σload, on raw measurements">
        r̂
      </span>
      {ids.map((id) => {
        const z = zones?.[id]
        const v = z?.live ? z.residual_hat : null
        const b = residualBucket(v)
        const pct = v == null ? null : Math.max(-0.3, Math.min(0.3, v))
        return (
          <span key={id} className="emap-gauge__zone" title={v == null ? `${id}: identity cannot be formed` : `${id}: residual ${((z?.residual ?? 0) | 0).toLocaleString('en-US')} MW = ${(v * 100).toFixed(1)} % of load (${b.label})`}>
            <span className="emap-gauge__label">{id}</span>
            <span className={`emap-gauge__bar ${b.cls}`}>
              {pct != null && (
                <span className="emap-gauge__fill" style={{ left: pct < 0 ? `${50 + (pct / 0.3) * 50}%` : '50%', width: `${(Math.abs(pct) / 0.3) * 50}%` }} />
              )}
            </span>
            <span className="emap-gauge__value">{v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(1)}%`}</span>
          </span>
        )
      })}
    </div>
  )
}
