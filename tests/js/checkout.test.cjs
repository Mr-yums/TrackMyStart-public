// [Sol] Exécute les vrais modules du formulaire avec un SDK Square simulé.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const vm = require('node:vm');
const source = process.env.CHECKOUT_JS_DIR || resolve(__dirname, '../../yumnews/static/js');

async function harness() {
  const element = () => ({ value: '', disabled: false, textContent: '', events: {},
    addEventListener(name, fn) { this.events[name] = fn; } });
  const elements = Object.fromEntries(['coupon', 'applyCoupon', 'couponMsg', 'payBtn', 'payError'].map(id => [id, element()]));
  const state = { amount: 1200, tokenize: [], charges: [], quoteHook: null, tokenHook: null };
  const context = vm.createContext({
    window: {
      BILLING_CONFIG: { devisUrl: '/quote', baseLabel: '20,00 €' },
      SQUARE_CONFIG: { appId: 'app', locationId: 'loc', payUrl: '/pay', email: 'test@example.com' },
      isSecureContext: true,
      Square: { payments: () => ({ card: async () => ({
        attach: async () => {},
        tokenize: async details => {
          state.tokenize.push(details);
          if (state.tokenHook) await state.tokenHook();
          return { status: 'OK', token: 'test-token' };
        },
      }) }) },
    },
    document: {
      getElementById: id => elements[id],
      querySelector: () => ({ content: 'test-csrf' }),
      querySelectorAll: () => [],
    },
    location: {},
    fetch: async (url, options) => {
      const body = JSON.parse(options.body);
      if (url === '/quote') {
        const amount = body.coupon ? state.amount : 2000;
        if (state.quoteHook) await state.quoteHook();
        return { ok: true, json: async () => ({ ok: true, amount_cents: amount, currency: 'EUR', amount_label: (amount/100).toFixed(2) + ' €' }) };
      }
      state.charges.push(body);
      return { ok: true, json: async () => ({ ok: true, redirect: '/merci' }) };
    },
  });
  const coupon = new vm.SourceTextModule(readFileSync(resolve(source, 'coupon.js'), 'utf8'), { context });
  const checkout = new vm.SourceTextModule(readFileSync(resolve(source, 'checkout.js'), 'utf8'), { context });
  await coupon.link(() => {});
  await checkout.link(() => coupon);
  await checkout.evaluate();
  await new Promise(setImmediate);
  return { elements, state, context };
}

test('coupon : affichage, Square et débit utilisent 12 euros et le même code figé', async () => {
  const { elements: el, state } = await harness();
  el.coupon.value = 'RABAT';
  el.coupon.events.input();
  await el.applyCoupon.events.click();
  assert.equal(el.payBtn.textContent, 'Payer 12.00 €');
  state.tokenHook = () => {
    assert.equal(el.coupon.disabled, true);
    assert.equal(el.applyCoupon.disabled, true);
    el.coupon.value = 'AUTRE'; // Même une mutation programmatique ne change pas le code envoyé.
  };
  await el.payBtn.events.click();
  assert.equal(state.tokenize[0].amount, '12.00');
  assert.equal(state.tokenize[0].currencyCode, 'EUR');
  assert.equal(state.charges[0].coupon, 'RABAT');
  assert.equal(state.charges[0].expected_amount_cents, 1200);
});

test('sans coupon : devis de base avant tokenisation', async () => {
  const { elements: el, state } = await harness();
  await el.payBtn.events.click();
  assert.equal(state.tokenize[0].amount, '20.00');
  assert.equal(state.charges[0].expected_amount_cents, 2000);
});

test('devis devenu plus cher : nouvelle confirmation avant Square', async () => {
  const { elements: el, state } = await harness();
  el.coupon.value = 'RABAT';
  await el.applyCoupon.events.click();
  state.amount = 1400;
  await el.payBtn.events.click();
  assert.equal(state.tokenize.length, 0);
  assert.equal(state.charges.length, 0);
  assert.match(el.couponMsg.textContent, /14.00/);
  assert.equal(el.coupon.disabled, false);
  await el.payBtn.events.click();
  assert.equal(state.tokenize[0].amount, '14.00');
});

test('une réponse de prévisualisation périmée ne remplace pas le nouveau champ', async () => {
  const { elements: el, state } = await harness();
  el.coupon.value = 'RABAT';
  let release;
  state.quoteHook = () => new Promise(resolve => { release = resolve; });
  const pending = el.applyCoupon.events.click();
  el.coupon.value = '';
  el.coupon.events.input();
  release();
  await pending;
  assert.equal(el.couponMsg.textContent, '');
  assert.equal(el.payBtn.textContent, 'Payer 20,00 €');
});
