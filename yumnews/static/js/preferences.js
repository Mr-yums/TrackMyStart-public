// [Sol] Contrôleur du formulaire de préférences ; stockage assuré par le serveur.
import { api } from './api.js';
export class PreferencePanel {
  constructor(form, onSaved) {
    this.form = form;
    this.onSaved = onSaved;
    this.status = document.getElementById('preferencesStatus');
    form?.addEventListener('submit', (event) => this.save(event));
  }
  async save(event) {
    event.preventDefault();
    const button = this.form.querySelector('button[type="submit"]');
    const data = new FormData(this.form);
    const preferences = { sections: data.getAll('sections'), news_categories: data.getAll('news_categories'), news_sources: data.getAll('news_sources'), start_tab: data.get('start_tab'), compact_cards: data.has('compact_cards') };
    button.disabled = true; this.status.textContent = 'Enregistrement…';
    try {
      const result = await api.savePreferences(preferences);
      this.onSaved(result.preferences);
      this.status.textContent = 'Préférences enregistrées. Votre accueil est mis à jour.';
    } catch (error) { this.status.textContent = error.message || 'Enregistrement impossible. Réessayez.'; }
    finally { button.disabled = false; }
  }
}
