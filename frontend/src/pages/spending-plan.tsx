import { useDeferredValue, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { accounts as accountsApi, spendingPlan as spendingPlanApi } from '@/lib/api'
import { getAccountName, sortAccountsByDisplayName } from '@/lib/account-utils'
import { extractApiError } from '@/lib/api-errors'
import { formatCompactCurrency, formatCurrency } from '@/lib/format'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { coverageLabel, formatPlanDate } from '@/lib/spending-plan'
import { usePrivacyMode } from '@/hooks/use-privacy-mode'
import { useDateLocale, useDisplayLocale } from '@/hooks/use-display-locale'
import { cn } from '@/lib/utils'
import type { SpendingPlan, SpendingPlanInput } from '@/types'

const SELECT_CLASS = 'w-full border border-border rounded-lg px-3 py-2 text-sm bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary'
const HORIZONS = [6, 12, 18, 24, 36]

function draftFrom(plan: SpendingPlan | null): SpendingPlanInput {
  return {
    daily_allowance: plan ? Number(plan.daily_allowance) : 0,
    balance_floor: plan ? Number(plan.balance_floor) : 0,
    account_ids: plan?.account_ids ?? null,
    horizon_months: plan?.horizon_months ?? 12,
  }
}

function parseAmount(value: string) {
  const parsed = Number(value.replace(',', '.'))
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0
}

export default function SpendingPlanPage() {
  const { data: plan, isLoading } = useQuery({
    queryKey: ['spending-plan'],
    queryFn: spendingPlanApi.get,
  })
  if (isLoading) return <Skeleton className="h-64 w-full" />
  // Keyed on the saved plan so a save or removal starts the form from the
  // stored values instead of syncing them into state after the fact.
  return <SpendingPlanEditor key={JSON.stringify(plan ?? null)} plan={plan ?? null} />
}

function SpendingPlanEditor({ plan }: { plan: SpendingPlan | null }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { mask } = usePrivacyMode()
  const locale = useDisplayLocale()
  const dateLocale = useDateLocale()

  const { data: accountsList } = useQuery({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })

  const [draft, setDraft] = useState<SpendingPlanInput>(() => draftFrom(plan))
  const [allowanceText, setAllowanceText] = useState(() => (plan ? String(Number(plan.daily_allowance)) : ''))
  const [floorText, setFloorText] = useState(() => (plan && Number(plan.balance_floor) ? String(Number(plan.balance_floor)) : ''))

  // The chart previews the allowance being typed, before it is saved.
  const previewAllowance = useDeferredValue(draft.daily_allowance)
  const { data: timeline, isLoading: timelineLoading } = useQuery({
    queryKey: ['dashboard', 'spending-plan', 'timeline', previewAllowance],
    queryFn: () => spendingPlanApi.timeline(previewAllowance),
    placeholderData: (previous) => previous,
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['spending-plan'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard', 'spending-plan'] })
    queryClient.invalidateQueries({ queryKey: ['transactions', 'calendar'] })
  }
  const save = useMutation({
    mutationFn: () => spendingPlanApi.save(draft),
    onSuccess: () => {
      invalidate()
      toast.success(t('spendingPlan.saved'))
    },
    onError: (error) => toast.error(extractApiError(error)),
  })
  const remove = useMutation({
    mutationFn: spendingPlanApi.remove,
    onSuccess: () => {
      invalidate()
      toast.success(t('spendingPlan.removed'))
    },
    onError: (error) => toast.error(extractApiError(error)),
  })

  const planAccounts = useMemo(
    () => sortAccountsByDisplayName((accountsList ?? []).filter((a) => !a.is_closed)),
    [accountsList],
  )
  const chosen = new Set(draft.account_ids ?? [])
  const toggleAccount = (id: string) => {
    const current = draft.account_ids ?? planAccounts.filter((a) => a.type !== 'loan').map((a) => a.id)
    const next = current.includes(id) ? current.filter((x) => x !== id) : [...current, id]
    setDraft((current) => ({ ...current, account_ids: next }))
  }

  const currency = timeline?.currency ?? 'BRL'
  const money = (value: number) => mask(formatCurrency(value, currency, locale))
  const chartData = timeline?.points ?? []
  const floor = timeline?.balance_floor ?? 0

  return (
    <div>
      <PageHeader
        section={t('nav.groupSetup')}
        title={t('spendingPlan.title')}
        action={plan ? (
          <Button variant="outline" size="sm" onClick={() => remove.mutate()} disabled={remove.isPending}>
            {t('spendingPlan.remove')}
          </Button>
        ) : undefined}
      />
      <p className="text-sm text-muted-foreground -mt-3 mb-6 max-w-2xl">{t('spendingPlan.intro')}</p>

      <div className="grid gap-3 sm:grid-cols-3 mb-6">
        <Stat
          label={t('spendingPlan.todayLabel')}
          loading={!timeline}
          value={timeline ? money(timeline.today.remaining) : ''}
          caption={timeline ? t('spendingPlan.todayCaption', {
            spent: money(timeline.today.spent),
            allowance: money(timeline.today.allowance),
          }) : ''}
          tone={timeline && timeline.today.remaining < 0 ? 'bad' : 'neutral'}
        />
        <Stat
          label={t('spendingPlan.safeLabel')}
          loading={!timeline}
          value={timeline ? money(timeline.safe_daily_allowance) : ''}
          caption={timeline ? t('spendingPlan.safeCaption', {
            date: formatPlanDate(timeline.horizon_end, dateLocale),
          }) : ''}
        />
        <Stat
          label={t('spendingPlan.coverageLabel')}
          loading={!timeline}
          value={timeline ? coverageLabel(timeline, dateLocale, t) : ''}
          caption={timeline ? t('spendingPlan.coverageCaption', { floor: money(floor) }) : ''}
          tone={timeline ? (timeline.covered_until === null ? 'bad' : 'good') : 'neutral'}
        />
      </div>

      <div className="bg-card rounded-xl border border-border shadow-sm p-4 mb-6">
        <p className="text-sm font-semibold text-foreground mb-3">{t('spendingPlan.chartTitle')}</p>
        <div className="h-64">
          {timelineLoading && !timeline ? (
            <Skeleton className="h-full w-full" />
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="planBalanceFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10B981" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#10B981" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} className="stroke-border" />
                <XAxis
                  dataKey="date"
                  tickFormatter={(value: string) => new Date(`${value}T00:00:00`).toLocaleDateString(dateLocale, { month: 'short', year: '2-digit' })}
                  minTickGap={40}
                  tick={{ fontSize: 11 }}
                />
                <YAxis
                  tickFormatter={(value: number) => mask(formatCompactCurrency(value, currency, locale))}
                  width={64}
                  tick={{ fontSize: 11 }}
                />
                <Tooltip
                  formatter={(value) => money(Number(value))}
                  labelFormatter={(label) => formatPlanDate(String(label), dateLocale)}
                />
                <ReferenceLine y={floor} stroke="#F43F5E" strokeDasharray="4 4" />
                {timeline?.covered_until && !timeline.covered_through_horizon && (
                  <ReferenceLine x={timeline.covered_until} stroke="#F43F5E" />
                )}
                <Area
                  type="monotone"
                  dataKey="balance"
                  name={t('spendingPlan.balance')}
                  stroke="#10B981"
                  fill="url(#planBalanceFill)"
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <form
        className="bg-card rounded-xl border border-border shadow-sm p-4 space-y-4 max-w-2xl"
        onSubmit={(event) => {
          event.preventDefault()
          save.mutate()
        }}
      >
        <p className="text-sm font-semibold text-foreground">{t('spendingPlan.settings')}</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="plan-allowance">{t('spendingPlan.dailyAllowance')}</Label>
            <Input
              id="plan-allowance"
              inputMode="decimal"
              value={allowanceText}
              onChange={(event) => {
                setAllowanceText(event.target.value)
                setDraft((current) => ({ ...current, daily_allowance: parseAmount(event.target.value) }))
              }}
              placeholder="0"
            />
            {timeline && timeline.safe_daily_allowance !== draft.daily_allowance && (
              <button
                type="button"
                className="text-xs text-primary hover:underline"
                onClick={() => {
                  const safe = timeline.safe_daily_allowance
                  setAllowanceText(String(safe))
                  setDraft((current) => ({ ...current, daily_allowance: safe }))
                }}
              >
                {t('spendingPlan.useSafe', { amount: money(timeline.safe_daily_allowance) })}
              </button>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="plan-floor">{t('spendingPlan.balanceFloor')}</Label>
            <Input
              id="plan-floor"
              inputMode="decimal"
              value={floorText}
              onChange={(event) => {
                setFloorText(event.target.value)
                setDraft((current) => ({ ...current, balance_floor: parseAmount(event.target.value) }))
              }}
              placeholder="0"
            />
            <p className="text-xs text-muted-foreground">{t('spendingPlan.balanceFloorHint')}</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="plan-horizon">{t('spendingPlan.horizon')}</Label>
            <select
              id="plan-horizon"
              className={SELECT_CLASS}
              value={draft.horizon_months}
              onChange={(event) => setDraft((current) => ({ ...current, horizon_months: Number(event.target.value) }))}
            >
              {HORIZONS.map((months) => (
                <option key={months} value={months}>{t('spendingPlan.months', { count: months })}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label>{t('spendingPlan.accounts')}</Label>
          <p className="text-xs text-muted-foreground">{t('spendingPlan.accountsHint')}</p>
          <div className="flex flex-wrap gap-2">
            {planAccounts.map((account) => {
              const selected = draft.account_ids === null ? account.type !== 'loan' : chosen.has(account.id)
              return (
                <button
                  key={account.id}
                  type="button"
                  onClick={() => toggleAccount(account.id)}
                  aria-pressed={selected}
                  className={cn(
                    'rounded-full border px-3 py-1 text-xs transition-colors',
                    selected
                      ? 'border-primary bg-primary/10 text-foreground'
                      : 'border-border text-muted-foreground hover:bg-muted/40',
                  )}
                >
                  {getAccountName(account)}
                </button>
              )
            })}
          </div>
        </div>

        <p className="text-xs text-muted-foreground">{t('spendingPlan.previewHint')}</p>
        <div className="flex gap-2">
          <Button type="submit" disabled={save.isPending}>{t('spendingPlan.save')}</Button>
        </div>
      </form>
    </div>
  )
}

function Stat({
  label,
  value,
  caption,
  loading,
  tone = 'neutral',
}: {
  label: string
  value: string
  caption: string
  loading: boolean
  tone?: 'good' | 'bad' | 'neutral'
}) {
  return (
    <div className="bg-card rounded-xl border border-border shadow-sm p-4">
      <p className="text-xs font-medium text-muted-foreground mb-1">{label}</p>
      {loading ? (
        <Skeleton className="h-6 w-28" />
      ) : (
        <>
          <p className={cn(
            'text-lg font-bold tabular-nums',
            tone === 'good' && 'text-emerald-600 dark:text-emerald-400',
            tone === 'bad' && 'text-rose-500',
            tone === 'neutral' && 'text-foreground',
          )}
          >
            {value}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">{caption}</p>
        </>
      )}
    </div>
  )
}
