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

type Point = SpendingPlanTimeline['points'][number]

/** The projected balance at the end of ``date``: the last point on or before it. */
export function balanceOn(points: Point[], date: string): number | null {
  let found: number | null = null
  for (const point of points) {
    if (point.date > date) break
    found = point.balance
  }
  return found
}

export function lowestBalance(points: Point[]): number | null {
  return points.length === 0 ? null : Math.min(...points.map((point) => point.balance))
}

/**
 * The date "how much do you save until" starts on: this year's 31 December,
 * or next year's once this one is less than a month away, never past the
 * horizon.
 */
export function defaultSavingsDate(today: string, horizonEnd: string): string {
  const year = Number(today.slice(0, 4))
  const thisYear = `${year}-12-31`
  const daysLeft = (Date.parse(thisYear) - Date.parse(today)) / 86_400_000
  const target = daysLeft < 30 ? `${year + 1}-12-31` : thisYear
  return target > horizonEnd ? horizonEnd : target
}
