"""Scraper for comingsoon.it/cinema — provinces, cinemas, and per-cinema
film programming (showtimes).

Selectors below were verified by inspecting the live, server-rendered HTML
(no JS execution needed — a plain requests.get() already contains the full
markup), not guessed from naming conventions.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import config
from .http_client import PoliteSession

logger = logging.getLogger(__name__)

_FILM_ID_RE = re.compile(r"/film/[^/]+/(\d+)/scheda/")
_TIME_RE = re.compile(r"\d{1,2}[.:]\d{2}")
_SALA_RE = re.compile(r"Sala\s*([\w.\-]+)")
_POSTI_RE = re.compile(r"Posti\s*(\d+)")
_CINEMA_HREF_RE = re.compile(r"^/cinema/[a-z0-9\-]+/[a-z0-9\-]+/\d+/?$")
_PROVINCE_HREF_RE = re.compile(r"^/cinema/[a-z0-9\-]+/$")


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


def _parse_showtime_block(block) -> Showtime:
    text = block.get_text(" ", strip=True)
    sala_match = _SALA_RE.search(text)
    posti_match = _POSTI_RE.search(text)
    times = [t.replace(".", ":") for t in _TIME_RE.findall(text)]
    return Showtime(
        sala=sala_match.group(1) if sala_match else None,
        posti=int(posti_match.group(1)) if posti_match else None,
        times=sorted(set(times)),
    )


def _parse_screening_card(card) -> Screening:
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

    showtimes = [
        _parse_showtime_block(block) for block in card.select(".cs-btn.primary.ico.sala")
    ]

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
    )


def get_cinema_program(session: PoliteSession, cinema: CinemaRef) -> CinemaProgram:
    """Scrape a single cinema's page: address + every film currently showing
    with its showtimes."""
    resp = session.get(cinema.url)
    soup = BeautifulSoup(resp.text, "html.parser")

    address, city, province_code, phone = _parse_address_block(soup)

    screenings = [_parse_screening_card(card) for card in soup.select(".header-scheda")]

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
