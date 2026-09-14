// [Sol] Devis serveur commun à l'affichage et à la tokenisation Square.
const cfg = window.BILLING_CONFIG || {};
const input = document.getElementById('coupon');
const applyBtn = document.getElementById('applyCoupon');
const msg = document.getElementById('couponMsg');
const payBtn = document.getElementById('payBtn');
const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
let revision = 0;
let busy = false;
let displayedQuote = null;
export const couponCode = () => (input?.value || '').trim();

export function setCouponBusy(value) {
  busy = value;
  revision += 1; // Invalide également une prévisualisation encore en vol.
  if (input) input.disabled = value;
  if (applyBtn) applyBtn.disabled = value;
  document.querySelectorAll('.coupon-sync').forEach((el) => {
    const button = el.form?.querySelector('button[type="submit"]');
    if (button) button.disabled = value;
  });
}

function showQuote(data, code) {
  displayedQuote = { ...data, code };
  if (msg) {
    msg.textContent = code ? `Code appliqué : vous paierez ${data.amount_label} (au lieu de ${cfg.baseLabel}).` : '';
    msg.className = 'muted small ok';
  }
  if (payBtn) payBtn.textContent = `Payer ${data.amount_label}`;
}

export async function getQuote(code) {
  const res = await fetch(cfg.devisUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, Accept: 'application/json' },
    body: JSON.stringify({ coupon: code }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || 'Vérification du tarif impossible.');
  if (!Number.isInteger(data.amount_cents) || data.amount_cents < 0) throw new Error('Montant du devis invalide.');
  return data;
}

export async function paymentQuote(code) {
  const data = await getQuote(code);
  const changed = displayedQuote?.code === code && displayedQuote.amount_cents !== data.amount_cents;
  showQuote(data, code);
  if (changed) throw new Error('Le tarif a changé. Vérifiez le nouveau montant et cliquez à nouveau pour payer.');
  return data;
}

async function preview() {
  if (busy) return;
  const version = ++revision;
  const code = couponCode();
  try {
    const data = await getQuote(code);
    if (version === revision) showQuote(data, code);
  } catch (e) {
    if (version !== revision) return;
    displayedQuote = null;
    if (payBtn) payBtn.textContent = 'Vérifier le tarif et payer';
    if (msg) { msg.textContent = e.message; msg.className = 'field-error small'; }
  }
}

input?.addEventListener('input', () => {
  revision += 1;
  displayedQuote = null;
  if (msg) msg.textContent = '';
  if (payBtn && !busy) payBtn.textContent = couponCode() ? 'Vérifier le tarif et payer' : `Payer ${cfg.baseLabel}`;
  document.querySelectorAll('.coupon-sync').forEach((el) => { el.value = couponCode(); });
});
applyBtn?.addEventListener('click', preview);
