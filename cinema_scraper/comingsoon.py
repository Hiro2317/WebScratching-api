"""Scraper for comingsoon.it/cinema — provinces, cinemas, and per-cinema
film programming (showtimes).

Selectors below were verified by inspecting the live, server-rendered HTML
(no JS execution needed — a plain requests.get() already contains the full
markup), not guessed from naming conventions.
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import config
from .http_client import PoliteSession

logger = logging.getLogger(__name__)

_FILM_ID_RE = re.compile(r"/film/[^/]+/(\d+)/scheda/")
_TIME_RE = re.compile(r"\d{1,2}[.:]\d{2}")
_SALA_RE = re.compile(r"Sala\s*([\w.\-]+)", re.IGNORECASE)
_POSTI_RE = re.compile(r"Posti\s*(\d+)")
_CINEMA_HREF_RE = re.compile(r"^/cinema/[a-z0-9\-]+/[a-z0-9\-]+/\d+/?$")
_PROVINCE_HREF_RE = re.compile(r"^/cinema/[a-z0-9\-]+/$")
_TICKET_HREF_RE = re.compile(r"/ticket/\?idf=\d+")

_ROME = ZoneInfo("Europe/Rome")
_MONTHS = {
    "GEN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAG": 5, "GIU": 6,
    "LUG": 7, "AGO": 8, "SET": 9, "OTT": 10, "NOV": 11, "DIC": 12,
}


@dataclass
class Province:
    slug: str
    name: str

    @property
    def url(self) -> str:
        return f"{config.BASE_URL}/cinema/{self.slug}/"


@dataclass
class CinemaRef:
    name: str
    slug: str
    cinema_id: str
    url: str


@dataclass
class Showtime:
    sala: Optional[str]
    posti: Optional[int]
    times: List[str] = field(default_factory=list)
    # Giorno degli spettacoli (YYYY-MM-DD, ora di Roma).
    date: Optional[str] = None
    # Link d'acquisto (Webtic) allineati a `times`; None dove la pagina non lo dà.
    booking_links: List[Optional[str]] = field(default_factory=list)


@dataclass
class Screening:
    raw_title: str
    canonical_title: str
    original_title: Optional[str]
    comingsoon_film_id: Optional[str]
    genere: Optional[str]
    durata: Optional[str]
    uscita: Optional[str]
    cast: Optional[str]
    showtimes: List[Showtime] = field(default_factory=list)
    # Pagina "Acquista biglietto e vedi tutte le date" del film in questo cinema.
    ticket_url: Optional[str] = None


@dataclass
class CinemaProgram:
    name: str
    url: str
    address: Optional[str]
    city: Optional[str]
    province_code: Optional[str]
    phone: Optional[str]
    screenings: List[Screening] = field(default_factory=list)


def list_provinces(session: PoliteSession) -> List[Province]:
    """Scrape the full list of Italian provinces covered by comingsoon.it."""
    resp = session.get(config.TROVACINEMA_URL)
    soup = BeautifulSoup(resp.text, "html.parser")

    provinces = []
    seen = set()
    for a in soup.select('a[href^="/cinema/"]'):
        href = a.get("href", "")
        if not _PROVINCE_HREF_RE.match(href):
            continue
        slug = href.strip("/").split("/")[-1]
        if slug in config.NON_PROVINCE_SLUGS or slug in seen:
            continue
        seen.add(slug)
        name = a.get_text(strip=True)
        if name:
            provinces.append(Province(slug=slug, name=name))
    return provinces


def list_cinemas(session: PoliteSession, province: Province) -> List[CinemaRef]:
    """Scrape every cinema listed for a given province."""
    resp = session.get(province.url)
    soup = BeautifulSoup(resp.text, "html.parser")

    cinemas = []
    seen = set()
    for a in soup.select(f'a[href^="/cinema/{province.slug}/"]'):
        href = a.get("href", "")
        if not _CINEMA_HREF_RE.match(href):
            continue
        if href in seen:
            continue
        seen.add(href)
        parts = href.strip("/").split("/")
        slug, cinema_id = parts[1], parts[2]
        name = a.get("title") or a.get_text(strip=True)
        cinemas.append(
            CinemaRef(
                name=name,
                slug=slug,
                cinema_id=cinema_id,
                url=urljoin(config.BASE_URL, href),
            )
        )
    return cinemas


def _parse_address_block(soup: BeautifulSoup) -> tuple:
    h1 = soup.select_one("h1.h1")
    if not h1:
        return None, None, None, None
    p = h1.find_next("p")
    if not p:
        return None, None, None, None
    spans = [s.get_text(strip=True) for s in p.find_all("span")]
    address = spans[0] if len(spans) > 0 else None
    city = spans[1] if len(spans) > 1 else None
    province_code = spans[2] if len(spans) > 2 else None
    phone = spans[3] if len(spans) > 3 else None
    return address, city, province_code, phone


def today_rome() -> date:
    return datetime.now(_ROME).date()


def _normalize_time(text: str) -> str:
    h, m = re.split(r"[.:]", text)
    return f"{int(h):02d}:{m}"


def _parse_showtime_block(block, day: Optional[str] = None) -> Showtime:
    text = block.get_text(" ", strip=True)
    sala_match = _SALA_RE.search(text)
    posti_match = _POSTI_RE.search(text)
    times = sorted({_normalize_time(t) for t in _TIME_RE.findall(text)})
    return Showtime(
        sala=sala_match.group(1) if sala_match else None,
        posti=int(posti_match.group(1)) if posti_match else None,
        times=times,
        date=day,
        booking_links=[None] * len(times),
    )


def _calendar_date(day: int, month: int, today: date) -> Optional[date]:
    """La pagina biglietti mostra solo giorno e mese ("1 NOV"): l'anno è quello della data più
    vicina a oggi (a dicembre "2 GEN" è dell'anno dopo, a gennaio "30 DIC" dell'anno prima)."""
    candidates = []
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            continue
    if not candidates:
        return None
    return min(candidates, key=lambda d: abs((d - today).days))


def _parse_ticket_page(html: str, posti_by_sala: dict, today: date) -> List[Showtime]:
    """Tutti i giorni in programmazione di un film in un cinema, dalla pagina
    `/cinema/{provincia}/{cinema}/{id}/ticket/?idf={film}`: un blocco `.media` per giorno con
    `.calendar-icon` (giorno della settimana, giorno, mese) e un `button.btn-fab` per spettacolo
    (title "SALA 3", testo "20:20", data-url = link d'acquisto Webtic)."""
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one("#salaFilmList") or soup
    showtimes: List[Showtime] = []
    for media in root.select(".media"):
        icon = media.select_one(".calendar-icon")
        if not icon:
            continue
        day_node = icon.select_one(".day")
        month_node = icon.select_one(".month")
        if not day_node or not month_node:
            continue
        month = _MONTHS.get(month_node.get_text(strip=True).upper()[:3])
        try:
            day_number = int(day_node.get_text(strip=True))
        except ValueError:
            continue
        if not month:
            continue
        day = _calendar_date(day_number, month, today)
        if not day:
            continue

        by_sala: dict = {}
        for button in media.select("button.btn-fab, a.btn-fab"):
            time_match = _TIME_RE.search(button.get_text(" ", strip=True))
            if not time_match:
                continue
            sala_match = _SALA_RE.search(button.get("title", ""))
            sala = sala_match.group(1) if sala_match else None
            by_sala.setdefault(sala, {})[_normalize_time(time_match.group(0))] = (
                button.get("data-url") or None
            )

        for sala, slots in by_sala.items():
            times = sorted(slots)
            showtimes.append(
                Showtime(
                    sala=sala,
                    posti=posti_by_sala.get(sala),
                    times=times,
                    date=day.isoformat(),
                    booking_links=[slots[t] for t in times],
                )
            )
    return showtimes


def _parse_screening_card(card, today: Optional[date] = None) -> Screening:
    title_node = card.select_one(".testo a.tit_olo")
    raw_title = title_node.get_text(strip=True) if title_node else ""

    original_title = None
    subtitle_node = card.select_one(".sottotitolo")
    if subtitle_node:
        original_title = subtitle_node.get_text(strip=True).strip("()").strip() or None

    meta = {}
    for p in card.select(".meta .p"):
        label_node = p.find("b")
        value_node = p.find("span")
        if label_node and value_node:
            label = label_node.get_text(strip=True).rstrip(":")
            meta[label] = value_node.get_text(strip=True)

    film_id = None
    scheda_link = card.select_one('a[href*="/scheda/"]')
    if scheda_link:
        match = _FILM_ID_RE.search(scheda_link.get("href", ""))
        if match:
            film_id = match.group(1)

    # La scheda del cinema mostra solo gli orari del giorno.
    day = (today or today_rome()).isoformat()
    showtimes = [
        _parse_showtime_block(block, day) for block in card.select(".cs-btn.primary.ico.sala")
    ]

    ticket_url = None
    ticket_link = card.find("a", href=_TICKET_HREF_RE)
    if ticket_link:
        ticket_url = urljoin(config.BASE_URL, ticket_link["href"])

    return Screening(
        raw_title=raw_title,
        canonical_title=raw_title,
        original_title=original_title,
        comingsoon_film_id=film_id,
        genere=meta.get("Genere"),
        durata=meta.get("Durata"),
        uscita=meta.get("Uscita al cinema"),
        cast=meta.get("Cast"),
        showtimes=showtimes,
        ticket_url=ticket_url,
    )


def fill_all_days(session: PoliteSession, screening: Screening, today: date) -> None:
    """Sostituisce gli orari di oggi con quelli di tutti i giorni in programmazione, se il film
    ha la pagina biglietti. Se la pagina non c'è, non risponde o non ha date, restano gli orari
    di oggi presi dalla scheda del cinema."""
    if not screening.ticket_url:
        return
    try:
        resp = session.get(screening.ticket_url)
    except Exception as exc:  # noqa: BLE001 - restano gli orari di oggi
        logger.warning("ticket page failed %s: %s", screening.ticket_url, exc)
        return
    posti_by_sala = {s.sala: s.posti for s in screening.showtimes if s.posti is not None}
    all_days = _parse_ticket_page(resp.text, posti_by_sala, today)
    if not all_days:
        return
    # Oggi resta quello della scheda del cinema se la pagina biglietti non ce l'ha (es. spettacoli
    # senza vendita online).
    covered = {s.date for s in all_days}
    keep_today = [s for s in screening.showtimes if s.date not in covered]
    screening.showtimes = sorted(
        keep_today + all_days, key=lambda s: (s.date or "", s.times[0] if s.times else "")
    )


def get_cinema_program(
    session: PoliteSession, cinema: CinemaRef, all_days: bool = config.FETCH_ALL_DAYS
) -> CinemaProgram:
    """Scrape a single cinema's page: address + every film currently showing
    with its showtimes. With all_days, each film's ticket page is fetched too, for the
    showtimes of every scheduled day (the cinema page only lists today's)."""
    resp = session.get(cinema.url)
    soup = BeautifulSoup(resp.text, "html.parser")

    address, city, province_code, phone = _parse_address_block(soup)

    today = today_rome()
    screenings = [_parse_screening_card(card, today) for card in soup.select(".header-scheda")]
    if all_days:
        for screening in screenings:
            fill_all_days(session, screening, today)

    name_node = soup.select_one("h1.h1")
    name = name_node.get_text(strip=True) if name_node else cinema.name

    return CinemaProgram(
        name=name,
        url=cinema.url,
        address=address,
        city=city,
        province_code=province_code,
        phone=phone,
        screenings=screenings,
    )
