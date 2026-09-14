"""[Sol] Deux avis simultanés et une modification des préférences ne s'écrasent pas."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from sqlalchemy.orm import Session
from test_coupon_migration import legacy_engine
from yumnews.services.recommendation_service import RecommendationService
from yumnews.services.preference_service import PreferenceService


def test_parallel_first_preferences_and_feedback_keep_both_namespaces(legacy_engine):
    service = RecommendationService("test-key")
    barrier = Barrier(3)

    def write(index):
        with Session(legacy_engine) as session:
            barrier.wait(timeout=10)
            if index == 0:
                PreferenceService().save(session, 1, {"compact_cards": True})
            else:
                token = service.signer.dumps(
                    {"user": 1, "id": str(index), "title": "Test", "topics": ["cinema"]}
                )
                service.feedback(session, 1, {"token": token, "action": "more"})
            session.commit()

    with ThreadPoolExecutor(max_workers=3) as workers:
        list(workers.map(write, range(3)))
    with Session(legacy_engine) as session:
        assert PreferenceService().get(session, 1)["compact_cards"] is True
        assert set(service.settings(session, 1)["feedback"]) == {"1", "2"}


def test_catalog_status_and_filters_do_not_overwrite_other_preferences(legacy_engine):
    # [Sol] Même verrou que les réglages du fil ; premières écritures concurrentes.
    from yumnews.services.catalog_preferences import CatalogPreferences
    from yumnews.services.access_policy import PremiumAccessPolicy

    service = CatalogPreferences()
    barrier = Barrier(4)

    def write(index):
        with Session(legacy_engine) as session:
            barrier.wait(timeout=10)
            if index == 0:
                PreferenceService().save(session, 1, {"compact_cards": True})
            elif index == 1:
                service.save_filters(
                    session, 1, PremiumAccessPolicy(), "movie", {"hide_seen": True}
                )
            else:
                service.mark(session, 1, "movie", index, {"seen": True})
            session.commit()

    with ThreadPoolExecutor(max_workers=4) as workers:
        list(workers.map(write, range(4)))
    with Session(legacy_engine) as session:
        data = service.get(session, 1)
        assert data["filters"]["movie"]["hide_seen"] is True
        assert set(data["titles"]) == {"movie:2", "movie:3"}
        assert PreferenceService().get(session, 1)["compact_cards"] is True


def test_preregistration_and_distinct_preferences_survive_simultaneous_writes(
    legacy_engine,
):
    # [Sol] Régression : consentement et champs de préférences modifiés ensemble.
    from yumnews.services.preregistration import PreregistrationService

    barrier = Barrier(3)

    def write(index):
        with Session(legacy_engine) as session:
            barrier.wait(timeout=10)
            if index == 0:
                PreferenceService().save(session, 1, {"compact_cards": True})
            elif index == 1:
                PreferenceService().save(session, 1, {"start_tab": "movies"})
            else:
                PreregistrationService().set_status(session, 1, True)
            session.commit()

    with ThreadPoolExecutor(max_workers=3) as workers:
        list(workers.map(write, range(3)))
    with Session(legacy_engine) as session:
        values = PreferenceService().get(session, 1)
        assert values["compact_cards"] is True and values["start_tab"] == "movies"
        assert PreregistrationService().status(session, 1)["active"] is True


def test_two_subscriptions_extend_instead_of_overlap(legacy_engine):
    # [Sol] Deux activations simultanées doivent donner deux périodes complètes.
    from yumnews.services.subscription_service import SubscriptionService
    from yumnews.domain.models import User, Subscription
    from sqlalchemy import select
    from datetime import timedelta

    barrier = Barrier(2)

    def activate(_):
        with Session(legacy_engine) as session:
            user = session.get(User, 1)
            barrier.wait(timeout=10)
            SubscriptionService(30).activate(session, user)
            session.commit()

    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(activate, range(2)))
    with Session(legacy_engine) as session:
        periods = list(
            session.scalars(select(Subscription).order_by(Subscription.started_at))
        )
        assert len(periods) == 2
        assert periods[0].current_period_end == periods[1].started_at
        assert periods[1].current_period_end - periods[0].started_at == timedelta(
            days=60
        )


def test_concurrent_free_follows_cannot_exceed_quota(legacy_engine):
    from yumnews.services.member_service import MemberService
    from yumnews.services.access_policy import FreeAccessPolicy
    from yumnews.services.errors import AccessDeniedError
    from yumnews.domain.models import User, Follow
    from sqlalchemy import select, func

    barrier = Barrier(5)

    def follow(index):
        with Session(legacy_engine) as session:
            user = session.get(User, 1)
            barrier.wait(timeout=10)
            try:
                MemberService().follow(
                    session,
                    user,
                    FreeAccessPolicy(),
                    {"id": index + 1, "name": "Person"},
                )
                session.commit()
                return True
            except AccessDeniedError:
                session.rollback()
                return False

    with ThreadPoolExecutor(max_workers=5) as workers:
        results = list(workers.map(follow, range(5)))
    assert sum(results) == 3
    with Session(legacy_engine) as session:
        assert session.scalar(select(func.count()).select_from(Follow)) == 3
