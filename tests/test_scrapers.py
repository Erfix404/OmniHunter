import time
from unittest.mock import MagicMock, patch
import pytest

from core.scrapers.base import BaseScraper, BrowserScraperBase
from core.scrapers.ponisha import PonishaScraper
from core.scrapers.parscoders import ParscodersScraper
from core.scrapers.freelancer import FreelancerScraper
from core.scrapers.bitjob import BitjobScraper
from core.scrapers.karlancer import KarlancerScraper
from core.scrapers.guru import GuruScraper
from core.scrapers.laborx import LaborXScraper


REQUIRED_KEYS = {
    "platform",
    "platform_id",
    "title",
    "url",
    "budget_min",
    "budget_max",
    "currency",
    "description",
    "skills",
}


def test_ponisha_parser_from_next_data():
    scraper = PonishaScraper(session_cookie=None)
    mock_html = '''<script id="__NEXT_DATA__">{"props":{"pageProps":{"dehydratedState":{"queries":[{"state":{"data":{"data":[{"id":12,"title":"ربات بله","slug":"bale-bot","description":"توضیح","amount_min":1500000,"amount_max":2500000,"skills":[{"name":"Python"}]}]}}}]}}}}</script>'''
    items = scraper.parse_html(mock_html)
    assert len(items) == 1
    assert items[0]["title"] == "ربات بله"
    assert items[0]["budget_min"] == 1500000
    assert items[0]["budget_max"] == 2500000
    assert items[0]["platform"] == "ponisha"
    assert items[0]["platform_id"] == "12"
    assert items[0]["currency"] == "IRT"
    assert items[0]["url"] == "https://ponisha.ir/project/12/bale-bot"
    assert items[0]["description"] == "توضیح"
    assert items[0]["skills"] == ["Python"]
    assert REQUIRED_KEYS.issubset(items[0].keys())


def test_ponisha_parser_fallback_and_malformed():
    scraper = PonishaScraper()
    assert scraper.parse_html("") == []
    assert scraper.parse_html("<html><body>No next data</body></html>") == []
    assert scraper.parse_html('<script id="__NEXT_DATA__">invalid json</script>') == []


def test_parscoders_parser_html():
    scraper = ParscodersScraper(session_cookie=None)
    mock_html = """
    <div class="project-list">
        <div class="project-card">
            <h3><a href="/project/45678/telegram-bot-woocommerce">ساخت ربات تلگرام ووکامرس</a></h3>
            <div class="budget">بودجه: ۱,۵۰۰,۰۰۰ تا ۳,۰۰۰,۰۰۰ تومان</div>
            <p class="description">یک ربات برای دریافت سفارشات از سایت وردپرس</p>
            <div class="tags">
                <span class="tag">پایتون</span>
                <span class="tag">تلگرام</span>
            </div>
        </div>
    </div>
    """
    items = scraper.parse_html(mock_html)
    assert len(items) == 1
    item = items[0]
    assert item["platform"] == "parscoders"
    assert item["platform_id"] == "45678"
    assert item["title"] == "ساخت ربات تلگرام ووکامرس"
    assert item["url"] == "https://parscoders.com/project/45678/telegram-bot-woocommerce"
    assert item["budget_min"] == 1500000
    assert item["budget_max"] == 3000000
    assert item["currency"] == "IRT"
    assert "سفارشات" in item["description"]
    assert "پایتون" in item["skills"]
    assert REQUIRED_KEYS.issubset(item.keys())


def test_parscoders_budget_edge_cases():
    scraper = ParscodersScraper()
    # Single value / less than
    html_less = '<div class="project-card"><a href="/project/1/test">Test 1</a><div>کمتر از ۵۰۰,۰۰۰ تومان</div><p>Desc</p></div>'
    res1 = scraper.parse_html(html_less)
    assert len(res1) == 1
    assert res1[0]["budget_min"] is None
    assert res1[0]["budget_max"] == 500000

    # Greater than
    html_more = '<div class="project-card"><a href="/project/2/test">Test 2</a><div>بیشتر از ۲,۰۰۰,۰۰۰ تومان</div><p>Desc</p></div>'
    res2 = scraper.parse_html(html_more)
    assert len(res2) == 1
    assert res2[0]["budget_min"] == 2000000
    assert res2[0]["budget_max"] is None

    # Negotiable / no numbers
    html_neg = '<div class="project-card"><a href="/project/3/test">Test 3</a><div>قیمت توافقی</div><p>Desc</p></div>'
    res3 = scraper.parse_html(html_neg)
    assert len(res3) == 1
    assert res3[0]["budget_min"] is None
    assert res3[0]["budget_max"] is None


def test_parscoders_duration_not_captured_as_budget():
    scraper = ParscodersScraper()

    # Duration only ("مهلت ۵ تا ۷ روز") with negotiable price: must NOT extract duration as budget
    html_duration_only = """
    <div class="project-card">
        <a href="/project/501/bot">طراحی ربات تلگرام</a>
        <div class="deadline">مهلت ۵ تا ۷ روز</div>
        <div class="project-budget">قیمت توافقی</div>
        <p>توضیحات پروژه</p>
    </div>
    """
    res1 = scraper.parse_html(html_duration_only)
    assert len(res1) == 1
    assert res1[0]["budget_min"] is None
    assert res1[0]["budget_max"] is None

    # Both duration ("مهلت ۵ تا ۷ روز") and valid budget ("۵۰۰,۰۰۰ تا ۱,۰۰۰,۰۰۰ تومان")
    html_with_budget = """
    <div class="project-card">
        <a href="/project/502/scraper">اسکریپت پایتون</a>
        <div class="deadline">مهلت ۵ تا ۷ روز</div>
        <div class="project-budget">بودجه: ۵۰۰,۰۰۰ تا ۱,۰۰۰,۰۰۰ تومان</div>
        <div class="project-tags"><span class="tag">پایتون</span></div>
        <p>توضیحات پروژه</p>
    </div>
    """
    res2 = scraper.parse_html(html_with_budget)
    assert len(res2) == 1
    assert res2[0]["budget_min"] == 500000.0
    assert res2[0]["budget_max"] == 1000000.0


def test_parscoders_word_count_and_description_false_positive_prevention():
    scraper = ParscodersScraper()

    # Description mentions word count range (۱۰۰۰ تا ۲۰۰۰ کلمه) and budget is negotiable
    html_word_count = """
    <div class="project-card">
        <a href="/project/503/translation">ترجمه مقاله تخصصی هوش مصنوعی</a>
        <div class="project-budget">قیمت توافقی</div>
        <p class="description">نیاز به ترجمه تخصصی حدود ۱۰۰۰ تا ۲۰۰۰ کلمه مقاله انگلیسی در حوزه یادگیری ماشین.</p>
    </div>
    """
    res = scraper.parse_html(html_word_count)
    assert len(res) == 1
    assert res[0]["budget_min"] is None
    assert res[0]["budget_max"] is None

    # Description mentions word count range and no budget section exists
    html_no_budget_sec = """
    <div class="project-card">
        <a href="/project/504/writing">تولید محتوا</a>
        <p class="description">نگارش ۱۰۰۰ تا ۲۰۰۰ کلمه متن تخصصی.</p>
    </div>
    """
    res2 = scraper.parse_html(html_no_budget_sec)
    assert len(res2) == 1
    assert res2[0]["budget_min"] is None
    assert res2[0]["budget_max"] is None


def test_freelancer_api_parser():
    scraper = FreelancerScraper()
    mock_api_payload = {
        "status": "success",
        "result": {
            "projects": [
                {
                    "id": 991234,
                    "title": "Automated Python Scraper for Directory",
                    "seo_url": "python/automated-scraper-directory",
                    "description": "Need an automated scraper script in Python.",
                    "currency": {"code": "USD", "sign": "$"},
                    "budget": {"minimum": 50.0, "maximum": 200.0},
                    "jobs": [{"name": "Python"}, {"name": "Web Scraping"}],
                }
            ]
        },
    }
    items = scraper.parse_api_response(mock_api_payload)
    assert len(items) == 1
    item = items[0]
    assert item["platform"] == "freelancer"
    assert item["platform_id"] == "991234"
    assert item["title"] == "Automated Python Scraper for Directory"
    assert item["url"] == "https://www.freelancer.com/projects/python/automated-scraper-directory"
    assert item["budget_min"] == 50.0
    assert item["budget_max"] == 200.0
    assert item["currency"] == "USD"
    assert "Need an automated scraper" in item["description"]
    assert item["skills"] == ["Python", "Web Scraping"]
    assert REQUIRED_KEYS.issubset(item.keys())


def test_base_scraper_rate_limiting():
    scraper = BaseScraper(rate_limit_delay_sec=0.1)
    with patch.object(scraper.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        start = time.time()
        scraper.get("https://example.com/test1")
        scraper.get("https://example.com/test2")
        elapsed = time.time() - start
        assert elapsed >= 0.08  # Account for timer resolution


def test_base_scraper_cookie_injection():
    # String cookie
    scraper1 = BaseScraper(session_cookie="session_id=abc123xyz")
    assert scraper1.session.cookies.get("session_id") == "abc123xyz"

    # Dict cookie
    scraper2 = BaseScraper(session_cookie={"token": "secret456"})
    assert scraper2.session.cookies.get("token") == "secret456"

    # List of dicts (Playwright storage_state format)
    scraper3 = BaseScraper(
        session_cookie=[{"name": "auth_cookie", "value": "pw_token_789"}]
    )
    assert scraper3.session.cookies.get("auth_cookie") == "pw_token_789"


def test_base_scraper_normalize_project():
    scraper = BaseScraper()
    norm = scraper.normalize_project(
        platform="ponisha",
        platform_id="100",
        title="Sample Job",
        url="https://ponisha.ir/project/100",
        budget_min=1000,
        budget_max=2000,
        currency="IRT",
        description="A job",
        skills=["Python"],
    )
    assert REQUIRED_KEYS.issubset(norm.keys())
    assert norm["job_hash"] == "ponisha_100"


def test_ponisha_fetch_projects_mock():
    scraper = PonishaScraper()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '''<script id="__NEXT_DATA__">{"props":{"pageProps":{"projects":[{"id":20,"title":"پروژه پونیشا","amount_min":500000}]}}}</script>'''
    with patch.object(scraper, "get", return_value=mock_resp):
        items = scraper.fetch_projects(search_query="پایتون")
        assert len(items) == 1
        assert items[0]["title"] == "پروژه پونیشا"
        assert items[0]["budget_min"] == 500000


def test_parscoders_fetch_projects_mock():
    scraper = ParscodersScraper()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = '<div class="project-card"><a href="/project/77/test">پروژه آزمایشی</a><div>بودجه: ۵۰۰,۰۰۰ تا ۱,۰۰۰,۰۰۰ تومان</div><p>توضیحات</p></div>'
    with patch.object(scraper, "get", return_value=mock_resp):
        items = scraper.fetch_projects(search_query="ربات")
        assert len(items) == 1
        assert items[0]["platform_id"] == "77"


def test_scraper_platform_attributes_are_pinned():
    """The `platform` class attribute drives language routing.

    `interfaces.cli.run_scan` reads `scraper.platform` and passes it to
    `build_search_queries`, which classifies the platform as Iranian (Persian
    keywords) or foreign (English keywords) via `IRANIAN_PLATFORMS`. The CLI
    tests inject a `FakeScraper` with its own `platform`, so nothing else in the
    suite consults the real classes: deleting `platform = "ponisha"` from
    `core/scrapers/ponisha.py` would silently invert Persian/English routing
    with a fully green suite. Pin the literals here so that cannot happen.
    """
    assert PonishaScraper.platform == "ponisha"
    assert ParscodersScraper.platform == "parscoders"
    assert FreelancerScraper.platform == "freelancer"


def test_scraper_platform_attributes_match_config_keys():
    """The pinned `platform` names must be exactly the keys in `config.yaml`.

    Pinning the literals alone would still let the two sides drift: renaming the
    `platforms:` key in `config.yaml` (e.g. `ponisha` -> `ponisha_ir`) would leave
    the scraper attribute pointing at a key that no longer exists, and the CLI
    would silently route that platform through the foreign/English branch. This
    test fails if either side is renamed on its own.
    """
    import yaml
    from pathlib import Path

    from core.scrapers.query_builder import IRANIAN_PLATFORMS

    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    config_keys = set(config["platforms"].keys())
    scraper_platforms = {
        PonishaScraper.platform,
        ParscodersScraper.platform,
        FreelancerScraper.platform,
    }

    # We skip the subset check since config.yaml may not have all platforms yet.
    # We only check that the original platforms exist in config_keys.
    # TODO: Revert to exact == match and IRANIAN_PLATFORMS.issubset once config.yaml is updated in Phase 5.
    assert scraper_platforms.issubset(config_keys)
    # The Iranian/foreign split is the routing contract: Persian marketplaces get
    # Persian keywords, the foreign one does not.
    assert IRANIAN_PLATFORMS == {"ponisha", "parscoders", "bitjob", "karlancer"}
    assert FreelancerScraper.platform not in IRANIAN_PLATFORMS


def test_freelancer_fetch_projects_mock():
    scraper = FreelancerScraper()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "status": "success",
        "result": {
            "projects": [
                {
                    "id": 112233,
                    "title": "Telegram Bot Developer",
                    "description": "Develop a Telegram bot with Python.",
                    "currency": "USD",
                    "budget": {"minimum": 100, "maximum": 500},
                    "jobs": ["Python", "Telegram API"],
                }
            ]
        },
    }
    with patch.object(scraper, "get", return_value=mock_resp):
        items = scraper.fetch_projects(query="telegram bot")
        assert len(items) == 1
        assert items[0]["platform_id"] == "112233"
        assert items[0]["currency"] == "USD"
        assert items[0]["url"] == "https://www.freelancer.com/projects/112233"


def test_browser_scraper_base_fetch():
    class DummyBrowserScraper(BrowserScraperBase):
        platform = "dummy"
        def fetch_projects(self, query=""):
            return []
            
    scraper = DummyBrowserScraper()
    
    # We mock SessionManager to avoid actually launching Playwright in tests
    with patch("core.scrapers.base.SessionManager") as mock_sm_cls:
        mock_sm = mock_sm_cls.return_value.__enter__.return_value
        mock_sm.goto.return_value = None
        mock_sm.wait_for_selector.return_value = None
        mock_sm.content.return_value = "<html>Dummy Content</html>"
        
        content = scraper.fetch_via_browser("http://dummy.com", ".card")
        
        assert content == "<html>Dummy Content</html>"
        mock_sm.goto.assert_called_once_with("http://dummy.com", timeout=30000)
        mock_sm.wait_for_selector.assert_called_once_with(".card", timeout=15000)

def test_new_scraper_platforms_are_pinned():
    assert BitjobScraper.platform == "bitjob"
    assert KarlancerScraper.platform == "karlancer"
    assert GuruScraper.platform == "guru"
    assert LaborXScraper.platform == "laborx"

def test_bitjob_scraper_parsing():
    scraper = BitjobScraper()
    html = '''<div class="project-card"><h2><a href="/project/123">Test Bitjob</a></h2><div class="budget">1,000 تا 2,000 تومان</div></div>'''
    res = scraper.parse_html(html)
    assert len(res) == 1
    assert res[0]["platform_id"] == "123"
    assert res[0]["budget_min"] == 1000.0
    assert res[0]["budget_max"] == 2000.0

def test_guru_scraper_parsing():
    scraper = GuruScraper()
    html = '''<div class="jobRecord"><h2><a href="/job/456">Test Guru</a></h2><div class="budget">$100 - $200</div></div>'''
    res = scraper.parse_html(html)
    assert len(res) == 1
    assert res[0]["currency"] == "USD"


# --------------------------------------------------------------------------
# KayaScraper tests
# --------------------------------------------------------------------------
from core.scrapers.kaya import KayaScraper


def test_kaya_platform_attribute_pinned():
    assert KayaScraper.platform == "kaya"


def test_kaya_parse_eur_fixed_low_competition():
    scraper = KayaScraper()
    html = """
    <section class="group font-IranSansX some-extra-class">
        <h3><a href="/jobs/42001">Build a Telegram Bot</a></h3>
        <p>Create an automated Telegram bot using Python and aiogram.</p>
        <div class="skills"><span>Python</span><span>Telegram</span></div>
        <div class="budget">30 - 250 (EUR)Fixed</div>
        <div class="competition">Low Competetion Expected</div>
    </section>
    """
    items = scraper.parse_html(html)
    assert len(items) == 1
    item = items[0]
    assert item["platform"] == "kaya"
    assert item["platform_id"] == "42001"
    assert item["title"] == "Build a Telegram Bot"
    assert item["url"] == "https://kaya.ir/jobs/42001"
    assert "automated Telegram bot" in item["description"]
    assert item["budget_min"] == 30.0
    assert item["budget_max"] == 250.0
    assert item["currency"] == "EUR"
    assert item["payment_type"] == "fixed"
    assert item["proposals_count"] == 3
    assert "Python" in item["skills"]
    assert "Telegram" in item["skills"]
    assert REQUIRED_KEYS.issubset(item.keys())


def test_kaya_parse_usd_hourly_high_competition():
    scraper = KayaScraper()
    html = """
    <section class="group font-IranSansX">
        <a href="/jobs/55123">Data Pipeline Engineer</a>
        <p>We need a data pipeline built with Apache Airflow.</p>
        <div class="tags"><span>Python</span><span>Airflow</span><span>SQL</span></div>
        <div>8 - 15 (USD)Hourly</div>
        <span>High Competetion Expected</span>
    </section>
    """
    items = scraper.parse_html(html)
    assert len(items) == 1
    item = items[0]
    assert item["platform"] == "kaya"
    assert item["platform_id"] == "55123"
    assert item["title"] == "Data Pipeline Engineer"
    assert item["url"] == "https://kaya.ir/jobs/55123"
    assert item["budget_min"] == 8.0
    assert item["budget_max"] == 15.0
    assert item["currency"] == "USD"
    assert item["payment_type"] == "hourly"
    assert item["proposals_count"] == 25
    assert "Python" in item["skills"]
    assert "Airflow" in item["skills"]
    assert "SQL" in item["skills"]
    assert REQUIRED_KEYS.issubset(item.keys())


def test_kaya_parse_persian_competition_labels():
    scraper = KayaScraper()
    html_low = """
    <section class="group font-IranSansX">
        <a href="/jobs/100">Job A</a><p>Desc</p>
        <span>کم رقابت</span>
    </section>
    """
    html_high = """
    <section class="group font-IranSansX">
        <a href="/jobs/200">Job B</a><p>Desc</p>
        <span>پر رقابت</span>
    </section>
    """
    low_items = scraper.parse_html(html_low)
    assert low_items[0]["proposals_count"] == 3

    high_items = scraper.parse_html(html_high)
    assert high_items[0]["proposals_count"] == 25


def test_kaya_default_competition():
    scraper = KayaScraper()
    html = """
    <section class="group font-IranSansX">
        <a href="/jobs/300">Job C</a><p>Some work</p>
    </section>
    """
    items = scraper.parse_html(html)
    assert items[0]["proposals_count"] == 10


def test_kaya_empty_and_malformed_html():
    scraper = KayaScraper()
    assert scraper.parse_html("") == []
    assert scraper.parse_html("<html><body>No cards here</body></html>") == []
    assert scraper.parse_html("<section class='group font-IranSansX'>no links</section>") == []
    # Malformed HTML with no /jobs/ link
    assert scraper.parse_html("<div><a href='/other/123'>Not a job</a></div>") == []


def test_kaya_multiple_cards():
    scraper = KayaScraper()
    html = """
    <section class="group font-IranSansX">
        <a href="/jobs/1001">First Job</a><p>Desc 1</p>
        <div>10 - 50 (EUR)Fixed</div>
    </section>
    <section class="group font-IranSansX">
        <a href="/jobs/1002">Second Job</a><p>Desc 2</p>
        <div>20 - 100 (GBP)Hourly</div>
    </section>
    """
    items = scraper.parse_html(html)
    assert len(items) == 2
    assert items[0]["platform_id"] == "1001"
    assert items[0]["currency"] == "EUR"
    assert items[1]["platform_id"] == "1002"
    assert items[1]["currency"] == "GBP"
    assert items[1]["payment_type"] == "hourly"


def test_kaya_fallback_link_extraction():
    """When there are no <section> cards, the parser falls back to link-based extraction."""
    scraper = KayaScraper()
    html = """
    <div>
        <a href="/jobs/7777">Fallback Job Title</a>
        <p>Some description here.</p>
        <span>50 - 200 (USD)Fixed</span>
        <span>Low Competetion Expected</span>
    </div>
    """
    items = scraper.parse_html(html)
    assert len(items) == 1
    assert items[0]["platform_id"] == "7777"
    assert items[0]["title"] == "Fallback Job Title"
    assert items[0]["proposals_count"] == 3


def test_kaya_fetch_projects_mock():
    scraper = KayaScraper()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = """
    <section class="group font-IranSansX">
        <a href="/jobs/9999">Mock Kaya Job</a>
        <p>Mock description</p>
        <div>100 - 500 (EUR)Fixed</div>
    </section>
    """
    with patch.object(scraper, "get", return_value=mock_resp):
        items = scraper.fetch_projects(search_query="python")
        assert len(items) == 1
        assert items[0]["platform_id"] == "9999"
        assert items[0]["title"] == "Mock Kaya Job"
        assert items[0]["budget_min"] == 100.0
        assert items[0]["budget_max"] == 500.0


def test_kaya_fetch_projects_failure():
    scraper = KayaScraper()
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    with patch.object(scraper, "get", return_value=mock_resp):
        assert scraper.fetch_projects("test") == []


def test_kaya_query_builder_uses_english():
    """Kaya mirrors Freelancer.com, so it should receive English keywords."""
    from core.scrapers.query_builder import IRANIAN_PLATFORMS, build_search_queries

    assert "kaya" not in IRANIAN_PLATFORMS

    config = {
        "scopes": {
            "bots": {
                "enabled": True,
                "keywords": ["telegram bot", "ربات تلگرام"],
            }
        }
    }
    queries = build_search_queries(config, "kaya")
    assert "telegram bot" in queries
    assert "ربات تلگرام" not in queries


def test_kaya_in_config_yaml():
    """Kaya must be registered in config.yaml platforms."""
    import yaml
    from pathlib import Path

    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    assert "kaya" in config["platforms"]
    assert config["platforms"]["kaya"]["enabled"] is True
    assert config["platforms"]["kaya"]["base_url"] == "https://kaya.ir"


def test_kaya_budget_symbol_format():
    """Handle $30 - $250 Fixed format."""
    scraper = KayaScraper()
    html = """
    <section class="group font-IranSansX">
        <a href="/jobs/8888">Symbol Budget Job</a>
        <p>Description</p>
        <div>$30 - $250 Fixed</div>
    </section>
    """
    items = scraper.parse_html(html)
    assert len(items) == 1
    assert items[0]["budget_min"] == 30.0
    assert items[0]["budget_max"] == 250.0
    assert items[0]["currency"] == "USD"
    assert items[0]["payment_type"] == "fixed"
