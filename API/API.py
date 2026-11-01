import os
import json
from fastapi import FastAPI, HTTPException
from typing import List, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timezone

# Importa la pipeline reale dal tuo scraper
from cinema_scraper.pipeline import run_pipeline

app = FastAPI(
    title="Local Cinema API",
    description="API locale per la consultazione dei dati cinematografici da file JSON.",
    version="1.0.0"
)

# Percorso dinamico alla cartella output situata alla radice (WEBSCRATCHING/output)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "output")

def load_all_json_data() -> List[dict]:
    """Legge tutti i file JSON presenti nella cartella output."""
    data_list = []
    if not os.path.exists(DATA_DIR):
        return data_list
    
    for filename in os.listdir(DATA_DIR):
        if filename.endswith(".json"):
            file_path = os.path.join(DATA_DIR, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = json.load(f)
                    data_list.append(content)
            except Exception as e:
                print(f"Errore nella lettura del file {filename}: {e}")
                
    return data_list

@app.get("/")
def read_root():
    """Endpoint di benvenuto."""
    return {"message": "API Locale Cinema attiva. Usa /data, /provinces o /province/{nome}[?date=YYYY-MM-DD] per i dati."}

@app.get("/data", summary="Ottieni tutti i dati di tutte le province")
def get_all_data():
    """Restituisce il contenuto di tutti i file JSON trovati nella cartella output."""
    data = load_all_json_data()
    if not data:
        raise HTTPException(status_code=404, detail="Nessun file JSON trovato nella cartella output.")
    return data

@app.get("/provinces", summary="Elenco delle province disponibili")
def list_provinces():
    """Slug, nome e sigle (es. FC) di ogni provincia scaricata: l'app Cinemate lo usa per
    trovare la provincia dell'utente a partire dal nome o dalla sigla restituiti dal GPS."""
    result = []
    for item in load_all_json_data():
        codes = sorted({c.get("province_code") for c in item.get("cinemas", []) if c.get("province_code")})
        result.append({
            "province": item.get("province"),
            "province_name": item.get("province_name"),
            "codes": codes,
            "timestamp": item.get("timestamp"),
            "total_cinemas": item.get("total_cinemas"),
        })
    return result

@app.get("/province/{province_name}", summary="Filtra per nome provincia")
def get_by_province(province_name: str, date: Optional[str] = None):
    """Cerca e restituisce i dati relativi a una specifica provincia (es. 'agrigento').
    Ogni gruppo di orari ha il suo giorno (`date`, YYYY-MM-DD): di default ci sono tutti i giorni
    in programmazione, con `?date=2026-11-01` solo quel giorno."""
    all_data = load_all_json_data()
    for item in all_data:
        if item.get("province", "").lower() == province_name.lower():
            return filter_by_date(item, date) if date else item
    raise HTTPException(status_code=404, detail=f"Provincia '{province_name}' non trovata.")

def filter_by_date(item: dict, day: str) -> dict:
    """Copia della provincia con i soli orari del giorno richiesto (film senza orari quel giorno esclusi)."""
    cinemas = []
    for cinema in item.get("cinemas", []):
        movies = []
        for movie in cinema.get("movies", []):
            showtimes = [s for s in movie.get("showtimes", []) if s.get("date") == day]
            if showtimes:
                movies.append({**movie, "showtimes": showtimes})
        cinemas.append({**cinema, "movies": movies})
    return {**item, "cinemas": cinemas}

# Funzione per l'aggiornamento automatico dei dati tramite la pipeline
def job_aggiornamento_dati():
    """Funzione che esegue lo scraping di tutte le province in automatico."""
    print("Avvio dello scraping giornaliero (pipeline)...")
    try:
        # Esegue la pipeline reale salvando i file nella cartella output corretta
        run_pipeline(output_dir=str(DATA_DIR), resume=False)
        print("Scraping completato con successo. File JSON aggiornati.")
    except Exception as e:
        print(f"Errore durante l'esecuzione della pipeline: {e}")

# Configura lo scheduler in background
scheduler = BackgroundScheduler()

# Esegue il job SUBITO all'avvio e poi ogni 24 ore
scheduler.add_job(
    job_aggiornamento_dati, 
    'interval', 
    days=1, 
    next_run_time=datetime.now(timezone.utc)
) 
scheduler.start()

@app.on_event("shutdown")
def shutdown_event():
    scheduler.shutdown()

# Endpoint per verificare lo stato dello scheduler
@app.get("/status", summary="Verifica stato API e Scheduler")
def get_status():
    """Restituisce lo stato dell'API e i prossimi job pianificati."""
    jobs_info = []
    for job in scheduler.get_jobs():
        jobs_info.append({
            "id": job.id,
            "next_run_time": str(job.next_run_time)
        })
        
    return {
        "status": "online",
        "scheduler_running": scheduler.running,
        "scheduled_jobs": jobs_info
    }