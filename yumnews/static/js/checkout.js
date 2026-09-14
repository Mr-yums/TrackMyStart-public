import { couponCode, paymentQuote, setCouponBusy } from './coupon.js';
// Square Web Payments SDK : tokenisation carte + vérification 3-D Secure, puis débit côté serveur.
const cfg = window.SQUARE_CONFIG;
const btn = document.getElementById('payBtn'), errBox = document.getElementById('payError');
const csrf = document.querySelector('meta[name="csrf-token"]').content;
const showError = (m) => { errBox.textContent = m; errBox.hidden = false; };

(async () => {
  // [Sol] Ne pas laisser un bouton actif si le formulaire ne peut pas être initialisé.
  btn.disabled = true;
  if (!window.isSecureContext) return showError('Le paiement par carte nécessite une connexion HTTPS.');
  if (!window.Square) return showError('Le module de paiement Square ne s\'est pas chargé.');
  let card;
  try { const payments = window.Square.payments(cfg.appId, cfg.locationId); card = await payments.card(); await card.attach('#card-container'); }
  catch (e) { return showError('Initialisation du paiement impossible : ' + e.message); }

  btn.disabled = false;
  btn.addEventListener('click', async () => {
    if (btn.disabled) return;
    const coupon = couponCode(); // [Sol] Même code pendant devis, 3-D Secure et débit.
    setCouponBusy(true);
    errBox.hidden = true; btn.disabled = true; btn.textContent = 'Vérification du tarif…';
    try {
      const quote = await paymentQuote(coupon);
      // [Sol] Parcours Square actuel : la tokenisation inclut la vérification acheteur.
      const tok = await card.tokenize({ amount: (quote.amount_cents / 100).toFixed(2), currencyCode: quote.currency, intent: 'CHARGE', billingContact: { email: cfg.email }, customerInitiated: true, sellerKeyedIn: false });
      if (tok.status !== 'OK') throw new Error(tok.errors?.[0]?.message || 'Carte refusée.');
      const res = await fetch(cfg.payUrl, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, Accept: 'application/json' }, body: JSON.stringify({ token: tok.token, coupon, expected_amount_cents: quote.amount_cents }) });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || 'Paiement refusé.');
      location.href = data.redirect;
    } catch (e) { showError(e.message); btn.disabled = false; btn.textContent = 'Vérifier le tarif et réessayer'; setCouponBusy(false); }
  });
})();
