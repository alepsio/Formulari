import os
from dotenv import load_dotenv
from pathlib import Path
import requests_pkcs12

# Carica variabili da .env
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
P12_FILE = str(BASE_DIR / os.getenv("P12_FILE"))
P12_PASSWORD = os.getenv("P12_PASSWORD")
API_BASE = os.getenv("API_BASE")

def vidima_formulario(numero=1, tipo="Ordinario"):
    url = f"{API_BASE}/vidimazione-formulari"
    payload = {
        "numeroFormulari": numero,
        "tipoFormulario": tipo  # "Ordinario" o "Semplificato"
    }

    print("📤 Invio richiesta di vidimazione...")
    response = requests_pkcs12.post(
        url,
        json=payload,
        pkcs12_filename=P12_FILE,
        pkcs12_password=P12_PASSWORD
    )

    if response.status_code == 200:
        data = response.json()
        print("\n✅ Vidimazione riuscita!\n")
        print(f"🆔 ID Vidimazione: {data['idVidimazione']}")
        print(f"📄 Numero iniziale: {data['numeroIniziale']}")
        print(f"📄 Numero finale:   {data['numeroFinale']}")
        print(f"📅 Data:            {data['dataVidimazione']}")
        return data
    else:
        print("❌ Errore:", response.status_code)
        print(response.text)
        return None

if __name__ == "__main__":
    # puoi cambiare tipoFormulario o quantità
    vidima_formulario(numero=1, tipo="Ordinario")
