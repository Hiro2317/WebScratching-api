# Handoff — WebScratching-api (scraper ComingSoon.it per Cinemate)

Ultimo aggiornamento: 31 ottobre 2026.

## Ultima modifica: orari di tutti i giorni, non solo di oggi

**Problema.** La scheda di un cinema su comingsoon.it (`/cinema/{provincia}/{cinema}/{id}/`) mostra
solo gli orari di oggi, quindi l'output e l'app Cinemate avevano solo la programmazione del giorno.

**Correzione.**
- `cinema_scraper/comingsoon.py`: per ogni film della scheda cinema si segue il link
  "Acquista biglietto e vedi tutte le date" (`.../ticket/?idf={film}`). Lì c'è un blocco per giorno
  (`#salaFilmList .media`, data in `.calendar-icon` come "sabato 31 OTT") con un pulsante
  `button.btn-fab` per spettacolo (`title="SALA 3"`, testo `20:20`, `data-url` = link Webtic).
  Selettori verificati sull'HTML reale del 31/10/2026 (Adriano Multisala, Roma).
- Ogni gruppo di orari ha ora `date` (YYYY-MM-DD, ora di Roma) e `booking_links` (allineati a
  `times`, `null` se manca). L'anno si deduce dalla data più vicina a oggi (dicembre/gennaio ok).
- Se la pagina biglietti manca, fallisce o non ha date, restano gli orari di oggi della scheda
  cinema (con `date` = oggi). Se la pagina biglietti non ha oggi, oggi resta quello della scheda.
- `config.FETCH_ALL_DAYS` (env `FETCH_ALL_DAYS`, default `1`): `0` per tornare ai soli orari di oggi.
- Costo: una richiesta in più per film per cinema, lo scraping completo dura qualche volta di più
  (ritardo educato 1,5 s per thread invariato).
- `requirements.txt`: `tzdata` (fuso Europe/Rome nell'immagine `python:3.10-slim`).
- `API/API.py`: nuovo `GET /provinces` (serve all'edge function `cinema-scraper` di Cinemate per
  trovare la provincia da nome o sigla) e `?date=YYYY-MM-DD` opzionale su `/province/{slug}`.

Testato: parsing su HTML reale salvato (scheda cinema + pagina biglietti), anno a cavallo
dell'anno nuovo. Non testato uno scraping completo (comingsoon.it non è raggiungibile dal
container cloud).

## Deploy (Coolify)
Repository: fork `Leo0541/WebScratching-api` (l'originale è `Hiro2317/WebScratching-api`, dove
Claude non ha accesso in scrittura). Le modifiche sono già su `main` del fork.
1. Coolify → applicazione dello scraper → Configuration → General → Source/Git: repository
   `https://github.com/Leo0541/WebScratching-api`, branch `main` (se puntava a quello di Hiro2317).
2. **Redeploy** (build dal `Dockerfile`, porta 4001).
3. All'avvio lo scheduler rifà subito lo scraping di tutte le province (poi ogni 24 ore): finché
   non finisce, le province non ancora riscaricate restano col vecchio formato (solo oggi, senza
   `date`). L'edge function di Cinemate gestisce entrambi i formati.
4. Verifica: `https://cinemate.cloud/WebScratching-api/italia/provinces` e
   `.../province/roma` (gli orari devono avere `date` su più giorni).

## Note
- Il dato `ticket_url` del film finisce anche nell'output JSON (innocuo).
- `tmdb.py`: nel repo manca `self._warned_no_key = True` dopo il warning sulla chiave TMDb (il
  warning si ripete a ogni film). Non toccato qui.
