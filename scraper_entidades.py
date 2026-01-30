import os
import time
import json
import io
import logging
import pandas as pd
from seleniumwire import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options

from google.cloud import firestore
from google.oauth2 import service_account
import os
import datetime

# Load service account credentials from file
cred = service_account.Credentials.from_service_account_file('./firebase-credentials.json')

db = firestore.Client(project="empyrean-cubist-467813-u9", credentials=cred)

# -------------------- DRIVER SETUP --------------------
#chrome_options = Options()
#chrome_options.add_argument("--headless=new")  # modern headless
#chrome_options.add_argument("--no-sandbox")
#chrome_options.add_argument("--disable-dev-shm-usage")
#chrome_options.add_argument("--disable-gpu")
#chrome_options.add_argument("window-size=1920,1080")

service = Service()
driver = webdriver.Chrome(service=service)
#driver = webdriver.Chrome(service=service, options=chrome_options)


# -------------------- MAIN --------------------
entidades_count = 0

driver.get("https://www.sicoes.gob.bo/portal/index.php")
time.sleep(2)

actions = ActionChains(driver)
actions.send_keys(Keys.TAB + Keys.ENTER).perform()

time.sleep(1)

clasificadores = driver.find_element(By.XPATH, "//span[contains(text(), 'Clasificadores')]")
clasificadores.click()

entidades_button = WebDriverWait(driver, 10).until(
    EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Institucional')]"))
)
driver.execute_script("arguments[0].scrollIntoView(true);", entidades_button)
driver.execute_script("arguments[0].click();", entidades_button)
time.sleep(2)

entidad_table = driver.find_element(By.ID, 'tablaSimple')

siguiente_button = driver.find_element(By.XPATH, "//a[contains(text(), 'Siguiente')]")

while (siguiente_button):
    time.sleep(2)
    rows = entidad_table.find_elements(By.TAG_NAME, 'tr')
    for row in rows[1:]:
        cols = row.find_elements(By.TAG_NAME, 'td')
        codigo = cols[0].text.replace('-', ' - ')
        entidad_data = {
            'nombre': cols[1].text,
            'departamento': cols[2].text,
            'tipo': cols[3].text,
            'max_autoridad': cols[4].text,
            'max_autoridad_cargo': cols[5].text,
            'direccion': cols[6].text,
            'telefono': cols[7].text
        }
        
        db.collection('entidades').document(codigo).set(entidad_data, merge=True)
        print(f"Actualizado entidad {codigo}: {entidad_data['nombre']}")
        entidades_count += 1

    siguiente_button = driver.find_element(By.XPATH, "//a[contains(text(), 'Siguiente')]")
    if 'disabled' in siguiente_button.get_attribute('class'):
        break
    driver.execute_script("arguments[0].scrollIntoView(true);", siguiente_button)
    driver.execute_script("arguments[0].click();", siguiente_button)
    time.sleep(2)
print(f"Total entidades actualizadas: {entidades_count}")
driver.quit()
