import { describe, expect, it } from 'vitest'
import { balanceOn, defaultSavingsDate, lowestBalance } from './spending-plan'

const points = [
  { date: '2026-11-12', balance: 1000 },
  { date: '2026-11-13', balance: 900 },
  { date: '2026-11-15', balance: 1200 },
]

describe('balanceOn', () => {
  it('reads the last point on or before the date', () => {
    expect(balanceOn(points, '2026-11-13')).toBe(900)
    expect(balanceOn(points, '2026-11-14')).toBe(900)
    expect(balanceOn(points, '2027-01-01')).toBe(1200)
  })

  it('has no balance before the first point', () => {
    expect(balanceOn(points, '2026-11-01')).toBeNull()
  })
})

describe('lowestBalance', () => {
  it('finds the lowest point', () => {
    expect(lowestBalance(points)).toBe(900)
    expect(lowestBalance([])).toBeNull()
  })
})

describe('defaultSavingsDate', () => {
  it('uses this December while it is more than a month away', () => {
    expect(defaultSavingsDate('2026-06-10', '2027-06-10')).toBe('2026-12-31')
  })

  it('moves to next December once this one is close', () => {
    expect(defaultSavingsDate('2026-12-10', '2028-01-10')).toBe('2027-12-31')
  })

  it('never passes the horizon', () => {
    expect(defaultSavingsDate('2026-12-10', '2027-06-10')).toBe('2027-06-10')
  })
})
