# Cinema Italia Scraper

Scraper per la programmazione cinematografica italiana: estrae film e orari
da [comingsoon.it](https://www.comingsoon.it/cinema/trovacinema/) per
qualsiasi provincia (o per tutta Italia) e abbina ogni titolo al suo
`tmdb_id` e `imdb_id` tramite [TMDb](https://www.themoviedb.org/).

## Come funziona

1. `comingsoon.py` scrapa, nell'ordine:
   - `/cinema/trovacinema/` → elenco di tutte le province coperte dal sito;
   - `/cinema/{provincia}/` → elenco dei cinema in quella provincia;
   - `/cinema/{provincia}/{cinema}/{id}/` → film in programmazione in quel
     cinema, con sala, posti e orari **di oggi**;
   - `/cinema/{provincia}/{cinema}/{id}/ticket/?idf={film}` → la pagina
     "Acquista biglietto e vedi tutte le date" di ogni film: orari di **tutti
     i giorni in programmazione**, con link d'acquisto Webtic. Se un film non
     ha questa pagina restano gli orari di oggi. `FETCH_ALL_DAYS=0` la salta
     (scraping più veloce, solo oggi).
2. `tmdb.py` risolve ogni titolo (preferendo il titolo originale quando
   disponibile, con l'anno di uscita come filtro) su TMDb, recuperando
   `tmdb_id` e il collegato `imdb_id`.
3. Una cache persistente (`tmdb_cache.json`) è indicizzata sull'id-film
   proprio di comingsoon.it (non sul titolo), così lo stesso film in
   programmazione in centinaia di cinema in tutta Italia viene interrogato
   su TMDb una sola volta.
4. `pipeline.py` orchestra lo scraping con un pool di thread per provincia e
   scrive un file JSON per provincia in `output/`, per poter riprendere
   un'esecuzione interrotta senza ripartire da zero (`--no-resume` per
   forzare un refresh completo).

I selettori CSS sono stati verificati sull'HTML reale del sito (che è
server-rendered: nessun JavaScript necessario), non indovinati da nomi di
classe plausibili.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# poi inserisci la tua TMDb API key (v3) in .env
```

Senza `TMDB_API_KEY` lo scraper funziona comunque: `tmdb_id` e `imdb_id`
restano `null` nell'output.

## Uso

```bash
# Una sola provincia (slug come appare nell'URL comingsoon.it, es. "forli", "roma", "milano")
python -m cinema_scraper.cli --province forli

# Più province
python -m cinema_scraper.cli --province forli --province rimini

# Tutta Italia (operazione lunga: ~110 province, migliaia di cinema)
python -m cinema_scraper.cli

# Solo le prime 5 province, utile per test
python -m cinema_scraper.cli --limit 5 -v
```

Opzioni principali (`python -m cinema_scraper.cli --help`):

- `--output-dir`: cartella di output (default `output/`)
- `--workers`: thread concorrenti per provincia (default 4)
- `--delay`: ritardo minimo in secondi tra le richieste, per thread (default 1.5s)
- `--no-resume`: ri-scarica anche le province già presenti in `output/`
- `-v`: log di debug

## Output

Un file `output/{provincia}.json` per provincia, es.:

```json
{
  "timestamp": 1729555200,
  "province": "forli",
  "province_name": "Forlì",
  "total_cinemas": 16,
  "cinemas": [
    {
      "name": "Cinema Multisala Astoria",
      "source_url": "https://www.comingsoon.it/cinema/forli/multisala-astoria/260/",
      "address": "viale Appennino",
      "city": "Forlì",
      "province_code": "FC",
      "phone": "054360064",
      "movies": [
        {
          "raw_title": "Je So' Pazzo",
          "original_title": "Je so' Pazzo",
          "comingsoon_film_id": "67032",
          "genere": "Biografico",
          "durata": "105 Minuti",
          "uscita": "15/10/2026",
          "cast": "Massimiliano Caiazzo, ...",
          "showtimes": [
            {"sala": "3", "posti": 144, "times": ["18:30", "21:00"], "date": "2026-10-31",
             "booking_links": ["https://secure.webtic.it/...", "https://secure.webtic.it/..."]},
            {"sala": "3", "posti": 144, "times": ["21:00"], "date": "2026-11-01",
             "booking_links": ["https://secure.webtic.it/..."]}
          ],
          "tmdb_id": 693134,
          "imdb_id": "tt15239678",
          "tmdb_canonical_title": "Je so' pazzo!",
          "poster": "https://image.tmdb.org/t/p/w500/xxx.jpg"
        }
      ]
    }
  ]
}
```

## API (FastAPI, porta 4001)

- `GET /provinces` → slug, nome, sigle (es. `FC`) e timestamp di ogni provincia scaricata.
- `GET /province/{slug}` → la provincia con tutti i giorni in programmazione;
  `?date=YYYY-MM-DD` per un solo giorno.
- `GET /data` → tutte le province; `GET /status` → stato dello scheduler (scraping ogni 24 ore).

## Nota etica / robots.txt

Il `robots.txt` di comingsoon.it vieta esplicitamente ad AnthropicBot/Claude
solo il percorso `/tag/`; `/cinema/` non è soggetto ad alcun blocco per i
bot "buoni". Lo scraper si identifica con uno User-Agent onesto
(non impersona un browser) e applica un ritardo minimo configurabile tra le
richieste per restare un crawler educato. Usalo in modo responsabile: non
aumentare la concorrenza/riduzione del delay per fare scraping aggressivo.
