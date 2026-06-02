import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.business_repo import BusinessRepository, DAYS_MAP
from app.services.business_config import BusinessConfig, DEMO_BUSINESS
from app.models.db_models import Business, Service, BusinessHour


@pytest.mark.anyio
async def test_get_business_by_phone_cache_hit():
    repo = BusinessRepository()
    # Mock Redis client
    mock_redis = AsyncMock()
    repo._redis = mock_redis

    test_config = BusinessConfig(
        business_id="123",
        name="Test Salon",
        services=[{"id": "corte", "name": "Corte", "duration_min": 30, "price": 100}],
        working_hours={"monday": {"start": "09:00", "end": "17:00"}},
        phone_number_id="5551234"
    )

    # Redis returns the serialized JSON
    mock_redis.get.return_value = test_config.model_dump_json()

    # Call get_business_by_phone
    result = await repo.get_business_by_phone("5551234")

    # Assertions
    assert result.business_id == "123"
    assert result.name == "Test Salon"
    mock_redis.get.assert_called_once_with("business:phone:5551234")


@pytest.mark.anyio
async def test_get_business_by_phone_cache_miss_db_hit():
    repo = BusinessRepository()
    mock_redis = AsyncMock()
    repo._redis = mock_redis
    mock_redis.get.return_value = None  # Cache miss

    # Mock DB query
    mock_db_business = MagicMock(spec=Business)
    mock_db_business.id = 456
    mock_db_business.name = "DB Salon"
    mock_db_business.phone_number_id = "5556789"

    mock_service = MagicMock(spec=Service)
    mock_service.id = 123
    mock_service.list_item_id = "barba"
    mock_service.name = "Arreglo de barba"
    mock_service.duration_min = 20
    mock_service.price = 80.0
    mock_db_business.services = [mock_service]

    mock_hour = MagicMock(spec=BusinessHour)
    mock_hour.day_of_week = 0  # Monday
    mock_hour.is_closed = False
    mock_hour.start_time = "10:00"
    mock_hour.end_time = "18:00"
    mock_db_business.working_hours = [mock_hour]

    with patch("app.services.business_repo.SessionLocal") as mock_session_local:
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = mock_db_business

        result = await repo.get_business_by_phone("5556789")

        assert result.business_id == "456"
        assert result.name == "DB Salon"
        assert len(result.services) == 1
        assert result.services[0]["id"] == "barba"
        assert result.working_hours["monday"] == {"start": "10:00", "end": "18:00"}
        assert result.working_hours["tuesday"] is None  # other days not provided

        # Verify cached in Redis
        mock_redis.setex.assert_called_once()
        cache_key, ttl, serialized = mock_redis.setex.call_args[0]
        assert cache_key == "business:phone:5556789"
        assert ttl == 3600


@pytest.mark.anyio
async def test_get_business_by_phone_fallback():
    repo = BusinessRepository()
    mock_redis = AsyncMock()
    repo._redis = mock_redis
    mock_redis.get.return_value = None  # Cache miss

    with patch("app.services.business_repo.SessionLocal") as mock_session_local:
        mock_session = MagicMock()
        mock_session_local.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = None  # DB miss

        result = await repo.get_business_by_phone("unknown_phone")

        # Returns default demo business
        assert result.business_id == DEMO_BUSINESS.business_id
        assert result.name == DEMO_BUSINESS.name


@pytest.mark.anyio
async def test_invalidate_business_cache():
    repo = BusinessRepository()
    mock_redis = AsyncMock()
    repo._redis = mock_redis

    success = await repo.invalidate_business_cache("5551234")

    assert success is True
    mock_redis.delete.assert_called_once_with("business:phone:5551234")
