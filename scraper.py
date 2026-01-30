import os
import random
import time
import json
import io
import logging
import re
import pandas as pd
import undetected_chromedriver as uc
import google.auth
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import UnexpectedAlertPresentException, NoAlertPresentException
from collections import defaultdict
from google.cloud import storage
from datetime import date, timedelta

# -------------------- CONFIG --------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "sicoescan")
GCS_FOLDER = os.environ.get("GCS_FOLDER", "forms")

# Date Logic: strictly "Yesterday" to "Yesterday" (One day only)
today = date.today()
yesterday = today - timedelta(days=1)
# You can override these with env vars if needed
date_from = os.environ.get("DATE_FROM", yesterday.strftime("%d/%m/%Y"))
date_to = os.environ.get("DATE_TO", yesterday.strftime("%d/%m/%Y"))

form_counter = defaultdict(int)
saved_files_count = 0

# -------------------- HELPERS --------------------
def get_gcs_client():
  try:
    # Try native GCP Auth first (Cloud Run default identity)
    credentials, project = google.auth.default()
    logger.info("✅ Authenticated with GCP Default Identity")
    return storage.Client(credentials=credentials, project=project)
  except Exception:
    # Fallback to JSON file if locally testing
    json_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "./google-credentials.json")
    if os.path.exists(json_path):
      from google.oauth2 import service_account
      logger.info("✅ Authenticated with JSON Key")
      return storage.Client.from_service_account_json(json_path)
    
  logger.error("❌ Could not authenticate with GCS.")
  return None

def upload_file_to_gcs(client, bucket_name, blob_name, content):
  try:
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    if blob.exists(): return False
    blob.upload_from_string(content, content_type="text/html")
    logger.info(f"☁ Uploaded {blob_name}")
    return True
  except Exception as e:
    logger.error(f"❌ Upload failed: {e}")
    return False

def extract_cuce(texto):
  if not texto: return None
  inicio = texto.find("CUCE")
  if inicio == -1: return None
  return texto[inicio:].split()[0].strip()

def get_network_response(driver, target_url_part="verFormulario.php", timeout=15):
  end_time = time.time() + timeout
  while time.time() < end_time:
    try:
      # REVISAR ALERTA PRIMERO
      alert = driver.switch_to.alert
      text = alert.text
      logger.warning(f"🛑 Alerta detectada: {text}")
      alert.accept()
      return "CAPTCHA_ERROR"
    except NoAlertPresentException:
      pass
    try:
      logs = driver.get_log("performance")
      for entry in logs:
        message = json.loads(entry["message"])["message"]
        if message["method"] == "Network.responseReceived":
          if target_url_part in message["params"]["response"]["url"]:
            req_id = message["params"]["requestId"]
            body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": req_id})
            return body["body"]
    except Exception as e:
      logger.error(f"❌ Error leyendo logs de performance: {e}")
      break # Si falla la comunicación con el driver, salimos del loop
    time.sleep(1)
  return None

def extract_cuce_flexible(html_content):
  # Busca el patrón: XX-XXXX-XX-XXXXXXX-X-X (donde X son números o letras)
  # Explicación: \w+ (caracteres) seguido de guiones en la estructura correcta
  pattern = r'\w+-\w+-\w+-\w+-\w+-\w+'
  
  matches = re.findall(pattern, html_content)
    
  for match in matches:
    # El CUCE real suele tener entre 15 y 30 caracteres
    # Esto filtra ruidos o IDs de CSS que podrían tener guiones
    if 15 <= len(match) <= 35:
      return match
          
  return None

def human_click(driver, element):
  try:
    driver.execute_script(
      "arguments[0].scrollIntoView({behavior: 'instant', block: 'center', inline: 'center'});", 
      element
    )
    time.sleep(random.uniform(1.0, 1.5))

    actions = ActionChains(driver)
    actions.move_to_element_with_offset(element, random.randint(-5, 5), random.randint(-5, 5))
    actions.pause(random.uniform(0.3, 0.7))
    actions.click()
    actions.perform()
    logger.info("🖱️ Clic humano exitoso.")
    return True
  except Exception as e:
    logger.warning(f"⚠️ ActionChains falló, usando fallback JS: {e}")
    try:
      driver.execute_script("arguments[0].click();", element)
      return True
    except:
      return False
        
# -------------------- MAIN --------------------
if __name__ == "__main__":
  logger.info(f"🚀 Job Started. Target Date: {date_from}")
  
  gcs_client = get_gcs_client()
  if not gcs_client: exit(1)

  options = uc.ChromeOptions()
  options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
  #options.add_argument('--headless')
  options.add_argument("--no-sandbox")
  options.add_argument("--disable-dev-shm-usage")
  options.add_argument("--start-maximized")
  options.add_argument("--window-size=1920,1080")
  #options.add_argument('--proxy-server=http://158.172.153.36:999')
  options.add_argument("--remote-debugging-port=9222")
  options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
  options.binary_location = "/usr/bin/google-chrome"

  try:
    driver = uc.Chrome(options=options, version_main=144)
  except Exception as e:
    logger.error(f"Fallo crítico al iniciar Chrome: {e}")
    exit(1)

  try:
    logger.info("Navigating to SICOES...")
    driver.get("https://www.sicoes.gob.bo/portal/index.php")
    
    # 1. HANDLE POPUP
    time.sleep(random.uniform(4.5, 6.5)) # Wait for page + popup
    try:
      popup = driver.find_element(By.ID, "modalComunicados")
      if popup.is_displayed():
        driver.execute_script("arguments[0].click();", popup.find_element(By.CLASS_NAME, "close"))
        time.sleep(random.uniform(1.5, 2.5))
    except: pass

    # 2. NAVIGATE TO SEARCH
    wait = WebDriverWait(driver, 20)
    convocatorias = wait.until(EC.element_to_be_clickable((By.XPATH, "//h4[contains(text(), 'Convocatorias')]")))
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", convocatorias)
    time.sleep(random.uniform(0.5, 1.5))
    driver.execute_script("arguments[0].click();", convocatorias)
    time.sleep(random.uniform(2.5, 4.5))

    # 3. FILL DATE (YESTERDAY)
    driver.find_element(By.NAME, "publicacionDesde").clear()
    driver.find_element(By.NAME, "publicacionDesde").send_keys(date_from)
    driver.find_element(By.NAME, "publicacionHasta").clear()
    driver.find_element(By.NAME, "publicacionHasta").send_keys(date_to)

    # Select "Todos" radio button
    radios = driver.find_elements(By.CLASS_NAME, "iradio_minimal-blue")
    if len(radios) > 1: radios[1].click()
    
    # --- Fix for Navbar Interception ---
    search_btn = driver.find_element(By.CLASS_NAME, "busquedaForm")
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", search_btn)
    time.sleep(random.uniform(0.5, 1.5))
    driver.execute_script("arguments[0].click();", search_btn)
    # -----------------------------------
    
    # Wait for search results
    time.sleep(random.uniform(8.5, 12.5))

    # 4. SCRAPE LOOP
    while True:
      try:
        forms = driver.find_elements(By.XPATH, "//a[contains(text(), 'FORM')]")
      except:
        break
      
      logger.info(f"Found {len(forms)} forms on page.")
      time.sleep(random.uniform(1.5, 2.5))

      for i in range(len(forms)):
        if (i + 1) % 5 == 0:
          extra_rest = random.uniform(4.5, 10.5)
          logger.info(f"☕ Tomando un descanso humano de {extra_rest:.2f}s...")
          time.sleep(extra_rest)

        current_forms = driver.find_elements(By.XPATH, "//a[contains(text(), 'FORM')]")

        if i >= len(current_forms): break
        form_btn = current_forms[i]

        logger.info(f"Processing Form {i+1}...")
        driver.get_log("performance")

        if not human_click(driver, form_btn): continue

        try:
          response_body = get_network_response(driver, "verFormulario.php", timeout=15)

          if response_body == "CAPTCHA_ERROR":
            logger.error(f"❌ Saltando Form {i+1} debido a bloqueo por Captcha.")
            continue # Salta al siguiente formulario en la lista
          
          if response_body:
            raw_html = json.loads(response_body).get("data", "")
            
            try:
              dataframes = pd.read_html(io.StringIO(raw_html))
            except ValueError:
              dataframes = []

            form_type = "UNKNOWN"
            cuce = None

            if len(dataframes) > 0 and not dataframes[0].empty:
              try:
                form_type = str(dataframes[0].iloc[0, 0]).replace(" ", "").strip()
              except: pass

            cuce = extract_cuce_flexible(raw_html)

            if not cuce:
              # Si no lo halló en el texto crudo, intentamos en el texto limpio de los dataframes
              all_text = " ".join([df.to_string() for df in dataframes])
              cuce = extract_cuce_flexible(all_text)

            if not cuce: cuce = time.strftime("%Y%m%d%H%M%S")
            cuce = str(cuce).replace("/", "-").strip()

            # Save
            form_counter[(cuce, form_type)] += 1
            idx = form_counter[(cuce, form_type)]
            filename = f"{cuce}_{form_type}_{idx}.html"
            blob_name = f"{GCS_FOLDER}/{filename}"

            if upload_file_to_gcs(gcs_client, GCS_BUCKET_NAME, blob_name, raw_html):
              saved_files_count += 1
              logger.info(f"✅ Saved: {filename}")
          
          else:
            logger.warning("Timed out waiting for data.")

        except Exception as e:
          logger.error(f"Error form {i+1}: {e}")

        # Close Modal
        try:
          actions = ActionChains(driver)
          actions.send_keys(Keys.ESCAPE).perform()
          time.sleep(random.uniform(0.8, 1.5))
        except UnexpectedAlertPresentException:
          try: driver.switch_to.alert.accept()
          except: pass
        except Exception as e:
          logger.warning(f"No se pudo cerrar el modal con ESCAPE: {e}")

      # Pagination
      try:
        next_btn = driver.find_element(By.XPATH, "//a[contains(text(), 'Siguiente')]")
        parent = next_btn.find_element(By.XPATH, "./..")
        if "disabled" in parent.get_attribute("class"): break
        
        driver.execute_script("arguments[0].click();", next_btn)
        time.sleep(random.uniform(3.5, 5.5))
      except:
        break

  finally:
    driver.quit()
    logger.info(f"Job finished. Total Uploaded: {saved_files_count}")