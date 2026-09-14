"""Lancement en développement : ``python app.py`` (ou ``flask --app app run``)."""

from yumnews import create_app

app = create_app()

if __name__ == "__main__":
    import os

    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "8800")),
        debug=False  # [Sol] Pas de débogueur exposé par défaut.,
    )
