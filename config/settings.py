# =============================================================
#  config/settings.py
#  All configurable values for the EPS Report Pipeline.
#  Fill in every field marked  ← REQUIRED  before running.
# =============================================================

# ── Portal credentials ─────────────────────────────────────
USERNAME  = ""          # ← REQUIRED: portal login username
PASSWORD  = ""          # ← REQUIRED: portal login password
LOGIN_URL = ""          # ← REQUIRED: full URL of the login page

# ── Tenant ─────────────────────────────────────────────────
TENANT_NAME = ""        # ← REQUIRED: must match data-subtenant attribute in the portal
                        #   e.g. "acme_corp"

# ── Client (used in the email report) ──────────────────────
CLIENT_NAME   = ""      # ← REQUIRED: display name shown in the email, e.g. "Acme Corp"
CLIENT_KEY    = ""      # ← REQUIRED: matches 'data_id' field in eps_average.json
ALLOCATED_EPS = "1500 EPS"  # Allocated EPS limit, e.g. "1500 EPS" or "2000 EPS"

# ── ChromeDriver ────────────────────────────────────────────
CHROMEDRIVER_PATH = "/usr/local/bin/chromedriver"
# Windows example:
# CHROMEDRIVER_PATH = "C:\\Users\\YourName\\Downloads\\chromedriver.exe"

# ── Output file paths ───────────────────────────────────────
EPS_FILE         = "/opt/eps-report-pipeline/output/eps_average.json"
GBS_FILE         = "/opt/eps-report-pipeline/output/gbs_day.json"
NULL_GBS_FILE    = "/opt/eps-report-pipeline/output/gbs_day_nulls.json"
BIFURCATION_FILE = "/opt/eps-report-pipeline/output/bifurcation.json"

# ── Email settings ──────────────────────────────────────────
SENDER_EMAIL  = ""          # ← REQUIRED: from address, e.g. 
TO_EMAILS     = [""]        # ← REQUIRED: list of To recipients
CC_EMAILS     = [""]        # ← REQUIRED: list of CC recipients (can be empty list [])

SMTP_HOST     = "smtp.office365.com"          # ← REQUIRED: SMTP server host, e.g. "smtp.gmail.com"
SMTP_PORT     = 587         # Standard TLS port (change to 465 for SSL if needed)
SMTP_USERNAME = ""          # ← REQUIRED: SMTP login username (often same as SENDER_EMAIL)
SMTP_PASSWORD = ""          # ← REQUIRED: SMTP password or app password

# ── Retry config ────────────────────────────────────────────
MAX_RETRIES = 3             # Number of times each scraper will retry on failure
