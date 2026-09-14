"""[Sol] Deux transactions indépendantes démarrées ensemble, SQLite et PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_coupon_migration import legacy_engine, migrate
from yumnews.domain.models import Coupon, DiscordPassphrase, Invoice, Redemption, User
from yumnews.repositories import PassphraseRepository
from yumnews.services.errors import CouponError


def run_pair(operation):
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs = [executor.submit(operation, barrier) for _ in range(2)]
        return [job.result(timeout=15) for job in jobs]


def test_simultaneous_checkouts_cannot_exceed_last_place(container, legacy_engine):
    migrate(legacy_engine)
    with Session(legacy_engine) as session, session.begin():
        session.add(Coupon(code="LAST", kind="percent", value=20, max_redemptions=1))

    def attempt(barrier):
        with Session(legacy_engine) as session, session.begin():
            user = session.get(User, 1)
            barrier.wait(timeout=5)
            try:
                container.billing.start_hosted_checkout(
                    session, user, "nowpayments", "LAST"
                )
                return "reserved"
            except CouponError:
                return "refused"

    assert sorted(run_pair(attempt)) == ["refused", "reserved"]


def test_simultaneous_claims_have_exactly_one_winner(container, legacy_engine):
    migrate(legacy_engine)
    phrase = "c" * 40
    with Session(legacy_engine) as session, session.begin():
        session.add(DiscordPassphrase(user_id=1, phrase=phrase))

    def attempt(barrier):
        with Session(legacy_engine, expire_on_commit=False) as session, session.begin():
            old = PassphraseRepository(session).by_phrase(phrase)
            assert old.status == "pending"
            barrier.wait(timeout=5)
            return container.passphrases.claim(session, phrase) is not None

    assert sorted(run_pair(attempt)) == [False, True]


def test_simultaneous_success_webhooks_redeem_once(container, legacy_engine):
    migrate(legacy_engine)
    with Session(legacy_engine) as session, session.begin():
        session.add(Coupon(code="ONCE", kind="percent", value=20))
        user = session.get(User, 1)
        payment, _ = container.billing.start_hosted_checkout(
            session, user, "nowpayments", "ONCE"
        )
        order = payment.order_id

    def attempt(barrier):
        with Session(legacy_engine) as session, session.begin():
            barrier.wait(timeout=5)
            return container.billing.handle_hosted_notification(
                session,
                "nowpayments",
                json.dumps({"order_id": order, "status": "finished"}).encode(),
                "good",
            ).status

    assert run_pair(attempt) == ["succeeded", "succeeded"]
    with Session(legacy_engine) as session:
        assert session.scalar(select(func.count()).select_from(Redemption)) == 1
        assert session.scalar(select(func.count()).select_from(Invoice)) == 1
