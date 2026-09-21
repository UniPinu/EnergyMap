import { useEffect, useMemo } from 'react'
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from 'recharts'
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from '@/components/ui/chart'
import type { SeriesResponse } from '@/lib/api'
import { seriesKey, useLive } from '@/store/live'
import { downsample, tickLabel, windowPoints, type Range } from './windowing'

/**
 * One quantity of one entity over the selected range. The series is fetched once for the
 * widest window and windowed/downsampled here (CONTEXT.md §1.4).
 */
export function SeriesChart({
  entityId,
  quantity,
  label,
  color,
  range,
  height = 140,
}: {
  entityId: string
  quantity: SeriesResponse['quantity']
  label: string
  color: string
  range: Range
  height?: number
}) {
  const key = seriesKey(entityId, quantity)
  const ensure = useLive((s) => s.ensureSeries)
  const entry = useLive((s) => s.series[key])
  useEffect(() => ensure(entityId, quantity), [ensure, entityId, quantity])

  const config = useMemo<ChartConfig>(() => ({ v: { label, color } }), [label, color])
  const data = useMemo(() => {
    if (!entry || entry === 'loading' || 'error' in entry) return []
    return downsample(windowPoints(entry.points, range), range)
  }, [entry, range])

  // Deterministic time axis: numeric epoch-ms with five evenly spaced ticks (no label-measurement heuristics).
  const ticks = useMemo(() => {
    if (data.length < 2) return data.map((d) => d.t)
    const t0 = data[0]!.t
    const t1 = data[data.length - 1]!.t
    return Array.from({ length: 5 }, (_, i) => t0 + ((t1 - t0) * i) / 4)
  }, [data])
  const unit = entry && entry !== 'loading' && !('error' in entry) ? entry.unit : ''
  const derived = entry && entry !== 'loading' && !('error' in entry) ? entry.derived_from : null

  return (
    <div className="grid gap-2">
      <div className="flex items-baseline justify-between">
        <span className="emap-detail__item-heading">{label}</span>
        <span className="font-mono text-[10px]" style={{ color: 'var(--overlay-40)' }}>
          {unit}
        </span>
      </div>
      {entry === 'loading' && <Placeholder height={height}>loading…</Placeholder>}
      {entry && entry !== 'loading' && 'error' in entry && <Placeholder height={height}>unavailable: {entry.error}</Placeholder>}
      {data.length === 0 && entry && entry !== 'loading' && !('error' in entry) && <Placeholder height={height}>no data in range</Placeholder>}
      {data.length > 0 && (
        <ChartContainer config={config} className="w-full" style={{ height }}>
          <AreaChart data={data} margin={{ left: 0, right: 8, top: 4, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--global-border)" />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={['dataMin', 'dataMax']}
              ticks={ticks}
              tickFormatter={(t: number) => tickLabel(t, range)}
              tickLine={false}
              axisLine={false}
              fontSize={10}
            />
            <YAxis width={44} tickLine={false} axisLine={false} fontSize={10} tickFormatter={(v: number) => v.toLocaleString('en-US', { maximumFractionDigits: 0 })} />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  labelFormatter={(_: unknown, payload: readonly { payload?: unknown }[]) => {
                    const t = (payload?.[0]?.payload as { t?: number } | undefined)?.t
                    return t ? new Date(t).toISOString().slice(0, 16).replace('T', ' ') + 'Z' : ''
                  }}
                />
              }
            />
            <Area dataKey="v" type="monotone" stroke="var(--color-v)" fill="var(--color-v)" fillOpacity={0.15} strokeWidth={1.5} isAnimationActive={false} dot={false} />
          </AreaChart>
        </ChartContainer>
      )}
      {derived && (
        <p className="text-[10px] leading-tight" style={{ color: 'var(--overlay-40)' }}>
          derived: {derived}
        </p>
      )}
    </div>
  )
}

function Placeholder({ children, height }: { children: React.ReactNode; height: number }) {
  return (
    <div className="flex items-center justify-center rounded border border-dashed text-[11px]" style={{ height, color: 'var(--overlay-40)', borderColor: 'var(--global-border)' }}>
      {children}
    </div>
  )
}
