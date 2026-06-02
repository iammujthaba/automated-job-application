from pathlib import Path

# Job search parameters (top-level for easy editing)
JOB_TITLE = "software developer"
LOCATION = "Calicut"

# Root directory of the application
ROOT_DIR = Path(__file__).parent.resolve()

# Dynamic Paths
RESUME_PATH = ROOT_DIR / "resume.pdf"
PROFILE_PATH = ROOT_DIR / "profile.json"
APPLIED_JOBS_PATH = ROOT_DIR / "applied_jobs.txt"
FAILED_JOBS_PATH = ROOT_DIR / "failed_jobs.txt"
CREDENTIALS_LOG_PATH = ROOT_DIR / "credentials.json"

# ---------------------------------------------------------------------------
# Unsupported / dead-end domains blocklist
# Add any hostname here (without 'www.') to prevent the engine from attempting
# form-filling on sites that are not real ATS job portals (e.g. social media,
# classified-ad sites, news/alert aggregators, or careers-listing-only pages).
# Subdomain matching is automatic: adding "facebook.com" also blocks "www.facebook.com".
# ---------------------------------------------------------------------------
UNSUPPORTED_DOMAINS = [
    # Social media — not application portals
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "whatsapp.com",
    "wa.me",
    "youtube.com",

    # LinkedIn — has its own Easy Apply flow; not handled yet
    "linkedin.com",

    # Classified / aggregator sites (India)
    "olx.in",
    "olx.com",
    "quikr.com",
    "naukri.com",       # Requires account login — not handled yet

    # Job alert / news aggregators (no application form)
    "freejobalert.com",
    "sarkariresult.com",
    "indiaresults.com",

    # Careers listing-only pages (no inline application form)
    "logiology.com",

    # URL shorteners / redirect hops (scraper should have resolved these already)
    "t.co",
    "bit.ly",
    "tly.fyi",
]
