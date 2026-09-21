/**
 * Typed client for service B — the only network surface the frontend uses.
 * Types come from `api-types.d.ts`, generated from the backend's OpenAPI doc
 * (`npm run gen:api`), so request/response shapes cannot drift from pydantic.
 */
import createClient from 'openapi-fetch'
import type { components, paths } from './api-types'

export type Sample = components['schemas']['Sample']
export type Health = components['schemas']['Health']
export type Quantity = Sample['quantity']

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

export const api = createClient<paths>({ baseUrl: API_BASE })

export type Topology = components['schemas']['Topology']
export type TopoNode = components['schemas']['Node']
export type TopoEdge = components['schemas']['Edge']
export type ClusterNode = components['schemas']['ClusterNode']
export type BundledEdge = components['schemas']['BundledEdge']
export type NodeKind = TopoNode['kind']
export type EdgeKind = TopoEdge['kind']
