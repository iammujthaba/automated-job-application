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
