"""[Sol] Chargement Google limité aux pages de contenu et aux lecteurs gratuits."""

import re

CONTENT_ENDPOINTS = frozenset(
    {
        "public.home",
        "public.news_index",
        "public.news_article",
        "public.press_article",
        "dashboard.app",
    }
)


def client_for_page(settings, policy, endpoint):
    if not settings.adsense_enabled or policy.can("ad_free"):
        return None
    if endpoint not in CONTENT_ENDPOINTS:
        return None
    if not re.fullmatch(r"ca-pub-[0-9]{16}", settings.adsense_client):
        return None
    return settings.adsense_client
