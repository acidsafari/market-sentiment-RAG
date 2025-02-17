from langchain.agents import Tool, AgentExecutor, create_react_agent
from langchain_community.tools import BaseTool
from bs4 import BeautifulSoup
import requests
import logging
from datetime import datetime, timedelta
import ssl
from urllib3.exceptions import InsecureRequestWarning
from http.cookiejar import CookieJar
import time
from config import ScrapingConfig
from typing import Optional

class WebScrapingTool(BaseTool):
    name = "web_scraper"
    description = "Scrapes web content from specified URLs handling various errors"

    def __init__(self, config: ScrapingConfig):
        super().__init__()
        self.config = config
        self.session = self._setup_session()
        
    def _setup_session(self):
        session = requests.Session()
        session.cookies = CookieJar()
        session.headers.update({'User-Agent': self.config.user_agent})
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
        return session

    def _handle_request(self, url: str) -> Optional[str]:
        for attempt in range(self.config.retry_attempts):
            try:
                response = self.session.get(
                    url, 
                    timeout=self.config.timeout,
                    verify=False  # Note: In production, consider security implications
                )
                response.raise_for_status()
                return response.text
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    logging.error(f"Page not found: {url}")
                    return None
                elif e.response.status_code == 429:
                    wait_time = (attempt + 1) * 5
                    time.sleep(wait_time)
                    continue
            except (requests.exceptions.SSLError, ssl.SSLError):
                logging.warning(f"SSL Error for {url}, attempting without verification")
                continue
            except Exception as e:
                logging.error(f"Error scraping {url}: {str(e)}")
                if attempt == self.config.retry_attempts - 1:
                    return None
        return None

    def _extract_content(self, html: str) -> dict:
        soup = BeautifulSoup(html, 'html.parser')
        # Customize this based on your target websites
        content = {
            'text': soup.get_text(separator=' ', strip=True),
            'title': soup.title.string if soup.title else '',
            'timestamp': datetime.now().isoformat()
        }
        return content

    def _is_within_timeframe(self, date_str: str) -> bool:
        try:
            article_date = datetime.fromisoformat(date_str)
            cutoff_date = datetime.now() - timedelta(days=self.config.days_to_scrape)
            return article_date >= cutoff_date
        except:
            return True

    def __call__(self, urls: list[str]) -> list[dict]:
        results = []
        pages_processed = 0

        for url in urls:
            if pages_processed >= self.config.max_pages:
                break

            html = self._handle_request(url)
            if html:
                content = self._extract_content(html)
                if self._is_within_timeframe(content['timestamp']):
                    results.append(content)
                    pages_processed += 1

        return results 