import { useEffect, useState, type FormEvent } from 'react';
import {
  ADDONS, BASE_PLANS, CARD_DIGITS, CUSTOM_SETUP, CVC_DIGITS, cardIsValid, digitsOnly, formatCardNumber, formatExpiry, formatRs,
  monthlyTotal, planLabel, sameSelection, validateCard, type CardErrors, type Subscription,
} from '../plans';
import { useFocusTrap } from './useFocusTrap';

/** The plan the user is on, pinned to the bottom-left corner (next to the side menu). Clicking it opens the plans. */
export function PlanBadge({ subscription, onOpen }: { subscription: Subscription; onOpen: () => void }) {
  const paid = subscription.base !== 'free' || subscription.addons.length > 0;
  return (
    <button
      type="button"
      onClick={onOpen}
      data-testid="plan-badge"
      title="See all plans and upgrade"
      className="fixed bottom-20 left-4 z-20 flex items-center gap-2 rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-semibold shadow-lg md:bottom-4 md:left-[100px]"
    >
      <span className={`h-2.5 w-2.5 rounded-full ${paid ? 'bg-emerald-500' : 'bg-amber-500'}`} aria-hidden="true" />
      <span className="text-slate-900">{planLabel(subscription)}</span>
      <span className="text-blue-700">{paid ? 'Manage' : 'Upgrade'}</span>
    </button>
  );
}

type Step = 'plans' | 'card' | 'done';

interface Props {
  subscription: Subscription;
  onClose: () => void;
  onSubscribe: (next: Subscription) => void;
}

export function PlansModal({ subscription, onClose, onSubscribe }: Props) {
  const [step, setStep] = useState<Step>('plans');
  const [base, setBase] = useState(subscription.base);
  const [addons, setAddons] = useState<string[]>(subscription.addons);
  const [number, setNumber] = useState('');
  const [expiry, setExpiry] = useState('');
  const [cvc, setCvc] = useState('');
  const [touched, setTouched] = useState(false);
  const ref = useFocusTrap<HTMLDivElement>(true, onClose);

  useEffect(() => { document.body.style.overflow = 'hidden'; return () => { document.body.style.overflow = ''; }; }, []);

  const total = monthlyTotal(base, addons);
  const unchanged = sameSelection(subscription, base, addons);
  const errors: CardErrors = validateCard(number, expiry, cvc);
  const show = (message: string | null) => (touched ? message : null);

  const toggleAddon = (id: string) => setAddons((current) => (current.includes(id) ? current.filter((a) => a !== id) : [...current, id]));

  function subscribe() {
    if (total === 0) {                                  // going back to the free plan needs no card
      onSubscribe({ base: 'free', addons: [] });
      setStep('done');
      return;
    }
    setStep('card');
  }

  function pay(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!cardIsValid(errors)) return;
    // Demo checkout: nothing is charged and the card is not sent or stored anywhere. Only the last four digits are kept, to show "Card ending 1234".
    onSubscribe({ base, addons, last4: digitsOnly(number).slice(-4), since: new Date().toISOString() });
    setNumber(''); setExpiry(''); setCvc('');
    setStep('done');
  }

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center overflow-y-auto bg-black/60 p-4 sm:items-center" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby="plans-title" className="my-4 w-full max-w-3xl rounded-2xl border border-slate-300 bg-white p-5 shadow-2xl sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 id="plans-title" className="text-xl font-bold text-slate-900">
              {step === 'plans' ? 'Plans & pricing' : step === 'card' ? 'Payment details' : 'Subscription updated'}
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              {step === 'plans' ? <>You are on <strong>{planLabel(subscription)}</strong>.</> : step === 'card' ? `${formatRs(total)} per month · ${planLabel({ base, addons })}` : ''}
            </p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="flex h-9 w-9 items-center justify-center rounded-md text-slate-600 ring-1 ring-inset ring-slate-300"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M3 3l10 10M13 3L3 13" /></svg></button>
        </div>

        {step === 'plans' && (
          <>
            <h3 className="mt-5 text-sm font-semibold uppercase tracking-wide text-slate-500">Choose your plan</h3>
            <div role="radiogroup" aria-label="Plan" className="mt-2 grid gap-3 sm:grid-cols-2">
              {BASE_PLANS.map((plan) => {
                const chosen = base === plan.id;
                return (
                  <button key={plan.id} type="button" role="radio" aria-checked={chosen} onClick={() => setBase(plan.id)} data-testid={`plan-${plan.id}`}
                    className={`rounded-xl border p-4 text-left ${chosen ? 'border-blue-700 ring-2 ring-blue-700' : 'border-slate-300'}`}>
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-slate-900">{plan.name}</span>
                      {subscription.base === plan.id && <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800">Current</span>}
                    </div>
                    <p className="mt-1 text-2xl font-bold text-slate-900">{formatRs(plan.price)}<span className="text-sm font-normal text-slate-600">/month</span></p>
                    <p className="mt-1 text-sm text-slate-600">{plan.blurb}</p>
                  </button>
                );
              })}
            </div>

            <h3 className="mt-5 text-sm font-semibold uppercase tracking-wide text-slate-500">Add-ons (per month)</h3>
            <div className="mt-2 grid gap-3 sm:grid-cols-3">
              {ADDONS.map((addon) => {
                const chosen = addons.includes(addon.id);
                return (
                  <button key={addon.id} type="button" role="checkbox" aria-checked={chosen} onClick={() => toggleAddon(addon.id)} data-testid={`addon-${addon.id}`}
                    className={`rounded-xl border p-4 text-left ${chosen ? 'border-blue-700 ring-2 ring-blue-700' : 'border-slate-300'}`}>
                    <span className="font-semibold text-slate-900">{addon.name}</span>
                    <p className="mt-1 text-xl font-bold text-slate-900">{formatRs(addon.price)}<span className="text-sm font-normal text-slate-600">/month</span></p>
                    <p className="mt-1 text-xs text-slate-600">{addon.blurb}</p>
                  </button>
                );
              })}
            </div>

            <div className="mt-3 rounded-xl border border-slate-300 bg-slate-50 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold text-slate-900">{CUSTOM_SETUP.name}</span>
                <span className="font-bold text-slate-900">{CUSTOM_SETUP.price}</span>
              </div>
              <p className="mt-1 text-xs text-slate-600">{CUSTOM_SETUP.blurb}. This one is a quote, not a subscription: contact the team to plan your project.</p>
            </div>

            <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-4">
              <p className="text-slate-900">Total: <strong className="text-xl" data-testid="plan-total">{formatRs(total)}</strong> <span className="text-sm text-slate-600">per month</span></p>
              <button type="button" onClick={subscribe} disabled={unchanged} data-testid="subscribe"
                className="rounded-lg bg-blue-700 px-5 py-2.5 font-semibold text-white disabled:opacity-50">
                {total === 0 ? 'Switch to Free' : 'Subscribe'}
              </button>
            </div>
            {unchanged && <p className="mt-2 text-right text-xs text-slate-500">This is your current plan. Pick another plan or add-ons to change it.</p>}
          </>
        )}

        {step === 'card' && (
          <form onSubmit={pay} noValidate autoComplete="off" className="mt-5 grid gap-4" data-testid="card-form">
            <label className="grid gap-1 text-sm font-medium text-slate-900">
              Card number
              <input data-autofocus inputMode="numeric" autoComplete="off" name="plan-field-1" data-lpignore="true" data-form-type="other" placeholder={'1234 '.repeat(CARD_DIGITS / 4).trim()} value={number}
                onChange={(e) => setNumber(formatCardNumber(e.target.value))} aria-invalid={Boolean(show(errors.number))} aria-describedby="err-number"
                className="rounded-lg border border-slate-300 px-3 py-2 font-mono text-base" />
              <span id="err-number" role="alert" className="min-h-[1.25rem] text-xs text-red-700">{show(errors.number)}</span>
            </label>
            <div className="grid grid-cols-2 gap-4">
              <label className="grid gap-1 text-sm font-medium text-slate-900">
                Expiry (MM/YY)
                <input inputMode="numeric" autoComplete="off" name="plan-field-2" data-lpignore="true" data-form-type="other" placeholder="MM/YY" value={expiry}
                  onChange={(e) => setExpiry(formatExpiry(e.target.value))} aria-invalid={Boolean(show(errors.expiry))} aria-describedby="err-expiry"
                  className="rounded-lg border border-slate-300 px-3 py-2 font-mono text-base" />
                <span id="err-expiry" role="alert" className="min-h-[1.25rem] text-xs text-red-700">{show(errors.expiry)}</span>
              </label>
              <label className="grid gap-1 text-sm font-medium text-slate-900">
                CVC
                <input inputMode="numeric" autoComplete="off" name="plan-field-3" data-lpignore="true" data-form-type="other" placeholder={'123'.slice(0, CVC_DIGITS)} value={cvc} maxLength={CVC_DIGITS}
                  onChange={(e) => setCvc(digitsOnly(e.target.value).slice(0, CVC_DIGITS))} aria-invalid={Boolean(show(errors.cvc))} aria-describedby="err-cvc"
                  className="rounded-lg border border-slate-300 px-3 py-2 font-mono text-base" />
                <span id="err-cvc" role="alert" className="min-h-[1.25rem] text-xs text-red-700">{show(errors.cvc)}</span>
              </label>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-4">
              <button type="button" onClick={() => setStep('plans')} className="rounded-lg px-4 py-2 text-sm font-medium ring-1 ring-inset ring-slate-300">Back</button>
              <button type="submit" data-testid="pay" className="rounded-lg bg-blue-700 px-5 py-2.5 font-semibold text-white">Pay {formatRs(total)}</button>
            </div>
          </form>
        )}

        {step === 'done' && (
          <div className="mt-5 text-center" data-testid="subscribed">
            <p className="text-lg font-semibold text-slate-900">You are on {planLabel({ base, addons })}.</p>
            <p className="mt-1 text-sm text-slate-600">{total === 0 ? 'No payment needed.' : `${formatRs(total)} per month${subscription.last4 ? ` · card ending ${subscription.last4}` : ''}.`}</p>
            <button type="button" onClick={onClose} className="mt-5 rounded-lg bg-blue-700 px-5 py-2.5 font-semibold text-white">Done</button>
          </div>
        )}
      </div>
    </div>
  );
}
