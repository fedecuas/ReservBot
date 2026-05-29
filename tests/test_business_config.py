from app.services.business_config import get_business_by_phone, DEMO_BUSINESS


def test_get_business_by_phone_found():
    business = get_business_by_phone("1147614285101997")
    assert business.business_id == "demo"
    assert business.name == "Barbería El Estilo"
    assert len(business.services) == 4


def test_get_business_by_phone_fallback():
    business = get_business_by_phone("non_existent_phone_id")
    assert business.business_id == "demo"
    assert business.name == "Barbería El Estilo"
