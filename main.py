import logging
from playwright.sync_api import sync_playwright
import config
import storage_manager
import scraper
from automation_engine import ATSAutomationEngine

# Configure dual logging (console + log file)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.ROOT_DIR / "job_application.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

def main():
    print("====================================================")
    print("  Autonomous Job Application Multi-Agent System")
    print("====================================================")
    
    # Step 1: Initialize Storage Files & Directories
    storage_manager.initialize_storage()
    
    profile = storage_manager.load_profile()
    print(f"Candidate: {profile.get('first_name')} {profile.get('last_name')}")
    print(f"Job Title Query: '{config.JOB_TITLE}'")
    print(f"Location Query:  '{config.LOCATION}'")
    print(f"Resume Path:     {config.RESUME_PATH}")
    print("====================================================\n")
    
    # Safety Check: Warn the user if they haven't set their actual resume
    if config.RESUME_PATH.exists() and config.RESUME_PATH.stat().st_size == 0:
        print("ATTENTION: resume.pdf in the workspace is an empty placeholder.")
        print("Please replace it with your real resume.pdf before applying.")
        confirm = input("Do you want to run scraping and application anyway? (y/n): ").strip().lower()
        if confirm != 'y':
            print("Exiting application so you can add your resume.")
            return

    # Step 2: Launch Playwright Context
    with sync_playwright() as p:
        logger.info("Launching visible Chromium browser instance...")
        
        browser = p.chromium.launch(
            headless=False,  # Crucial: Visible context so user can see & solve CAPTCHAs
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized"
            ]
        )
        
        # Create standard browser context with realistic viewport and user-agent
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            no_viewport=True  # Allows maximized args to override viewport shape
        )
        
        # Step 3: Scrape Job Listings
        try:
            job_urls = scraper.scrape_job_urls(context, config.JOB_TITLE, config.LOCATION)
        except Exception as e:
            logger.error(f"Error during Google Jobs scraping phase: {e}", exc_info=True)
            job_urls = []
            
        print(f"\nScraping complete. Found {len(job_urls)} potential job URLs.")
        
        if not job_urls:
            print("No new job links to process. Closing browser.")
            browser.close()
            return
            
        # Step 4: Automate Applications Loop
        success_count = 0
        failure_count = 0
        
        for idx, url in enumerate(job_urls):
            print(f"\n----------------------------------------------------")
            print(f"Applying for Job {idx + 1}/{len(job_urls)}")
            print(f"Target URL: {url}")
            print(f"----------------------------------------------------")
            
            # Double check applied jobs to prevent duplicate applies
            if storage_manager.is_job_applied(url):
                print("Job already applied. Skipping.")
                continue
                
            # Create a separate tab/page for the application attempt
            page = context.new_page()
            
            # Apply playwright-stealth to the page
            from playwright_stealth import Stealth
            stealth = Stealth()
            stealth.apply_stealth_sync(page)
            
            try:
                engine = ATSAutomationEngine(page)
                engine.apply(url)
                
                # Log success after safe submit completes successfully
                storage_manager.log_applied_job(url)
                print(f"STATUS: Successfully applied to {url}")
                success_count += 1
            except Exception as e:
                # Log failure context and keep running loop
                error_msg = str(e)
                storage_manager.log_failed_job(url, error_msg)
                print(f"STATUS: Application failed for {url}. Reason: {error_msg}")
                failure_count += 1
            finally:
                # Always close the application tab
                try:
                    page.close()
                except Exception:
                    pass
                    
        # Clean up browser
        browser.close()
        
        print("\n====================================================")
        print("  Application Run Summary")
        print("====================================================")
        print(f"Successfully Applied: {success_count}")
        print(f"Failed Applications:  {failure_count}")
        print("====================================================")

if __name__ == "__main__":
    main()
