import type { SpendingPlanTimeline } from '@/types'

export function formatPlanDate(value: string, dateLocale: string) {
  return new Date(`${value}T00:00:00`).toLocaleDateString(dateLocale, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

/** "Covered until 18 Dec 2027", "covered through the horizon" or "not covered". */
export function coverageLabel(
  timeline: SpendingPlanTimeline,
  dateLocale: string,
  t: (key: string, options?: Record<string, unknown>) => string,
) {
  if (timeline.covered_until === null) return t('spendingPlan.notCovered')
  const date = formatPlanDate(timeline.covered_until, dateLocale)
  return timeline.covered_through_horizon
    ? t('spendingPlan.coveredThrough', { date })
    : t('spendingPlan.coveredUntil', { date })
}
