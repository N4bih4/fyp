// Subscription plans and the card-form rules. No imports on purpose: the node tests load this file on its own.

export interface Plan {
  id: string;
  name: string;
  price: number;            // Rs per month (0 = free)
  commands?: number;        // commands per month
  blurb: string;
}

export const BASE_PLANS: Plan[] = [
  { id: 'free', name: 'Free Plan', price: 0, commands: 100, blurb: '100 commands every month' },
  { id: 'premium', name: 'Premium Plan', price: 999, commands: 1000, blurb: '1,000 commands every month' },
];

export const ADDONS: Plan[] = [
  { id: 'files', name: 'File Management', price: 399, blurb: 'Create, copy, move, rename and organise files and folders' },
  { id: 'browser', name: 'Browser Automation', price: 699, blurb: 'Control tabs, search, YouTube and websites' },
  { id: 'office', name: 'Office Productivity', price: 999, blurb: 'Word, Excel and PowerPoint documents' },
];

export const CUSTOM_SETUP = { name: 'Custom Automation Setup', price: 'Rs. 5,000 – 15,000+ per project', blurb: 'Built for you once; priced per project' };

export interface Subscription {
  base: string;             // 'free' | 'premium'
  addons: string[];
  last4?: string;           // the only card detail that is ever kept
  since?: string;           // ISO date
}

export const FREE_SUBSCRIPTION: Subscription = { base: 'free', addons: [] };

/** Card numbers must have exactly this many digits (change here if a different length is wanted). */
export const CARD_DIGITS = 16;
export const CVC_DIGITS = 3;

export function formatRs(amount: number): string {
  return amount === 0 ? 'Rs. 0' : `Rs. ${amount.toLocaleString('en-US')}`;
}

export function monthlyTotal(base: string, addons: string[]): number {
  const basePrice = BASE_PLANS.find((p) => p.id === base)?.price ?? 0;
  const extra = ADDONS.filter((a) => addons.includes(a.id)).reduce((sum, a) => sum + a.price, 0);
  return basePrice + extra;
}

export function planLabel(sub: Subscription): string {
  const base = BASE_PLANS.find((p) => p.id === sub.base) ?? BASE_PLANS[0];
  const n = sub.addons.filter((id) => ADDONS.some((a) => a.id === id)).length;
  return n ? `${base.name} + ${n} add-on${n > 1 ? 's' : ''}` : base.name;
}

export function sameSelection(sub: Subscription, base: string, addons: string[]): boolean {
  return sub.base === base && sub.addons.length === addons.length && sub.addons.every((id) => addons.includes(id));
}

// ---------------------------------------------------------------------------------------------------- card form
export function digitsOnly(value: string): string {
  return value.replace(/\D/g, '');
}

/** "4242424242424242" -> "4242 4242 4242 4242" while typing. */
export function formatCardNumber(value: string): string {
  return digitsOnly(value).slice(0, CARD_DIGITS).replace(/(\d{4})(?=\d)/g, '$1 ');
}

/** "1228" / "12/28" -> "12/28" while typing. */
export function formatExpiry(value: string): string {
  const d = digitsOnly(value).slice(0, 4);
  return d.length > 2 ? `${d.slice(0, 2)}/${d.slice(2)}` : d;
}

export function validateCardNumber(value: string): string | null {
  const d = digitsOnly(value);
  if (!d) return 'Enter your card number.';
  if (/[^\d\s]/.test(value)) return 'The card number can only contain digits.';
  if (d.length !== CARD_DIGITS) return `The card number must be ${CARD_DIGITS} digits (you entered ${d.length}).`;
  return null;
}

/** MM/YY. A card is good until the END of its expiry month, so the month must not be over yet. */
export function validateExpiry(value: string, now: Date = new Date()): string | null {
  const text = value.trim();
  if (!text) return 'Enter the expiry date (MM/YY).';
  const m = /^(\d{2})\s*\/\s*(\d{2})$/.exec(text);
  if (!m) return 'Enter the expiry as MM/YY, for example 08/29.';
  const month = Number(m[1]);
  const year = 2000 + Number(m[2]);
  if (month < 1 || month > 12) return 'The expiry month must be between 01 and 12.';
  const endOfMonth = new Date(year, month, 0, 23, 59, 59, 999);       // day 0 of the next month = the last day of this one
  if (endOfMonth.getTime() < now.getTime()) return 'Your card has expired. Please use a card that is still valid.';
  return null;
}

export function validateCvc(value: string): string | null {
  const d = digitsOnly(value);
  if (!d) return 'Enter the CVC.';
  if (/[^\d]/.test(value.trim())) return 'The CVC can only contain digits.';
  if (d.length !== CVC_DIGITS) return `The CVC must be ${CVC_DIGITS} digits (you entered ${d.length}).`;
  return null;
}

export interface CardErrors { number: string | null; expiry: string | null; cvc: string | null }

export function validateCard(number: string, expiry: string, cvc: string, now: Date = new Date()): CardErrors {
  return { number: validateCardNumber(number), expiry: validateExpiry(expiry, now), cvc: validateCvc(cvc) };
}

export function cardIsValid(errors: CardErrors): boolean {
  return !errors.number && !errors.expiry && !errors.cvc;
}

// ---------------------------------------------------------------------------------------------------- storage
const KEY = 'agentdesk.subscription';

export function loadSubscription(): Subscription {
  try {
    const raw = JSON.parse(window.localStorage.getItem(KEY) || 'null');
    if (raw && BASE_PLANS.some((p) => p.id === raw.base) && Array.isArray(raw.addons)) {
      return { base: raw.base, addons: raw.addons.filter((id: unknown) => ADDONS.some((a) => a.id === id)), last4: typeof raw.last4 === 'string' ? raw.last4.slice(-4) : undefined, since: raw.since };
    }
  } catch { /* storage can be blocked or hold junk: start on the free plan */ }
  return FREE_SUBSCRIPTION;
}

export function saveSubscription(sub: Subscription): void {
  try { window.localStorage.setItem(KEY, JSON.stringify(sub)); } catch { /* private mode: the plan just is not remembered */ }
}
