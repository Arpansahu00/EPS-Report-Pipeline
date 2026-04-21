#!/usr/bin/python3
"""
EPS Report Pipeline — Unified Script
=====================================
Combines:
  1. EPS Average + GBs/Day scraping       (was: EPS.py)
  2. Tenant bifurcation/drill-down scrape (was: tenant bifurcation.py)
  3. HTML email report generation & send  (was: email sender.py)

Flow:
  scrape_eps_and_gbs()  →  scrape_tenant_bifurcation()  →  send_report_email()
"""

import os
import json
import time
import smtplib
import datetime
import traceback
import logging
import sys

from email.message import EmailMessage
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

# Load config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '/opt/eps-report-pipeline/config'))
from settings import (
    USERNAME, PASSWORD, LOGIN_URL,
    TENANT_NAME,
    CLIENT_NAME, CLIENT_KEY, ALLOCATED_EPS,
    CHROMEDRIVER_PATH,
    EPS_FILE, GBS_FILE, NULL_GBS_FILE, BIFURCATION_FILE,
    SENDER_EMAIL, TO_EMAILS, CC_EMAILS,
    SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD,
    MAX_RETRIES,
)


# ============================================================
#  LOGGER
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), '..', 'logs', 'pipeline.log'),
            encoding='utf-8'
        ),
    ]
)
log = logging.getLogger(__name__)


# ============================================================
#  SHARED HELPERS
# ============================================================

def setup_driver():
    """Return a headless Chrome WebDriver instance."""
    from webdriver_manager.chrome import ChromeDriverManager
    
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def login(driver):
    """Open LOGIN_URL, fill credentials, and submit the form."""
    driver.get(LOGIN_URL)
    log.info("Opened login page.")
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.NAME, "j_username"))
    )
    driver.find_element(By.NAME, "j_username").send_keys(USERNAME)
    pwd = driver.find_element(By.NAME, "j_password")
    pwd.send_keys(PASSWORD)
    pwd.send_keys(Keys.RETURN)
    log.info("Login form submitted.")
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    time.sleep(3)


def open_activity_monitor(driver):
    """Click the nav dropdown then 'Activity Monitor'."""
    toggle = WebDriverWait(driver, 30).until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, 'a.dropdown-toggle[data-toggle="dropdown"]')
        )
    )
    toggle.click()
    WebDriverWait(driver, 30).until(
        EC.element_to_be_clickable((By.LINK_TEXT, "Activity Monitor"))
    ).click()
    log.info("Opened Activity Monitor.")
    time.sleep(5)


def switch_to_iframe(driver):
    """Switch focus into the Activity Monitor iframe."""
    WebDriverWait(driver, 30).until(
        EC.frame_to_be_available_and_switch_to_it((By.ID, "externalAppObjectId"))
    )
    log.info("Switched to iframe.")


def set_pagination(driver):
    """Set the data-grid page size to 10 rows (best-effort)."""
    try:
        dropdown = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//div[@role='combobox' and contains(text(), '5')]")
            )
        )
        dropdown.click()
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//li[@role='option' and @data-value='10']")
            )
        ).click()
        log.info("Pagination set to 10.")
        time.sleep(2)
    except Exception:
        log.warning("Could not set pagination — continuing with default.")


def has_null_gbs(file_path):
    """Return True if GBS_FILE is missing or contains any null GBs_Day values."""
    if not os.path.exists(file_path):
        log.warning(f"{file_path} missing — treating as invalid.")
        return True
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    nulls = [r for r in data if r.get("GBs_Day") in [None, "", "null"]]
    if nulls:
        with open(NULL_GBS_FILE, "w", encoding="utf-8") as nf:
            json.dump(nulls, nf, ensure_ascii=False, indent=2)
        log.warning(f"{len(nulls)} null GBs_Day row(s) found — saved to {NULL_GBS_FILE}.")
        return True
    return False


def _save_json(data, path, label=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"Saved {label} data → {path}  ({len(data)} rows)")


def _load_json(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Required file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
#  SECTION 1 — EPS Average + GBs/Day Scraper
# ============================================================

def scrape_eps_old(driver):
    set_pagination(driver)
    rows = WebDriverWait(driver, 20).until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, ".MuiDataGrid-virtualScrollerRenderZone > div[data-id]")
        )
    )
    scraped = []
    for row in rows:
        data_id = row.get_attribute("data-id")
        try:
            aria_div = row.find_element(By.CSS_SELECTOR, "div[aria-label]")
            aria_label = aria_div.get_attribute("aria-label")
        except Exception:
            aria_label = None
        scraped.append({"data_id": data_id, "aria_label": aria_label})
    _save_json(scraped, EPS_FILE, "EPS Average (old UI)")


def scrape_gbs_old(driver):
    set_pagination(driver)
    rows = WebDriverWait(driver, 20).until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, ".MuiDataGrid-virtualScrollerRenderZone > div[data-id]")
        )
    )
    scraped = []
    for row in rows:
        data_id = row.get_attribute("data-id")
        try:
            gbs_div = row.find_element(By.CSS_SELECTOR, 'div[data-field="events_size"] > div')
            gbs_value = gbs_div.text.strip()
        except Exception:
            soup = BeautifulSoup(row.get_attribute("outerHTML"), "html.parser")
            target = soup.find("div", {"data-field": "events_size"})
            gbs_value = target.get_text(strip=True) if target else None
        scraped.append({"data_id": data_id, "GBs_Day": gbs_value})
    _save_json(scraped, GBS_FILE, "GBs/Day (old UI)")


def scrape_eps_table(driver):
    set_pagination(driver)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    table = soup.find("table")
    scraped = []
    if table:
        for tr in table.find_all("tr")[1:]:
            tds = tr.find_all("td")
            if len(tds) >= 2:
                data_id = tds[0].get_text(strip=True)
                span = tds[1].find("span")
                if span and span.has_attr("aria-label"):
                    aria_label = span["aria-label"].strip()
                elif span:
                    aria_label = span.get_text(strip=True)
                else:
                    aria_label = None
                scraped.append({"data_id": data_id, "aria_label": aria_label})
    _save_json(scraped, EPS_FILE, "EPS Average (new UI)")


def scrape_gbs_table(driver):
    set_pagination(driver)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    table = soup.find("table")
    scraped = []
    if table:
        for tr in table.find_all("tr")[1:]:
            tds = tr.find_all("td")
            if len(tds) >= 3:
                data_id = tds[0].get_text(strip=True)
                gbs_span = tds[2].find("span")
                if gbs_span and gbs_span.has_attr("aria-label"):
                    gbs_value = gbs_span["aria-label"].strip()
                elif gbs_span:
                    gbs_value = gbs_span.get_text(strip=True)
                else:
                    gbs_value = tds[2].get_text(strip=True)
                scraped.append({"data_id": data_id, "GBs_Day": gbs_value})
    _save_json(scraped, GBS_FILE, "GBs/Day (new UI)")


def run_eps_scraper():
    """Login, detect UI, scrape EPS + GBs/Day. Returns True on success."""
    driver = setup_driver()
    try:
        login(driver)
        open_activity_monitor(driver)
        switch_to_iframe(driver)
        time.sleep(2)

        page_html = driver.page_source

        if "Total Events" in page_html:
            log.info("OLD UI detected.")
            WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(text(), 'Total Events')]")
                )
            ).click()
            WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//li[contains(text(), 'EPS Average')]")
                )
            ).click()
            scrape_eps_old(driver)

            driver.switch_to.default_content()
            switch_to_iframe(driver)
            WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(text(), 'EPS Average')]")
                )
            ).click()
            WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//li[contains(text(), 'GBs/Day')]")
                )
            ).click()
            scrape_gbs_old(driver)

        elif "Events/Day" in page_html:
            log.info("NEW UI detected.")
            WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(text(), 'Events/Day')]")
                )
            ).click()
            WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//li[contains(text(), 'Average EPS')]")
                )
            ).click()
            time.sleep(2)
            scrape_eps_table(driver)

            WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(text(), 'Average EPS')]")
                )
            ).click()
            WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//li[contains(text(), 'GBs/Day')]")
                )
            ).click()
            time.sleep(2)
            scrape_gbs_table(driver)

        else:
            log.error("Unknown UI — neither 'Total Events' nor 'Events/Day' found.")
            return False

        return True

    except Exception as e:
        log.error(f"EPS scraper error: {e}")
        traceback.print_exc()
        return False
    finally:
        driver.quit()
        log.info("EPS scraper: browser closed.")


# ============================================================
#  SECTION 2 — Tenant Bifurcation Scraper
# ============================================================

def run_bifurcation_scraper():
    """Login, drill into tenant, scrape GBs/Day table. Returns True on success."""
    driver = setup_driver()
    try:
        login(driver)
        open_activity_monitor(driver)
        switch_to_iframe(driver)

        drilldown = driver.find_element(
            By.CSS_SELECTOR,
            f'button[data-testid="tenantDrillDown"][data-subtenant="{TENANT_NAME}"]'
        )
        drilldown.click()
        log.info(f"Clicked drill-down for tenant '{TENANT_NAME}'.")
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(5)

        try:
            WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(text(), 'Events/Day')]")
                )
            ).click()
            log.info("Clicked 'Events/Day'.")
        except Exception:
            WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(text(), 'Total Events')]")
                )
            ).click()
            log.info("Clicked 'Total Events' (fallback).")

        WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//li[contains(text(), 'GBs/Day')]")
            )
        ).click()
        log.info("Selected 'GBs/Day'.")
        time.sleep(5)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        extracted = []

        mui_rows = soup.select("div.MuiDataGrid-row")
        if mui_rows:
            log.info("Bifurcation: MUI DataGrid layout.")
            for row in mui_rows:
                ds_div  = row.find("div", {"data-field": "data_source"})
                ing_div = row.find("div", {"data-field": "ingester"})
                es_div  = row.find("div", {"data-field": "events_size"})
                events_size = None
                if es_div:
                    inner = es_div.find("div")
                    if inner:
                        events_size = (
                            inner["aria-label"].strip()
                            if inner.has_attr("aria-label")
                            else inner.get_text(strip=True)
                        )
                extracted.append({
                    "DataSource":  ds_div.get_text(strip=True)  if ds_div  else None,
                    "Ingester":    ing_div.get_text(strip=True) if ing_div else None,
                    "Events Size": events_size,
                })
        else:
            log.info("Bifurcation: standard HTML table layout.")
            table = soup.find("table")
            if table:
                tbody = table.find("tbody")
                rows  = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]
                for row in rows:
                    cols = row.find_all("td")
                    if len(cols) < 3:
                        continue
                    datasource = cols[0].get_text(strip=True)
                    ingester   = cols[1].get_text(strip=True)
                    span_es    = cols[2].find("span")
                    if span_es and span_es.has_attr("aria-label"):
                        events_size = span_es["aria-label"].strip()
                    elif span_es:
                        events_size = span_es.get_text(strip=True)
                    else:
                        events_size = cols[2].get_text(strip=True)

                    avg_eps = None
                    if len(cols) >= 4:
                        span_eps = cols[3].find("span")
                        if span_eps and span_eps.has_attr("aria-label"):
                            avg_eps = span_eps["aria-label"].strip()
                        elif span_eps:
                            avg_eps = span_eps.get_text(strip=True)
                        else:
                            avg_eps = cols[3].get_text(strip=True)

                    extracted.append({
                        "DataSource":  datasource,
                        "Ingester":    ingester,
                        "Events Size": events_size,
                        "Average EPS": avg_eps,
                    })

        _save_json(extracted, BIFURCATION_FILE, "tenant bifurcation")
        return True

    except Exception as e:
        log.error(f"Bifurcation scraper error: {e}")
        traceback.print_exc()
        return False
    finally:
        driver.quit()
        log.info("Bifurcation scraper: browser closed.")


# ============================================================
#  SECTION 3 — Email Sender
# ============================================================

def send_report_email():
    """Read JSON files, calculate license status, build + send HTML email."""
    today            = datetime.date.today()
    previous_day     = today - datetime.timedelta(days=1)
    previous_day_str = previous_day.strftime("%d/%m/%Y")

    eps_data    = _load_json(EPS_FILE)
    eps_average = None
    for entry in eps_data:
        if CLIENT_KEY.lower() in entry.get("data_id", "").lower():
            eps_average = entry.get("aria_label")
            break

    if eps_average is None:
        raise ValueError(f"EPS value not found for client key: '{CLIENT_KEY}'")

    try:
        allocated_val = round(float(ALLOCATED_EPS.replace(",", "").split()[0]))
        average_val   = round(float(eps_average.replace(",", "").split()[0]))
    except (ValueError, IndexError):
        raise ValueError("EPS values must be formatted as 'number EPS', e.g. '1500 EPS'.")

    if average_val > allocated_val:
        license_status = "Breached"
        badge_color    = "#dc2626"
    else:
        license_status = "Safe"
        badge_color    = "#15803d"

    storage_data = _load_json(BIFURCATION_FILE)
    storage_rows = ""
    for entry in storage_data:
        storage_rows += f"""
        <tr>
          <td>{entry.get('DataSource', 'N/A')}</td>
          <td>{entry.get('Ingester',   'N/A')}</td>
          <td>{entry.get('Events Size','N/A')}</td>
        </tr>"""

    html_body = f"""
<html>
<head>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    body {{
      font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      margin: 0; padding: 30px 20px; color: #1e293b; line-height: 1.6; min-height: 100vh;
    }}
    .email-container {{
      background: #ffffff; max-width: 850px; margin: auto;
      border-radius: 16px; overflow: hidden;
      box-shadow: 0 25px 50px rgba(0,0,0,0.15); position: relative;
    }}
    .email-container::before {{
      content: ''; position: absolute; top: 0; left: 0; right: 0; height: 4px;
      background: linear-gradient(90deg, #3b82f6, #8b5cf6, #06b6d4);
    }}
    .header {{
      background: #2563eb; color: #ffffff;
      padding: 40px 35px; text-align: center;
    }}
    .header h1 {{ margin: 0; font-size: 24px; font-weight: 700; color: #ffffff !important; }}
    .header p  {{ margin: 10px 0 0 0; font-size: 15px; color: #ffffff !important; }}
    .content   {{ padding: 35px; }}
    .greeting  {{ font-size: 16px; margin-bottom: 25px; color: #475569; }}
    .greeting strong {{ color: #1e40af; font-weight: 600; }}
    h3 {{
      font-size: 18px; margin: 40px 0 20px 0; padding: 15px 20px;
      background: linear-gradient(135deg, #f8fafc, #f1f5f9);
      border-left: 6px solid #3b82f6; border-radius: 8px; color: #1e293b; font-weight: 600;
    }}
    h3:first-of-type {{ margin-top: 20px; }}
    table {{
      width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 14px;
      border-radius: 12px; overflow: hidden;
      box-shadow: 0 4px 12px rgba(0,0,0,0.08); border: 1px solid #e2e8f0;
    }}
    th, td {{ padding: 16px 20px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
    th {{
      background: linear-gradient(135deg, #f8fafc, #f1f5f9);
      font-weight: 600; color: #1e40af; text-transform: uppercase;
      font-size: 12px; letter-spacing: 0.5px;
    }}
    td {{ background: #ffffff; font-weight: 500; }}
    tr:hover td {{ background: #f8fafc; }}
    tr:last-child td {{ border-bottom: none; }}
    .metric-value {{ font-weight: 600; color: #1e40af; }}
    .badge {{
      padding: 8px 16px; border-radius: 8px; font-weight: 600;
      font-size: 12px; display: inline-block; text-transform: uppercase;
    }}
    .note {{
      font-size: 14px; margin-top: 25px;
      background: linear-gradient(135deg, #fffbeb, #fef3c7);
      padding: 18px 20px; border-left: 5px solid #f59e0b; border-radius: 10px;
    }}
    .divider {{
      height: 2px; background: linear-gradient(90deg, transparent, #e2e8f0, transparent);
      margin: 30px 0; border: none;
    }}
    .footer {{
      background: linear-gradient(135deg, #f8fafc, #f1f5f9);
      padding: 25px 35px; font-size: 13px; color: #64748b;
      text-align: center; border-top: 1px solid #e2e8f0;
    }}
  </style>
</head>
<body>
  <div class="email-container">
    <div class="header">
      <h1>EPS &amp; Data Storage Daily Report</h1>
      <p>Generated for <strong>{CLIENT_NAME}</strong> on <strong>{previous_day_str}</strong></p>
    </div>
    <div class="content">
      <div class="greeting">
        <p>Hello <strong>{CLIENT_NAME}</strong> team,</p>
        <p>Please find the EPS utilisation and storage report for <strong>{previous_day_str}</strong>.</p>
      </div>

      <h3>📊 EPS Utilisation Report</h3>
      <table>
        <tr><th>Report Date</th>   <td class="metric-value">{previous_day_str}</td></tr>
        <tr><th>Client Name</th>   <td class="metric-value">{CLIENT_NAME}</td></tr>
        <tr><th>Allocated EPS</th> <td class="metric-value">{ALLOCATED_EPS}</td></tr>
        <tr><th>Average EPS</th>   <td class="metric-value">{average_val} EPS</td></tr>
        <tr>
          <th>License Status</th>
          <td>
            <span class="badge" style="background:{badge_color}; color:white;">
              {license_status}
            </span>
          </td>
        </tr>
      </table>
      <div class="note">
        ⚠️ This report shows utilisation for the specific date to track continuous EPS changes.
        The final report at month-end may differ.
      </div>

      <hr class="divider">

      <h3>💾 Data Source Storage Report</h3>
      <p style="margin:0; font-weight:500; color:#0c4a6e;">
        Top storage usage details for data sources and their respective ingesters.
      </p>
      <table>
        <tr>
          <th>Data Source</th>
          <th>Ingester</th>
          <th>Event Size (GB)</th>
        </tr>
        {storage_rows}
      </table>

      <hr class="divider">

      <div style="margin-top:30px; padding:20px; background:linear-gradient(135deg,#f0fdf4,#dcfce7);
                  border-radius:12px; border:1px solid #22c55e;">
        <p style="margin:0; color:#166534; font-weight:500;">
          💬 <strong>Need Assistance?</strong><br>
          Feel free to reach out if you have any queries or require additional insights.
        </p>
      </div>

      <div style="margin-top:25px;">
        <p style="margin:0; color:#475569;">Best regards,</p>
        <div style="font-weight:700; color:#1e40af; font-size:16px; margin-top:4px;">SOC Team</div>
        <div style="color:#64748b; font-size:14px; margin-top:2px;">
          Labs – A Cybersecurity Limited
        </div>
      </div>
    </div>
    <div class="footer">
      <div style="font-weight:500; margin-bottom:8px;">🤖 This is an automated email</div>
      <div style="font-size:12px; opacity:0.8;">
        Generated on {previous_day_str} • Labs 
      </div>
    </div>
  </div>
</body>
</html>"""

    subject = f"{CLIENT_NAME} - EPS & Storage Daily Report - {previous_day_str}"
    msg = EmailMessage()
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = ", ".join(TO_EMAILS)
    msg["Cc"]      = ", ".join(CC_EMAILS)
    msg["Subject"] = subject
    msg.set_content("This is an HTML email. Please view it in an HTML-compatible client.")
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg, from_addr=SENDER_EMAIL, to_addrs=TO_EMAILS + CC_EMAILS)

    log.info(f"Email sent successfully to '{CLIENT_NAME}' for {previous_day_str}.")


# ============================================================
#  ENTRY POINT
# ============================================================

def main():
    # ── Step 1: EPS Average + GBs/Day ──────────────────────────────────
    log.info("=" * 60)
    log.info("STEP 1 — EPS Average + GBs/Day scraping")
    log.info("=" * 60)
    eps_success = False
    for attempt in range(1, MAX_RETRIES + 1):
        log.info(f"EPS scraper attempt {attempt}/{MAX_RETRIES}")
        if run_eps_scraper():
            if has_null_gbs(GBS_FILE):
                log.warning("Null GBs_Day values detected — retrying.")
                time.sleep(3)
            else:
                log.info("EPS + GBs/Day collected successfully.")
                eps_success = True
                break
        else:
            log.warning(f"EPS scraper failed on attempt {attempt}.")
            time.sleep(3)

    if not eps_success:
        log.error("EPS scraper failed after max retries. Aborting.")
        sys.exit(1)

    # ── Step 2: Tenant Bifurcation ──────────────────────────────────────
    log.info("=" * 60)
    log.info("STEP 2 — Tenant bifurcation scraping")
    log.info("=" * 60)
    bif_success = False
    for attempt in range(1, MAX_RETRIES + 1):
        log.info(f"Bifurcation scraper attempt {attempt}/{MAX_RETRIES}")
        if run_bifurcation_scraper():
            log.info("Bifurcation data collected successfully.")
            bif_success = True
            break
        else:
            log.warning(f"Bifurcation scraper failed on attempt {attempt}.")
            time.sleep(3)

    if not bif_success:
        log.error("Bifurcation scraper failed after max retries. Aborting.")
        sys.exit(1)

    # ── Step 3: Send Email ──────────────────────────────────────────────
    log.info("=" * 60)
    log.info("STEP 3 — Sending email report")
    log.info("=" * 60)
    try:
        send_report_email()
        log.info("✅ Pipeline completed successfully.")
    except Exception as e:
        log.error(f"Email sending failed: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
