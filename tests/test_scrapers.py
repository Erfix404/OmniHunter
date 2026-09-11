import time
from unittest.mock import MagicMock, patch
import pytest

from core.scrapers.base import BaseScraper
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

