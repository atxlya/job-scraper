from app.core.settings import get_settings


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("GEMINI_DAILY_CAP", "100")
    assert get_settings().gemini_daily_cap == 100


def test_settings_defaults(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    s = get_settings()
    assert s.gemini_model == "gemini-3.5-flash-lite"
    assert s.gemini_rpm == 5
    assert s.http_min_interval_s == 2.5
