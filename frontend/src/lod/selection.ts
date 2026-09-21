import type { Topology } from '@/lib/api'

/**
 * Keep the selection meaningful across a level switch: a finest-level entity maps to its
 * cluster at a coarser level; a cluster maps to a neighbour zone's hub (level-invariant) or is
 * dropped when descending into DK detail.
 */
export function remapSelection(topology: Topology, selectedId: string | null, level: number): string | null {
  if (!selectedId) return null
  const finest = topology.meta.finest_level
  const node = topology.nodes.find((n) => n.id === selectedId)
  if (node) return level >= finest ? node.id : (node.cluster?.[String(level)] ?? null)
  // a cluster id from some coarser level
  for (const view of Object.values(topology.views)) {
    const c = view.nodes.find((x) => x.id === selectedId)
    if (!c) continue
    if (level === c.level) return c.id
    const member = topology.nodes.find((n) => n.id === c.members[0])
    if (!member) return null
    if (level >= finest) return member.zone.startsWith('DK') ? null : `hub:${member.zone}`
    return member.cluster?.[String(level)] ?? null
  }
  return null
}
