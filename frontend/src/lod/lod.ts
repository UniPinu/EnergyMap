/**
 * Level-of-detail engine (MVP.md §4.2) — pure functions.
 *
 *   ℓ*(z) = max{ ℓ : z ≥ z_ℓ }                      zoom selects a base level
 *   Rendered(z, vp) = { c ∈ Π_ℓ* : bbox(c) ∩ vp ≠ ∅ }   viewport intersection
 *   decrement ℓ* until |Rendered| ≤ N_max            hard DOM budget
 *
 * Everything outside Rendered is left unmounted (React Flow `onlyRenderVisibleElements`), and
 * the level swap replaces the node/edge arrays wholesale. One constant world for every level,
 * so switching levels never moves the viewport.
 */

export interface Rect {
  x: number
  y: number
  width: number
  height: number
}

/** Zoom thresholds z_0 < z_1 < z_2 for Π₀, Π₁, Π₂ (world ≈ 36k px; fitView ≈ 0.03; fitting one
 * DK zone on a laptop-width pane ≈ 0.29, which must already be the entity level). */
export const LEVEL_ZOOM: readonly number[] = [0, 0.08, 0.28]

/** Hard render budget: mounted nodes (MVP.md §4.2 target 300–500). */
export const N_MAX = 400

/** Relative band around a threshold inside which the current level is kept (no flapping). */
export const HYSTERESIS = 0.12

export function levelForZoom(zoom: number, thresholds: readonly number[] = LEVEL_ZOOM): number {
  let level = 0
  for (let l = 0; l < thresholds.length; l++) if (zoom >= thresholds[l]!) level = l
  return level
}

/**
 * Like `levelForZoom`, but keeps `current` while the zoom sits within ±HYSTERESIS of the
 * threshold separating it from the naive choice.
 */
export function levelForZoomWithHysteresis(
  zoom: number,
  current: number | null,
  thresholds: readonly number[] = LEVEL_ZOOM,
  band = HYSTERESIS,
): number {
  const naive = levelForZoom(zoom, thresholds)
  if (current == null || naive === current) return naive
  // threshold between current and naive
  const t = thresholds[Math.max(current, naive)]!
  if (Math.abs(zoom - t) <= t * band) return current
  return naive
}

/** Viewport in flow coordinates from React Flow's transform [tx, ty, zoom] and pane size. */
export function viewportRect(tx: number, ty: number, zoom: number, width: number, height: number): Rect {
  return { x: -tx / zoom, y: -ty / zoom, width: width / zoom, height: height / zoom }
}

export function intersects(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y
}

export function countVisible(boxes: readonly Rect[], vp: Rect): number {
  let n = 0
  for (const b of boxes) if (intersects(b, vp)) n++
  return n
}

/**
 * Final level: start at the zoom-selected level (with hysteresis) and demote while the
 * viewport would mount more than `nMax` nodes. Π₀ is always allowed.
 */
export function selectLevel(
  zoom: number,
  vp: Rect,
  boxesByLevel: readonly (readonly Rect[])[],
  current: number | null,
  nMax = N_MAX,
  thresholds: readonly number[] = LEVEL_ZOOM,
): { level: number; visible: number; demoted: boolean } {
  let level = Math.min(levelForZoomWithHysteresis(zoom, current, thresholds), boxesByLevel.length - 1)
  let visible = countVisible(boxesByLevel[level]!, vp)
  let demoted = false
  while (level > 0 && visible > nMax) {
    level -= 1
    visible = countVisible(boxesByLevel[level]!, vp)
    demoted = true
  }
  return { level, visible, demoted }
}
