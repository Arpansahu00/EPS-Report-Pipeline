# 📊 EPS Report Pipeline

An automated daily reporting pipeline for SOC teams that:

1. **Scrapes** EPS Average + GBs/Day data from the Activity Monitor portal (supports both old MUI DataGrid UI and new HTML table UI)
2. **Drills down** into a specific tenant to collect per-data-source storage bifurcation data
3. **Sends** a styled HTML email report with EPS utilisation and licence status to the client

---

## 📁 Project Structure

```
eps-report-pipeline/
├── src/
│   └── eps_report_pipeline.py   # Main unified script
├── config/
│   ├── settings.py              # Your real config (git-ignored)
│   └── settings.example.py     # Template — safe to commit
├── logs/
│   └── pipeline.log             # Auto-generated run logs
├── output/                      # Scraped JSON files land here (git-ignored)
├── requirements.txt
├── .gitignore
└── README.md
```

---

## ⚙️ Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.8 + |
| Google Chrome | Latest stable |
| ChromeDriver | Must match your Chrome version |

---

## 🚀 Setup

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/eps-report-pipeline.git
cd eps-report-pipeline
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure settings

```bash
cp config/settings.example.py config/settings.py
```

Now open `config/settings.py` and fill in **all required fields**:

| Field | Description |
|---|---|
| `USERNAME` / `PASSWORD` | Portal login credentials |
| `LOGIN_URL` | Full URL of the login page |
| `TENANT_NAME` | Matches `data-subtenant` attribute in the portal |
| `CLIENT_NAME` | Display name shown in the email |
| `CLIENT_KEY` | Matches `data_id` field in scraped JSON |
| `ALLOCATED_EPS` | Licence limit, e.g. `"1500 EPS"` |
| `CHROMEDRIVER_PATH` | Path to your chromedriver binary |
| `SENDER_EMAIL` / `TO_EMAILS` / `CC_EMAILS` | Email addresses |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` | SMTP server settings |

### 5. Install ChromeDriver

**Linux:**
```bash
# Check your Chrome version first
google-chrome --version

# Download matching ChromeDriver from:
# https://googlechromelabs.github.io/chrome-for-testing/
sudo mv chromedriver /usr/local/bin/
sudo chmod +x /usr/local/bin/chromedriver
```

**Windows:**
Download ChromeDriver from https://googlechromelabs.github.io/chrome-for-testing/  
Update `CHROMEDRIVER_PATH` in `settings.py` to the `.exe` path.

---

## ▶️ Running the Pipeline

```bash
python src/eps_report_pipeline.py
```

The script runs 3 steps sequentially:

```
STEP 1 → Scrape EPS Average + GBs/Day  (retries up to MAX_RETRIES times if nulls found)
STEP 2 → Scrape tenant bifurcation data (retries up to MAX_RETRIES times on failure)
STEP 3 → Send HTML email report
```

Logs are printed to the console **and** saved to `logs/pipeline.log`.

---

## ⏰ Scheduling (Cron — Linux)

To run the pipeline daily at 8:00 AM:

```bash
crontab -e
```

Add this line (adjust paths):

```
0 8 * * * /path/to/venv/bin/python /path/to/eps-report-pipeline/src/eps_report_pipeline.py
```

---

## 🔄 How It Works

### UI Detection
The portal has two possible UI layouts. The script auto-detects which one is active:

| UI Type | Detection | Scraping method |
|---|---|---|
| Old UI | `"Total Events"` in page HTML | MUI DataGrid CSS selectors |
| New UI | `"Events/Day"` in page HTML | Standard `<table>` via BeautifulSoup |

### Null Retry Logic
After scraping GBs/Day data, if any row has a `null`/empty value, the entire scrape is retried (up to `MAX_RETRIES` times). Null rows are saved to a separate file for inspection.

### Licence Status
| Condition | Status | Badge colour |
|---|---|---|
| Average EPS ≤ Allocated EPS | ✅ Safe | Green |
| Average EPS > Allocated EPS | ❌ Breached | Red |

---

## 🔒 Security Notes

- `config/settings.py` is **git-ignored** — it will never be committed
- Never hardcode credentials in `src/eps_report_pipeline.py`
- For Gmail SMTP, use an **App Password** (not your main password):  
  Google Account → Security → 2-Step Verification → App passwords

---

## 🐛 Troubleshooting

| Problem | Fix |
|---|---|
| `SessionNotCreatedException` | ChromeDriver version doesn't match Chrome — re-download |
| `TimeoutException` on login | Check `LOGIN_URL`, username/password field names |
| EPS value not found | Check `CLIENT_KEY` matches `data_id` in scraped JSON |
| SMTP auth error | Use App Password for Gmail; check host/port |
| All GBs_Day are null | Portal may be slow — increase `time.sleep()` values |

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🏢 Maintained By

**SOC Team — Labs**  
# eps-report-pipeline
