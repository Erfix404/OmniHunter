import time
from unittest.mock import MagicMock, patch
import pytest

from core.scrapers.base import BaseScraper, BrowserScraperBase
from core.scrapers.ponisha import PonishaScraper
from core.scrapers.parscoders import ParscodersScraper
from core.scrapers.freelancer import FreelancerScraper


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

    # Every scraper's platform name is a real key in config.yaml's platforms block.
    assert scraper_platforms == config_keys

    # ...and the language-routing classification uses names drawn from that same
    # set, so a name that does not match a config key cannot reach the router.
    assert IRANIAN_PLATFORMS.issubset(config_keys)
    # The Iranian/foreign split is the routing contract: Persian marketplaces get
    # Persian keywords, the foreign one does not.
    assert IRANIAN_PLATFORMS == {"ponisha", "parscoders"}
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

from core.scrapers.bitjob import BitjobScraper
from core.scrapers.karlancer import KarlancerScraper
from core.scrapers.guru import GuruScraper
from core.scrapers.laborx import LaborXScraper

def test_new_scraper_platforms_are_pinned():
    assert BitjobScraper.platform == "bitjob"
    assert KarlancerScraper.platform == "karlancer"
    assert GuruScraper.platform == "guru"
    assert LaborXScraper.platform == "laborx"

def test_bitjob_scraper_parsing():
    scraper = BitjobScraper()
    html = '''<div class="project-card"><h2><a href="/project/123">Test Bitjob</a></h2><div class="budget">1000 تا 2000 تومان</div></div>'''
    res = scraper.parse_html(html)
    assert len(res) == 1
    assert res[0]["platform_id"] == "123"

def test_guru_scraper_parsing():
    scraper = GuruScraper()
    html = '''<div class="jobRecord"><h2><a href="/job/456">Test Guru</a></h2><div class="budget">$100 - $200</div></div>'''
    res = scraper.parse_html(html)
    assert len(res) == 1
    assert res[0]["currency"] == "USD"
