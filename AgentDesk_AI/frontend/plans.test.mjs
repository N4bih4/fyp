import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';
import vm from 'node:vm';

const compiled = ts.transpileModule(readFileSync(new URL('./src/plans.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const sandbox = { exports: {} };
vm.runInNewContext(compiled, sandbox);
const P = sandbox.exports;
const NOW = new Date(2026, 10, 27, 15, 0, 0);     // 27 Nov 2026

test('prices and totals match the plan sheet', () => {
  assert.equal(P.BASE_PLANS.find((p) => p.id === 'free').price, 0);
  assert.equal(P.BASE_PLANS.find((p) => p.id === 'free').commands, 100);
  assert.equal(P.BASE_PLANS.find((p) => p.id === 'premium').price, 999);
  assert.equal(P.BASE_PLANS.find((p) => p.id === 'premium').commands, 1000);
  assert.equal(JSON.stringify(P.ADDONS.map((a) => [a.name, a.price])), JSON.stringify([['File Management', 399], ['Browser Automation', 699], ['Office Productivity', 999]]));
  assert.equal(P.monthlyTotal('free', []), 0);
  assert.equal(P.monthlyTotal('premium', []), 999);
  assert.equal(P.monthlyTotal('premium', ['files', 'browser']), 999 + 399 + 699);
  assert.equal(P.monthlyTotal('free', ['office', 'nope']), 999);
  assert.equal(P.formatRs(0), 'Rs. 0');
  assert.equal(P.formatRs(1497), 'Rs. 1,497');
});

test('plan label says which plan is running', () => {
  assert.equal(P.planLabel({ base: 'free', addons: [] }), 'Free Plan');
  assert.equal(P.planLabel({ base: 'premium', addons: [] }), 'Premium Plan');
  assert.equal(P.planLabel({ base: 'premium', addons: ['files'] }), 'Premium Plan + 1 add-on');
  assert.equal(P.planLabel({ base: 'free', addons: ['files', 'office'] }), 'Free Plan + 2 add-ons');
});

test('card number must have exactly the right number of digits', () => {
  const n = P.CARD_DIGITS;
  assert.equal(P.validateCardNumber('4'.repeat(n)), null);
  assert.equal(P.validateCardNumber('4242 4242 4242 4242'), null);
  assert.match(P.validateCardNumber('4'.repeat(n - 1)), /must be 16 digits/);
  assert.match(P.validateCardNumber('4'.repeat(n + 1)), /must be 16 digits/);
  assert.match(P.validateCardNumber(''), /Enter your card number/);
  assert.match(P.validateCardNumber('4242 4242 4242 42ab'), /digits/);
  assert.equal(P.formatCardNumber('4242424242424242'), '4242 4242 4242 4242');
  assert.equal(P.formatCardNumber('42424242424242429999'), '4242 4242 4242 4242');      // typing past the length is cut
});

test('cvc is exactly three digits', () => {
  assert.equal(P.validateCvc('123'), null);
  assert.match(P.validateCvc('12'), /must be 3 digits/);
  assert.match(P.validateCvc('1234'), /must be 3 digits/);
  assert.match(P.validateCvc(''), /Enter the CVC/);
  assert.match(P.validateCvc('12a'), /only contain digits/);
});

test('expiry must still be valid: a past month is refused, this month and later are fine', () => {
  assert.equal(P.validateExpiry('12/26', NOW), null);          // the end of next month
  assert.equal(P.validateExpiry('11/26', NOW), null);          // this month: good until its last day
  assert.match(P.validateExpiry('10/26', NOW), /has expired/); // last month
  assert.match(P.validateExpiry('01/20', NOW), /has expired/);
  assert.equal(P.validateExpiry('01/30', NOW), null);
  assert.match(P.validateExpiry('13/30', NOW), /between 01 and 12/);
  assert.match(P.validateExpiry('00/30', NOW), /between 01 and 12/);
  assert.match(P.validateExpiry('1230', NOW), /MM\/YY/);
  assert.match(P.validateExpiry('', NOW), /Enter the expiry date/);
  assert.equal(P.validateExpiry('12/26', new Date(2027, 0, 1)) === null, false);           // January 2027: Dec 2026 is over
  assert.equal(P.formatExpiry('1228'), '12/28');
  assert.equal(P.formatExpiry('12'), '12');
});

test('a card is accepted only when all three fields are right', () => {
  assert.equal(P.cardIsValid(P.validateCard('4242424242424242', '08/29', '123', NOW)), true);
  assert.equal(P.cardIsValid(P.validateCard('424242424242424', '08/29', '123', NOW)), false);
  assert.equal(P.cardIsValid(P.validateCard('4242424242424242', '08/24', '123', NOW)), false);
  assert.equal(P.cardIsValid(P.validateCard('4242424242424242', '08/29', '12', NOW)), false);
});

test('only the plan and the last four digits are remembered', () => {
  const store = {};
  sandbox.window = { localStorage: { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } } };
  P.saveSubscription({ base: 'premium', addons: ['files'], last4: '4242', since: '2026-11-27' });
  const raw = Object.values(store)[0];
  assert.ok(!/4242424242424242/.test(raw));
  assert.equal(JSON.stringify(P.loadSubscription()), JSON.stringify({ base: 'premium', addons: ['files'], last4: '4242', since: '2026-11-27' }));
  store[Object.keys(store)[0]] = '{not json';
  assert.equal(JSON.stringify(P.loadSubscription()), JSON.stringify({ base: 'free', addons: [] }));
});
