"""Async multi-tier scraper engine for Ethiopian capital-market feeds."""

import asyncio
import hashlib
import logging
import re
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse, unquote

import httpx
import urllib3
from bs4 import BeautifulSoup

from ethio_fin_bureau.config import HEADERS, REQUEST_TIMEOUT, TARGET_SOURCES

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class FinancialBureauIngestionEngine:
    """Scrapes configured feeds and returns raw headline payloads."""

    MIN_HEADLINE_LENGTH = 15

    def __init__(self) -> None:
        self._seen_urls: Set[str] = set()
        self._seen_hashes: Set[str] = set()

    @staticmethod
    def generate_sha256(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def sanitize_headline(raw_text: str) -> str:
        text = re.sub(r"\d+\s+downloads", "", raw_text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def title_from_slug(url: str) -> Optional[str]:
        """Derive a readable title from URL slug when DOM text is truncated."""
        path = unquote(urlparse(url).path.rstrip("/"))
        if not path:
            return None
        slug = path.split("/")[-1]
        if not slug or slug.isdigit() or len(slug) < 8:
            return None
        title = slug.replace("-", " ").strip()
        return title[:1].upper() + title[1:] if title else None

    @staticmethod
    def resolve_url(link: str, base_url: str) -> str:
        if not link:
            return ""
        return urljoin(base_url, link.split("#")[0])

    async def fetch_page(self, client: httpx.AsyncClient, url: str) -> Optional[str]:
        try:
            response = await client.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
            )
            if response.status_code not in (200, 203):
                logger.warning("Non-OK status %s for %s", response.status_code, url)
                return None
            if len(response.text) < 500:
                logger.warning("Suspiciously short response (%d bytes) for %s", len(response.text), url)
                return None
            return response.text
        except httpx.HTTPError as exc:
            logger.warning("Fetch failed for %s: %s", url, exc)
            return None

    def _pick_containers(self, soup: BeautifulSoup, source_config: Dict):
        css = source_config.get("container_css")
        if css:
            return soup.select(css)
        return soup.find_all(source_config["container_tag"])

    def _extract_title_and_link(self, card, source_config: Dict) -> tuple[Optional[str], Optional[str]]:
        title_elem = card.find(source_config["title_tag"])
        link_elem = card.find(source_config["link_tag"])

        if not title_elem:
            title_elem = card.find(re.compile(r"^h[1-4]$"))
        if not link_elem and card.name == "a":
            link_elem = card

        if not link_elem:
            return None, None

        link = link_elem.get("href", "")
        raw_text = ""

        if title_elem:
            raw_text = title_elem.get_text(strip=True)
        elif link_elem.get("title"):
            raw_text = link_elem["title"]
        elif link_elem.get("aria-label"):
            raw_text = link_elem["aria-label"]

        headline = self.sanitize_headline(raw_text)

        # Prefer longer title from slug when DOM headline looks truncated
        slug_title = self.title_from_slug(link)
        if slug_title and (not headline or headline.endswith("...") or len(slug_title) > len(headline) + 10):
            headline = slug_title

        return headline, link

    def parse_payload(self, source_config: Dict, html_content: str) -> List[Dict]:
        soup = BeautifulSoup(html_content, "html.parser")
        extracted: List[Dict] = []
        base_url = source_config.get("base_url", source_config["url"])

        for card in self._pick_containers(soup, source_config):
            headline, link = self._extract_title_and_link(card, source_config)
            if not headline or not link:
                continue

            if len(headline) < self.MIN_HEADLINE_LENGTH:
                continue

            url = self.resolve_url(link, base_url)
            if not url.startswith("http"):
                continue

            # URL-level deduplication (catches truncated headline duplicates)
            url_key = url.rstrip("/").lower()
            if url_key in self._seen_urls:
                continue

            payload_hash = self.generate_sha256(f"{headline}|{url_key}")
            if payload_hash in self._seen_hashes:
                continue

            self._seen_urls.add(url_key)
            self._seen_hashes.add(payload_hash)

            extracted.append({
                "source_name": source_config["source_name"],
                "tier": source_config["tier"],
                "headline": headline,
                "url": url,
                "content_hash": payload_hash,
            })

        return extracted

    async def run(self) -> List[Dict]:
        logger.info("Starting B2B Financial Intelligence Scraping Layer...")
        all_payloads: List[Dict] = []

        async with httpx.AsyncClient(verify=False) as client:
            tasks = [self.fetch_page(client, target["url"]) for target in TARGET_SOURCES]
            results = await asyncio.gather(*tasks)

            for target_config, raw_html in zip(TARGET_SOURCES, results):
                if not raw_html:
                    logger.warning("[%s] No HTML retrieved.", target_config["source_name"])
                    continue
                docs = self.parse_payload(target_config, raw_html)
                logger.info("[%s] Extracted %d raw items.", target_config["source_name"], len(docs))
                all_payloads.extend(docs)

        return all_payloads
