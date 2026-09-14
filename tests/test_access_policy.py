import pytest

from yumnews.domain.enums import Plan
from yumnews.services.access_policy import (
    AccessPolicyFactory,
    FreeAccessPolicy,
    PremiumAccessPolicy,
)
from yumnews.services.errors import AccessDeniedError


def test_factory_maps_plans():
    assert isinstance(AccessPolicyFactory.for_plan(Plan.FREE), FreeAccessPolicy)
    assert isinstance(AccessPolicyFactory.for_plan(Plan.PREMIUM), PremiumAccessPolicy)
    assert AccessPolicyFactory.for_plan(None).label == "Visiteur"


def test_free_policy_blocks_premium_features_and_quotas():
    policy = FreeAccessPolicy()
    assert policy.can("follows") and not policy.can("upcoming")
    with pytest.raises(AccessDeniedError) as exc:
        policy.require("upcoming")
    assert exc.value.code == "premium_required" and exc.value.status_code == 402
    policy.check_quota("follows", 2)
    with pytest.raises(AccessDeniedError):
        policy.check_quota("follows", 3)
    assert policy.news_category_allowed("cinema") and not policy.news_category_allowed(
        "anime"
    )


def test_premium_policy_is_unlimited():
    policy = PremiumAccessPolicy()
    for feature in ("upcoming", "seasons", "actor_feed", "news_full", "anime_schedule"):
        policy.require(feature)
    policy.check_quota("follows", 10_000)
    assert policy.to_dict()["limits"]["follows"] is None
