# -*- coding: utf-8 -*-
import urllib.parse
import logging
import time
from playwright.sync_api import BrowserContext
from playwright_stealth import Stealth
import storage_manager

logger = logging.getLogger(__name__)

def build_google_jobs_url(job_title: str, location: str) -> str:
    """Constructs the Google Jobs URL with proper URL encoding."""
    return f"https://www.google.com/search?q={urllib.parse.quote(job_title)}+jobs+in+{urllib.parse.quote(location)}&udm=8"

def scrape_job_urls(context: BrowserContext, job_title: str, location: str, max_jobs: int = 15) -> list[str]:
    """
    Navigates to Google Jobs (udm=8), iterates through job cards using a specific
    selector (div.EimVGf) to avoid matching header search tabs. Clicks each card
    to trigger Google's details panel update on the right, extracts Apply link hrefs,
    and resolves them in silent background tabs.
    """
    logger.info(f"Starting Google Jobs scrape for '{job_title}' in '{location}'...")

    page = context.new_page()
    stealth = Stealth()
    stealth.apply_stealth_sync(page)

    url = build_google_jobs_url(job_title, location)
    logger.info(f"Navigating to Google Jobs: {url}")

    try:
        page.goto(url)
        # CAPTCHA pause -- triggered when Google detects automation
        if "google_abuse" in page.url or "sorry/index" in page.url:
            print(
                "\n\033[1mWARNING: Google CAPTCHA detected! "
                "Please manually solve the CAPTCHA in the browser window.\033[0m\n"
            )
            input("Press Enter in the terminal once you have solved the CAPTCHA to resume...")

        # Wait for the job cards to load using the stable job card container selector
        page.locator("div.EimVGf").first.wait_for(timeout=15000)
    except Exception as e:
        logger.error(f"Failed to load Google Jobs widget: {e}")
        page.close()
        return []

    # Let the page settle
    page.wait_for_timeout(2000)

    # Scroll the job list panel to reveal more cards
    try:
        # Locate the scrollable infinity-scrolling panel
        list_container = page.locator("infinity-scrolling").first
        for _ in range(2):
            list_container.evaluate("element => element.scrollTop = element.scrollHeight")
            page.wait_for_timeout(1000)
        # Also scroll the page just in case
        for _ in range(2):
            page.evaluate("window.scrollBy(0, 1000)")
            page.wait_for_timeout(500)
    except Exception as e:
        logger.warning(f"Could not scroll to load more jobs: {e}")

    # Snapshot the full card list after scrolling
    cards = page.locator("div.EimVGf").all()
    num_cards = len(cards)
    logger.info(f"Found {num_cards} job cards on Google Jobs panel.")

    resolved_urls = []

    for i in range(min(num_cards, max_jobs)):
        logger.info(f"Processing job card {i + 1}/{min(num_cards, max_jobs)}...")

        try:
            card = cards[i]

            try:
                card.scroll_into_view_if_needed()
            except Exception:
                pass

            # Click the card to trigger Google's JS panel update
            card.click()
            page.wait_for_timeout(1500)   # wait for right-panel / page to settle

            # Collect all Apply links now visible on the page
            apply_links = page.locator("a:has-text('Apply')").all()

            for apply_link in apply_links:
                try:
                    text = apply_link.inner_text().strip()
                    if "Apply" not in text:
                        continue

                    logger.info(f"Found apply button: '{text}'. Resolving redirect...")

                    # Read the href directly -- never click the Apply link on the main page
                    href = apply_link.get_attribute("href") or ""
                    if not href or not href.startswith("http"):
                        continue

                    # Open a silent background tab to follow the redirect chain
                    redirect_page = context.new_page()
                    resolved_url = None
                    try:
                        redirect_page.goto(href, wait_until="commit", timeout=15000)

                        # Poll until we leave Google's redirect domain
                        start_time = time.time()
                        while time.time() - start_time < 12:
                            current_url = redirect_page.url
                            if (
                                current_url
                                and "google.com/url" not in current_url
                                and current_url != "about:blank"
                            ):
                                resolved_url = current_url
                                break
                            redirect_page.wait_for_timeout(500)

                        if not resolved_url:
                            resolved_url = redirect_page.url
                    finally:
                        try:
                            redirect_page.close()
                        except Exception:
                            pass

                    logger.info(f"Resolved destination URL: {resolved_url}")

                    if resolved_url and resolved_url.startswith("http"):
                        if storage_manager.is_job_applied(resolved_url):
                            logger.info(f"Already applied. Skipping: {resolved_url}")
                        else:
                            if resolved_url not in resolved_urls:
                                resolved_urls.append(resolved_url)
                                logger.info(f"Added to apply queue: {resolved_url}")

                except Exception as ex:
                    logger.error(f"Error resolving individual apply link: {ex}")

        except Exception as e:
            logger.error(f"Error reading job details for card {i}: {e}")

    page.close()
    return resolved_urls
