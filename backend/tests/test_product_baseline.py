from app.config import settings, should_seed_demo_data


def test_demo_seed_is_impossible_in_production():
    previous_environment = settings.environment
    previous_seed = settings.seed_demo_data
    try:
        settings.environment = "production"
        settings.seed_demo_data = True
        assert should_seed_demo_data() is False
        settings.environment = "development"
        settings.seed_demo_data = False
        assert should_seed_demo_data() is False
        settings.seed_demo_data = True
        assert should_seed_demo_data() is True
    finally:
        settings.environment = previous_environment
        settings.seed_demo_data = previous_seed


def test_personalization_metrics_exposes_product_funnel():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/api/v1/personalization/metrics")
        assert response.status_code == 200
        funnel = response.json()["funnel"]
        assert set(funnel) >= {
            "recommendation_batches",
            "outfits_generated",
            "outfits_decided",
            "adoption_rate",
            "rejection_rate",
            "replacement_rate",
            "rule_fallback_rate",
        }


def test_explicit_style_and_garment_preferences_persist():
    from fastapi.testclient import TestClient
    from app.main import app

    headers={"x-ootd-dev-user":"preference-onboarding@example.test"}
    payload={"temperature_preference":"怕冷","preferred_styles":["简约"],"avoided_styles":["街头"],"preferred_item_terms":["衬衫"],"avoided_item_terms":["高跟鞋"],"preferred_colors":[],"avoided_colors":[],"restrictions":["优先适合步行"],"visual_goals":[],"photo_retention_consent":False}
    with TestClient(app) as client:
        saved=client.put("/api/v1/profile",headers=headers,json=payload)
        assert saved.status_code==200,saved.text
        profile=client.get("/api/v1/profile",headers=headers).json()
        assert profile["avoided_styles"]==["街头"]
        assert profile["preferred_item_terms"]==["衬衫"]
        assert profile["avoided_item_terms"]==["高跟鞋"]


def test_redis_cache_failure_falls_back_to_database(monkeypatch):
    from app import preference_cache
    from app.database import SessionLocal
    from app.models import UserProfile

    class OfflineRedis:
        def ping(self):raise ConnectionError("offline")
    monkeypatch.setattr(preference_cache,"_client",OfflineRedis())
    monkeypatch.setattr(preference_cache,"_retry_after",0.0)
    with SessionLocal() as db:
        profile=preference_cache.recommendation_profile(db,"u_1001")
        assert isinstance(profile,UserProfile)
