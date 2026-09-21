/**
 * Web-Mercator projection helper — the ONE spatial reference shared by the
 * geographic layer (shadcn-maps SVG) and the balance-graph layer (React Flow).
 * MVP.md §8 / CONTEXT.md §3: node `position` = projection of `(lat, lon)`;
 * keep a single helper so both layers agree spatially.
 *
 * Conventions
 *  - `mercatorUnit` maps the globe onto the unit square [0,1]² with x east
 *    and y DOWN (north = 0), i.e. the slippy-map convention at zoom 0 / 1px.
 *  - `fitBounds` builds a concrete pixel projection for a lat/lon bounding box
 *    inside a pixel box (aspect-preserving, centred, optional padding).
 *  - Latitudes are clamped to ±MAX_LAT (the Mercator singularity).
 */

export interface LngLat {
  lon: number
  lat: number
}

export interface Point {
  x: number
  y: number
}

export interface Bounds {
  west: number
  south: number
  east: number
  north: number
}

export interface Size {
  width: number
  height: number
}

/** Latitude where Web Mercator's square world ends (85.05112878°). */
export const MAX_LAT = (2 * Math.atan(Math.exp(Math.PI)) - Math.PI / 2) * (180 / Math.PI)

const DEG = Math.PI / 180

function clampLat(lat: number): number {
  return Math.max(-MAX_LAT, Math.min(MAX_LAT, lat))
}

/** Globe → unit square. x ∈ [0,1] west→east, y ∈ [0,1] north→south. */
export function mercatorUnit({ lon, lat }: LngLat): Point {
  const φ = clampLat(lat) * DEG
  const x = (lon + 180) / 360
  const y = (1 - Math.log(Math.tan(φ) + 1 / Math.cos(φ)) / Math.PI) / 2
  return { x, y }
}

/** Unit square → globe (inverse of `mercatorUnit`). */
export function mercatorUnitInverse({ x, y }: Point): LngLat {
  const lon = x * 360 - 180
  const lat = Math.atan(Math.sinh(Math.PI * (1 - 2 * y))) / DEG
  return { lon, lat }
}

/** A concrete pixel projection: unit square scaled and translated into a pixel box. */
export interface Projection {
  /** Pixels per unit-square side. */
  readonly scale: number
  /** Pixel offset applied after scaling. */
  readonly translate: Point
  project(ll: LngLat): Point
  unproject(p: Point): LngLat
}

export function makeProjection(scale: number, translate: Point): Projection {
  if (!(scale > 0) || !Number.isFinite(scale)) throw new RangeError(`scale must be > 0, got ${scale}`)
  return {
    scale,
    translate,
    project(ll) {
      const u = mercatorUnit(ll)
      return { x: u.x * scale + translate.x, y: u.y * scale + translate.y }
    },
    unproject(p) {
      return mercatorUnitInverse({ x: (p.x - translate.x) / scale, y: (p.y - translate.y) / scale })
    },
  }
}

/**
 * Projection that fits `bounds` inside `size` (minus `padding` on every side),
 * preserving aspect ratio and centring the slack on the non-limiting axis.
 */
export function fitBounds(bounds: Bounds, size: Size, padding = 0): Projection {
  if (!(bounds.east > bounds.west)) throw new RangeError('bounds.east must exceed bounds.west')
  if (!(bounds.north > bounds.south)) throw new RangeError('bounds.north must exceed bounds.south')
  const innerW = size.width - 2 * padding
  const innerH = size.height - 2 * padding
  if (!(innerW > 0) || !(innerH > 0)) throw new RangeError('size minus padding must be positive')

  const nw = mercatorUnit({ lon: bounds.west, lat: bounds.north })
  const se = mercatorUnit({ lon: bounds.east, lat: bounds.south })
  const uw = se.x - nw.x
  const uh = se.y - nw.y
  const scale = Math.min(innerW / uw, innerH / uh)

  // centre the projected bbox inside the inner box
  const boxW = uw * scale
  const boxH = uh * scale
  const translate = {
    x: padding + (innerW - boxW) / 2 - nw.x * scale,
    y: padding + (innerH - boxH) / 2 - nw.y * scale,
  }
  return makeProjection(scale, translate)
}

/**
 * Default region frame: Northern Europe as scoped in MVP.md §2.3
 * (DK-centric; DE, NO, SE, NL, PL, FI, Baltics as context).
 */
export const NORTHERN_EUROPE_BOUNDS: Bounds = { west: 3, south: 49, east: 31, north: 71 }
