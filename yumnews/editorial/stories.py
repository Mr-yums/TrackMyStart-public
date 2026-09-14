"""[Sol] Sélection éditoriale manuelle, vérifiée le 10/09/2026.

Textes originaux fondés sur les sources liées ; pas de reproduction des articles.
Une nouvelle brève demande une lecture de source et une validation éditoriale.
"""

STORIES = (
    {
        "slug": "netflix-lust-stories-3-septembre",
        "category": "Netflix · à venir",
        "theme": "netflix",
        "title": "Lust Stories 3 : Netflix donne rendez-vous le 18 septembre",
        "lead": "La plateforme prépare un troisième volet de son anthologie indienne, avec quatre récits et quatre réalisateurs.",
        "status": "Annonce officielle",
        "date": "10 septembre 2026",
        "published_at": "2026-09-10",
        "paragraphs": [
            "Netflix annonce la sortie de Lust Stories 3 le 18 septembre 2026. Le film réunit quatre histoires autour des relations amoureuses et du désir, confiées à Vikramaditya Motwane, Kiran Rao, Shakun Batra et Vishal Bhardwaj.",
            "Le casting rassemble notamment Radhika Apte, Konkona Sen Sharma, Aditi Rao Hydari et Vijay Varma. Pour qui suit ces talents, l’intérêt tient à ce format : plusieurs regards de cinéastes réunis dans un même programme.",
        ],
        "context_title": "Le repère à garder",
        "context": "Il s’agit d’une anthologie : les quatre récits composent ce troisième volet. La date vient directement du communiqué Netflix ; la disponibilité précise de votre catalogue régional reste à vérifier auprès de la plateforme.",
        "source_name": "Netflix",
        "source_kind": "Communiqué officiel · annonce du 4 septembre 2026",
        "source_note": "Cette brève résume l’annonce de la plateforme. Elle ne constitue pas une critique du film.",
        "source_url": "https://about.netflix.com/en/news/four-acclaimed-directors-four-new-stories-emmy-r-nominated-anthology-film-franchise-lust-stories-unveils-third-instalment-premieres-september-18-on-netflix",
    },
    {
        "slug": "kathryn-newton-comedie-mike-birbiglia",
        "category": "Casting · cinéma",
        "theme": "cinema",
        "title": "Kathryn Newton en discussion pour la prochaine comédie de Mike Birbiglia",
        "lead": "Deadline rapporte des négociations autour de Old Friends New Friends, un projet de Focus Features.",
        "status": "Négociations rapportées",
        "date": "10 septembre 2026",
        "published_at": "2026-09-10",
        "paragraphs": [
            "Selon Deadline, Kathryn Newton est en pourparlers pour participer à Old Friends New Friends. Mike Birbiglia doit réaliser cette comédie à partir de son propre scénario.",
            "Le film suit un groupe d’amis de longue date réunis pour un mariage, confrontés aux changements survenus dans leurs vies. Deadline cite notamment Lucas Hedges et Geraldine Viswanathan parmi les interprètes déjà annoncés.",
        ],
        "context_title": "Ce qui reste ouvert",
        "context": "L’information concernant Kathryn Newton porte sur des discussions. Le rôle n’est pas détaillé dans l’article et sa participation ne doit donc pas être présentée comme définitivement acquise. Le tournage est envisagé à l’automne, selon la même source.",
        "source_name": "Deadline",
        "source_kind": "Information de presse · article du 10 septembre 2026",
        "source_note": "Attribution conservée à Deadline. Une confirmation du studio ou de l’équipe permettrait de mettre à jour le statut.",
        "source_url": "https://deadline.com/2026/09/kathryn-newton-old-friends-new-friends-mike-birbiglia-1237073451/",
    },
    {
        "slug": "c-a-vous-rendez-vous-culture-rentree",
        "category": "Télévision · rendez-vous",
        "theme": "television",
        "title": "C à vous : où retrouver la séquence consacrée aux talents et à la culture",
        "lead": "France Télévisions détaille la place des personnalités du cinéma et du divertissement dans la rentrée de l’émission.",
        "status": "Programme annoncé",
        "date": "10 septembre 2026",
        "published_at": "2026-09-10",
        "paragraphs": [
            "Le communiqué de rentrée de France Télévisions fixe le retour de C à vous au lundi 31 août, à 19 heures sur France 5 et france.tv.",
            "La deuxième partie accueille les personnalités de la culture et du divertissement autour d’Anne-Élisabeth Lemoine, avec notamment Pierre Lescure, Bertrand Chameroy et Lorrain Sénéchal. Ce rendez-vous permet de retrouver les talents au-delà de leurs films et séries.",
        ],
        "context_title": "Pour suivre une apparition précise",
        "context": "Ce communiqué décrit l’organisation de l’émission, pas une liste complète des invités à venir. L’annonce datée d’un invité sera nécessaire avant de lui associer un rendez-vous individuel sur TrackMyStart.",
        "source_name": "France Télévisions",
        "source_kind": "Communiqué officiel · rentrée 2026",
        "source_note": "Le début de saison indiqué est le 31 août. La page consultée ne donne pas de date de publication explicite.",
        "source_url": "https://www.francetvpro.fr/contenu-de-presse/77906049",
    },
    {
        "slug": "prime-video-neagley-maria-sten",
        "category": "Prime Video · séries",
        "theme": "prime",
        "title": "Neagley : Maria Sten au centre du prochain chapitre de l’univers Reacher",
        "lead": "Amazon présente cette nouvelle série dans son programme américain de septembre, avec un lancement annoncé le 16.",
        "status": "Annonce officielle · États-Unis",
        "date": "10 septembre 2026",
        "published_at": "2026-09-10",
        "paragraphs": [
            "Prime Video prépare une série centrée sur Frances Neagley, incarnée par Maria Sten. Amazon annonce le 16 septembre 2026 dans son calendrier des nouveautés aux États-Unis.",
            "Devenue détective privée à Chicago, l’ancienne militaire enquête après la mort suspecte d’un proche. Le projet prolonge l’univers de Reacher en donnant à ce personnage sa propre histoire.",
        ],
        "context_title": "Le calendrier à vérifier pour la France",
        "context": "La source consultée concerne le catalogue américain. Elle confirme le projet et cette date pour les États-Unis ; elle ne suffit pas à garantir la même disponibilité en France.",
        "source_name": "Amazon / Prime Video",
        "source_kind": "Programme officiel · septembre 2026 · États-Unis",
        "source_note": "Synthèse de la présentation publiée par Amazon. Disponibilité française à vérifier sur Prime Video.",
        "source_url": "https://www.aboutamazon.com/news/entertainment/prime-video-september-films-shows-sports-2026",
    },
)


def story_by_slug(slug):
    return next((story for story in STORIES if story["slug"] == slug), None)
