// [Sol] Réouverture de la CMP officielle, sans consentement inventé ni stockage maison.
const button = document.getElementById('google-consent-settings');
if (button) {
  window.googlefc = window.googlefc || {};
  window.googlefc.callbackQueue = window.googlefc.callbackQueue || [];
  window.googlefc.callbackQueue.push({
    CONSENT_API_READY: () => {
      if (typeof window.googlefc.showRevocationMessage === 'function') button.hidden = false;
    },
  });
  button.addEventListener('click', () => window.googlefc.showRevocationMessage?.());
}
