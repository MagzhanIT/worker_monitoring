from config import Settings


def test_comma_separated_cors_origins_from_environment(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5000,http://localhost:8080",
    )
    value = Settings(_env_file=None)
    assert value.cors_origins == [
        "http://localhost:3000",
        "http://localhost:5000",
        "http://localhost:8080",
    ]


def test_development_environment_does_not_implicitly_enable_reload(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("APP_RELOAD", raising=False)

    value = Settings(_env_file=None)

    assert value.app_reload is False


def test_reload_can_be_enabled_explicitly(monkeypatch):
    monkeypatch.setenv("APP_RELOAD", "true")

    value = Settings(_env_file=None)

    assert value.app_reload is True


def test_development_allows_dynamic_loopback_frontend_ports():
    value = Settings(_env_file=None, app_env="development")

    assert value.cors_origin_regex == r"https?://(localhost|127[.]0[.]0[.]1)(:[0-9]+)?$"


def test_production_does_not_allow_dynamic_loopback_frontend_ports():
    value = Settings(_env_file=None, app_env="production")

    assert value.cors_origin_regex is None
