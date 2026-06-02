import json
import logging
from datetime import datetime
import config

logger = logging.getLogger(__name__)

BASELINE_PROFILE = {
  "first_name": "Mujthaba",
  "last_name": "Mk",
  "email": "iammujthaba@gmail.com",
  "phone": "+917025962175",
  "current_city": "Malappuram",
  "current_state": "Kerala",
  "linkedin": "www.linkedin.com/in/mujthabamk2",
  "github": "https://github.com/iammujthaba",
  "portfolio": "https://iammujthaba.github.io/portfolio/index.html",
  "skills": ["Python", "GIT", "SQL"],
  "experience_years": "FRESHER / less than 1 year",
  "highest_degree": "BSc in computer science",
  "notice_period": "IMMEDIATE"
}

def initialize_storage():
    """Initializes profile.json, applied_jobs.txt, failed_jobs.txt and credentials.json if they don't exist."""
    # Ensure root/parent folders exist
    config.ROOT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize profile.json
    if not config.PROFILE_PATH.exists():
        with open(config.PROFILE_PATH, "w", encoding="utf-8") as f:
            json.dump(BASELINE_PROFILE, f, indent=2)
        logger.info(f"Initialized new profile.json at {config.PROFILE_PATH}")
        
    # Check resume.pdf presence
    if not config.RESUME_PATH.exists():
        print(f"\nWARNING: resume.pdf was not found at: {config.RESUME_PATH}")
        print("Creating a empty dummy resume.pdf. Please overwrite it with your actual resume before applying!\n")
        config.RESUME_PATH.touch()

    # Initialize log files
    if not config.APPLIED_JOBS_PATH.exists():
        config.APPLIED_JOBS_PATH.touch()
    if not config.FAILED_JOBS_PATH.exists():
        config.FAILED_JOBS_PATH.touch()
    if not config.CREDENTIALS_LOG_PATH.exists():
        with open(config.CREDENTIALS_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)

def load_profile() -> dict:
    """Loads the profile JSON as a dictionary."""
    if not config.PROFILE_PATH.exists():
        initialize_storage()
    with open(config.PROFILE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_profile(profile: dict):
    """Saves the profile dictionary to profile.json."""
    with open(config.PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)

def update_profile_field(key: str, value):
    """Updates a single field in profile.json dynamically (Learning Loop)."""
    profile = load_profile()
    profile[key] = value
    save_profile(profile)
    logger.info(f"Learned and saved new key '{key}' to profile.")

def is_job_applied(url: str) -> bool:
    """Checks if a job URL has already been successfully applied to."""
    if not config.APPLIED_JOBS_PATH.exists():
        return False
    with open(config.APPLIED_JOBS_PATH, "r", encoding="utf-8") as f:
        applied_urls = [line.strip() for line in f if line.strip()]
    return url in applied_urls

def log_applied_job(url: str):
    """Logs a successfully completed job URL to applied_jobs.txt."""
    with open(config.APPLIED_JOBS_PATH, "a", encoding="utf-8") as f:
        f.write(f"{url}\n")
    logger.info(f"Logged successful application: {url}")

def log_failed_job(url: str, reason: str):
    """Logs a failed job URL and the failure reason to failed_jobs.txt."""
    timestamp = datetime.now().isoformat()
    with open(config.FAILED_JOBS_PATH, "a", encoding="utf-8") as f:
        # Normalize newlines inside reason to single-line format
        clean_reason = str(reason).replace('\n', ' ').replace('\r', '')
        f.write(f"{timestamp} | {url} | {clean_reason}\n")
    logger.error(f"Logged failed application: {url} | Reason: {clean_reason}")

def log_credentials(portal_url: str, email: str, password: str):
    """Logs auto-generated credentials for an ATS portal."""
    if not config.CREDENTIALS_LOG_PATH.exists():
        credentials = []
    else:
        try:
            with open(config.CREDENTIALS_LOG_PATH, "r", encoding="utf-8") as f:
                credentials = json.load(f)
        except Exception:
            credentials = []

    credentials.append({
        "portal_url": portal_url,
        "email": email,
        "password": password,
        "timestamp": datetime.now().isoformat()
    })
    
    with open(config.CREDENTIALS_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(credentials, f, indent=2)
    logger.info(f"Saved new account credentials for {portal_url}")
