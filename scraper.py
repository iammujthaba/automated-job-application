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
    Navigates to Google Jobs, iterates through job cards, clicks them,
    and resolves the actual application target URLs by intercepting redirect tabs.
    """
    logger.info(f"Starting Google Jobs scrape for '{job_title}' in '{location}'...")
    
    page = context.new_page()
    stealth = Stealth()
    stealth.apply_stealth_sync(page)
    
    url = build_google_jobs_url(job_title, location)
    logger.info(f"Navigating to Google Jobs: {url}")
    
    try:
        page.goto(url)
        # Implement a CAPTCHA Pause if Google abuse/sorry page is hit
        if "google_abuse" in page.url or "sorry/index" in page.url:
            print("\n\033[1mWARNING: Google CAPTCHA detected! Please manually solve the CAPTCHA in the browser window.\033[0m\n")
            input("Press Enter in the terminal once you have solved the CAPTCHA to resume...")
        
        # Wait for the job cards to load using a robust listitem selector
        page.get_by_role("listitem").first.wait_for(timeout=15000)
    except Exception as e:
        logger.error(f"Failed to load Google Jobs widget: {e}")
        page.close()
        return []

    # Let the page settle
    page.wait_for_timeout(2000)
    
    # Locate all job cards (typically list items under the main list)
    cards_locator = page.get_by_role("listitem")
    
    # We can perform a scroll to load more jobs if needed
    try:
        # The left column is usually scrollable. Let's find it.
        # Find the container enclosing the job list and scroll it.
        list_container = page.get_by_role("listitem").first.locator("..")
        for _ in range(2):
            list_container.evaluate("element => element.scrollTop = element.scrollHeight")
            page.wait_for_timeout(1000)
    except Exception as e:
        logger.warning(f"Could not scroll to load more jobs: {e}")

    # Re-evaluate cards after scrolling
    cards = cards_locator.all()
    num_cards = len(cards)
    logger.info(f"Found {num_cards} job cards on Google Jobs panel.")
    
    resolved_urls = []
    
    for i in range(min(num_cards, max_jobs)):
        card = cards[i]
        logger.info(f"Processing job card {i + 1}/{min(num_cards, max_jobs)}...")
        
        try:
            # Click the card to load its details on the right panel
            card.scroll_into_view_if_needed()
            card.click()
            page.wait_for_timeout(1500) # wait for right details pane to update
            
            # Find all links on the right panel containing text "Apply"
            # We target the detail section on the right, which typically has class/role details.
            # But the simplest, most resilient locator is locating 'a' tags with text 'Apply'
            apply_links = page.locator("a:has-text('Apply')").all()
            
            for apply_link in apply_links:
                try:
                    text = apply_link.inner_text().strip()
                    # Skip if it doesn't mention "Apply"
                    if "Apply" not in text:
                        continue
                    
                    logger.info(f"Found apply button: '{text}'. Clicking to resolve redirect...")
                    
                    # Capture the new page/tab that opens when we click the Apply button
                    with context.expect_page(timeout=15000) as new_page_info:
                        apply_link.click()
                    
                    new_page = new_page_info.value
                    
                    # Wait for redirects to settle (resolve from google.com/url to company/ATS site)
                    resolved_url = None
                    start_time = time.time()
                    while time.time() - start_time < 12:
                        current_url = new_page.url
                        # Check if we have moved away from Google's redirect domain
                        if current_url and "google.com/url" not in current_url and current_url != "about:blank":
                            resolved_url = current_url
                            break
                        new_page.wait_for_timeout(500)
                    
                    if not resolved_url:
                        resolved_url = new_page.url
                        
                    logger.info(f"Resolved destination URL: {resolved_url}")
                    
                    # Close the tab immediately
                    try:
                        new_page.close()
                    except Exception:
                        pass
                    
                    if resolved_url and resolved_url.startswith("http"):
                        # Check if we've already applied or logged this URL
                        if storage_manager.is_job_applied(resolved_url):
                            logger.info(f"Job already applied. Skipping: {resolved_url}")
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
