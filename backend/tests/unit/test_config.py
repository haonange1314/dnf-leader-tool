from app.core.config import Settings


def test_cors_origins_are_normalized() -> None:
    settings = Settings(cors_origins="http://localhost:5173, https://example.test ")

    assert settings.cors_origin_list == ["http://localhost:5173", "https://example.test"]
