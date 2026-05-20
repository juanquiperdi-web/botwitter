"""
Busca en X tweets recientes con vídeo de medios verificados sobre un tema,
para hacer quote-tweet con el vídeo real de la noticia.
"""
import logging
import re
import urllib.parse
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright

log = logging.getLogger(__name__)
PROFILE_DIR = Path(__file__).parent / "chrome_profile"

# Cuentas de medios españoles verificados con cobertura política/noticias
TRUSTED_ACCOUNTS = [
    "rtve", "rtvenoticias", "el_pais", "elmundoes", "abc_es",
    "lavanguardia", "eldiarioes", "europapress", "la_ser", "ondacero_es",
    "lasextatv", "antena3com", "telecincoes", "cuatro", "cope",
    "newtral", "publico_es", "infoLibre", "elconfidencial",
]


def _build_search_url(keywords: str) -> str:
    accounts = " OR ".join(f"from:{a}" for a in TRUSTED_ACCOUNTS)
    query = f"({accounts}) {keywords} filter:videos"
    encoded = urllib.parse.quote(query)
    return f"https://x.com/search?q={encoded}&f=live"


_STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "y", "o", "de", "del", "al", "a",
    "en", "con", "por", "para", "que", "se", "su", "es", "son", "ha", "han",
    "este", "esta", "más", "como", "tras", "sobre", "entre", "mientras",
    "media", "medio", "medios", "crisis", "llega", "llegan", "tiene", "tienen",
    "hace", "hacen", "ser", "estar",
    "the", "and", "of", "in", "to", "for", "on",
}

# Nombres comunes que sabemos son relevantes para buscar (políticos, países, casos)
_PRIORITY_NAMES = {
    "sánchez", "feijóo", "ayuso", "abascal", "díaz", "puigdemont", "yolanda",
    "ábalos", "koldo", "mazón", "moncloa", "junts", "psoe", "vox",
    "trump", "biden", "putin", "zelenski", "netanyahu", "macron",
    "ucrania", "rusia", "gaza", "israel", "palestina", "irán", "china",
    "taiwán", "otan", "bruselas", "lagarde",
}


def _build_query_keywords(topic_text: str, max_keywords: int = 2) -> str:
    """Extrae nombres propios/conceptos clave. Prioriza nombres conocidos."""
    raw = topic_text
    low = raw.lower()
    low_clean = re.sub(r"[^\wáéíóúñ ]", " ", low)
    words = [w for w in low_clean.split() if len(w) >= 4 and w not in _STOPWORDS]

    # 1. Primero: nombres prioritarios encontrados en el texto
    found_priority = [w for w in _PRIORITY_NAMES if w in low]
    if found_priority:
        return " ".join(found_priority[:max_keywords])

    # 2. Después: nombres propios del texto original (palabras que empiezan en mayúscula)
    proper_nouns = re.findall(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{3,}\b", raw)
    proper_nouns = [w.lower() for w in proper_nouns if w.lower() not in _STOPWORDS]
    if proper_nouns:
        return " ".join(proper_nouns[:max_keywords])

    # 3. Último: primeras palabras significativas
    return " ".join(words[:max_keywords])


def find_news_video_tweet(topic_text: str, headless: bool = True) -> Optional[str]:
    """Devuelve URL de un tweet reciente con vídeo de medio verificado sobre el tema, o None."""
    if not PROFILE_DIR.exists():
        log.warning("Perfil de Chrome no existe; sin búsqueda")
        return None

    keywords = _build_query_keywords(topic_text)
    if not keywords:
        log.info("Sin keywords útiles para buscar quote-tweet")
        return None

    search_url = _build_search_url(keywords)
    log.info(f"Buscando vídeo de medios sobre: {keywords!r}")

    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                channel="chrome",
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 900},
            )
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(5000)

                articles = page.locator('article[data-testid="tweet"]').all()
                log.info(f"Resultados encontrados: {len(articles)}")

                for art in articles[:8]:
                    try:
                        has_video = (
                            art.locator('[data-testid="videoPlayer"]').count() > 0
                            or art.locator('video').count() > 0
                        )
                        if not has_video:
                            continue
                        # URL del tweet
                        link = art.locator('a[href*="/status/"]').first
                        href = link.get_attribute("href", timeout=2000)
                        if not href:
                            continue
                        url = "https://x.com" + href if href.startswith("/") else href
                        # Limpia params
                        url = url.split("?")[0]
                        if re.search(r"/status/\d+$", url):
                            log.info(f"Quote candidato encontrado: {url}")
                            return url
                    except Exception:
                        continue
                return None
            finally:
                context.close()
    except Exception as e:
        log.warning(f"Error buscando quote-tweet: {e}")
        return None


_TOP_ACCOUNTS = ["rtve", "el_pais", "elmundoes", "abc_es", "eldiarioes", "europapress", "la_ser"]

# Texto promocional/cabecera que NO queremos contestar
_PROMO_PATTERNS = (
    "portada", "sigue en directo", "sigue la última hora", "no te pierdas",
    "buenos días", "buenas tardes", "buenas noches", "edición de hoy",
    "noticias destacadas", "lo más leído", "te recomendamos",
    "puedes leer", "lee aquí", "ver vídeo", "vídeo|",
    "newsletter", "boletín", "suscríbete", "@abckioskoymas",
    "kiosko y más",
)


def _is_promo(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in _PROMO_PATTERNS)


# Keywords de FÚTBOL — al menos UNO debe estar presente.
_FUTBOL_KEYWORDS = (
    # Jugadores estrella:
    "messi", "ronaldo", "cristiano", "mbappé", "mbappe", "haaland", "bellingham",
    "vinicius", "vini jr", "lamine", "yamal", "rodrygo", "pedri", "gavi",
    "lewandowski", "salah", "kane", "de bruyne", "rashford", "rüdiger",
    "courtois", "modric", "kroos", "valverde", "camavinga", "tchouameni",
    "musiala", "wirtz", "florian", "ferran", "raphinha", "joao felix",
    # Equipos españoles:
    "real madrid", "madrid", "barça", "barcelona", "barca", "atlético", "atletico",
    "sevilla", "valencia", "betis", "athletic", "real sociedad", "villarreal",
    "espanyol", "celta", "getafe", "rayo", "girona", "osasuna", "alavés",
    # Equipos internacionales top:
    "manchester", "city", "united", "chelsea", "arsenal", "liverpool",
    "tottenham", "psg", "bayern", "dortmund", "leipzig", "inter", "milan",
    "juventus", "napoli", "ajax",
    # Competiciones:
    "laliga", "la liga", "champions", "uefa", "fifa", "premier", "bundesliga",
    "serie a", "ligue 1", "copa del rey", "supercopa", "europa league",
    "mundial", "eurocopa", "copa américa", "copa america",
    # Entrenadores top:
    "ancelotti", "xabi alonso", "flick", "guardiola", "klopp", "simeone",
    "mourinho", "tuchel", "arteta", "luis enrique",
    # Conceptos clave:
    "fichaje", "fichajes", "transfer", "rumor", "cláusula", "clausula",
    "lesión", "lesion", "var", "penalti", "tarjeta roja", "hat-trick",
    "hat trick", "gol", "asistencia", "alineación", "alineacion",
    "futbol", "fútbol", "football", "soccer",
)


def _is_futbol_topic(text: str) -> bool:
    """True SOLO si el texto contiene una keyword de FÚTBOL."""
    low = text.lower()
    return any(kw in low for kw in _FUTBOL_KEYWORDS)


def _try_search_political(query: str, used_urls: set, require_video: bool, headless: bool) -> Optional[dict]:
    encoded = urllib.parse.quote(query)
    search_url = f"https://x.com/search?q={encoded}&f=live"
    log.info(f"Query: {query[:120]}")
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                channel="chrome",
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 900},
            )
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(8000)

                # Probar varios selectores porque X cambia el testid de vez en cuando
                articles = page.locator('article[data-testid="tweet"]').all()
                if not articles:
                    articles = page.locator('[data-testid="cellInnerDiv"] article').all()
                if not articles:
                    articles = page.locator('article[role="article"]').all()
                if not articles:
                    articles = page.locator('article').all()
                log.info(f"Resultados encontrados: {len(articles)}")
                if len(articles) == 0:
                    try:
                        debug_dir = Path(__file__).parent / "debug"
                        debug_dir.mkdir(exist_ok=True)
                        page.screenshot(path=str(debug_dir / "search_empty.png"), full_page=True)
                    except Exception:
                        pass

                for art in articles[:20]:
                    try:
                        link = art.locator('a[href*="/status/"]').first
                        href = link.get_attribute("href", timeout=2000)
                        if not href:
                            continue
                        url = "https://x.com" + href if href.startswith("/") else href
                        url = url.split("?")[0]
                        if not re.search(r"/status/\d+$", url):
                            continue
                        if url in used_urls:
                            continue
                        if require_video:
                            has_video = (
                                art.locator('[data-testid="videoPlayer"]').count() > 0
                                or art.locator('video').count() > 0
                            )
                            if not has_video:
                                continue

                        author = ""
                        m = re.search(r"/([^/]+)/status/", url)
                        if m:
                            author = m.group(1)

                        text = ""
                        try:
                            text = art.locator('[data-testid="tweetText"]').first.inner_text(timeout=2000)
                        except Exception:
                            pass

                        # Filtramos texto muy corto, promocional, o sin contenido sustantivo
                        if len(text) < 50:
                            continue
                        if _is_promo(text):
                            log.info(f"Saltando tweet promocional: {text[:60]}")
                            continue

                        result = {"url": url, "author": author, "text": text}
                        log.info(f"Candidato: @{author} | {url}")
                        return result
                    except Exception:
                        continue
                return None
            finally:
                context.close()
    except Exception as e:
        log.warning(f"Error en _try_search_political: {e}")
        return None


_POLITICAL_KEYWORDS_IN_TEXT = (
    "sánchez", "feijóo", "ayuso", "abascal", "koldo", "mazón", "moncloa",
    "psoe", "pp ", "vox", "junts", "amnistía", "fiscal", "supremo",
    "putin", "trump", "biden", "zelenski", "netanyahu", "macron",
    "ucrania", "rusia", "gaza", "israel", "irán", "china", "taiwán",
    "otan", "ue ", "unión europea", "bruselas", "lagarde",
    "guerra", "ataque", "misil", "huelga", "manifestación", "elecciones",
    "bce", "inflación", "aranceles", "petróleo",
    "diputado", "senador", "ministro", "investidura", "tribunal",
)


_NON_POLITICAL_NOISE = (
    # Deportes
    "florentino", "real madrid", "barça", "barcelona", "atlético", "athletic",
    "fútbol", "futbol", "champions", "liga", "uefa", "fifa", "gol", "messi",
    "cristiano", "ronaldo", "mbappé", "vinicius", "lamine", "bellingham",
    "nba", "lebron", "tenis", "alcaraz", "nadal", "djokovic",
    "f1", "fórmula 1", "alonso", "sainz", "ferrari",
    "moto gp", "motogp", "marc márquez",
    "junta directiva", "junta electoral",
    # Entretenimiento / cultura
    "ot ", "operación triunfo", "supervivientes", "first dates",
    "masterchef", "got talent", "gh ", "gran hermano",
    "reina letizia", "rey felipe", "felipe vi", "leonor", "infanta",
    "alba carrillo", "ana rosa", "pantoja", "shakira", "rosalía",
    "concierto", "festival", "estreno",
)


def _looks_political(text: str) -> bool:
    low = text.lower()
    # Primero: descartar si hay ruido no-político
    if any(noise in low for noise in _NON_POLITICAL_NOISE):
        return False
    # Después: verificar señal política
    return any(kw in low for kw in _POLITICAL_KEYWORDS_IN_TEXT)


def _scrape_profile_for_political_tweet(account: str, used_urls: set,
                                        require_video: bool, headless: bool) -> Optional[dict]:
    """Lee la timeline de UN perfil concreto y devuelve el primer tweet político."""
    url_profile = f"https://x.com/{account}"
    log.info(f"Leyendo perfil de @{account}")
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                channel="chrome",
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 1200},
            )
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(url_profile, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(7000)
                # Scroll para cargar más tweets
                page.mouse.wheel(0, 1500)
                page.wait_for_timeout(2000)

                articles = page.locator('article').all()
                log.info(f"@{account}: {len(articles)} tweets visibles")

                for art in articles[:15]:
                    try:
                        link = art.locator('a[href*="/status/"]').first
                        href = link.get_attribute("href", timeout=2000)
                        if not href:
                            continue
                        url = "https://x.com" + href if href.startswith("/") else href
                        url = url.split("?")[0]
                        if not re.search(r"/status/\d+$", url):
                            continue
                        if url in used_urls:
                            continue

                        # Solo tweets DEL autor (no retweets)
                        if f"/{account.lower()}/status/" not in url.lower():
                            continue

                        if require_video:
                            has_video = (
                                art.locator('[data-testid="videoPlayer"]').count() > 0
                                or art.locator('video').count() > 0
                            )
                            if not has_video:
                                continue

                        text = ""
                        try:
                            text = art.locator('[data-testid="tweetText"]').first.inner_text(timeout=2000)
                        except Exception:
                            pass

                        if len(text) < 50:
                            continue
                        if _is_promo(text):
                            log.info(f"Saltando promo: {text[:60]}")
                            continue
                        if not _looks_political(text):
                            continue

                        log.info(f"Candidato: @{account} | {url}")
                        return {"url": url, "author": account, "text": text}
                    except Exception:
                        continue
                return None
            finally:
                context.close()
    except Exception as e:
        log.warning(f"Error leyendo @{account}: {e}")
        return None


def find_political_post(used_urls: set = None, require_video: bool = False,
                        max_age_hours: int = 6, headless: bool = True) -> Optional[dict]:
    """Lee directamente las timelines de medios verificados (sin usar X search,
    que X rate-limita a cuentas nuevas). Devuelve el primer tweet político válido."""
    if used_urls is None:
        used_urls = set()
    if not PROFILE_DIR.exists():
        return None

    import random as _r
    accounts = list(_TOP_ACCOUNTS)
    _r.shuffle(accounts)

    log.info(f"Buscando tweet político (require_video={require_video}) leyendo timelines")
    for account in accounts[:4]:  # probamos hasta 4 perfiles
        res = _scrape_profile_for_political_tweet(account, used_urls, require_video, headless)
        if res:
            return res
    return None


def find_big_account_post(topic: str, used_urls: set = None,
                          used_accounts: set = None,
                          headless: bool = True) -> Optional[dict]:
    """Elige una cuenta GRANDE del pool al azar y devuelve el primer post válido."""
    from big_accounts import pick_random_account_excluding
    if used_urls is None:
        used_urls = set()
    if used_accounts is None:
        used_accounts = set()

    tried_accounts = set()
    for _ in range(7):
        account = pick_random_account_excluding(topic, used_accounts | tried_accounts)
        if not account:
            break
        tried_accounts.add(account)
        log.info(f"Probando cuenta @{account} para tema {topic}")
        result = _scrape_profile_simple(account, used_urls, headless)
        if result:
            return result
    return None


def _parse_count_label(label: str) -> int:
    """Parsea 'aria-label' de likes/replies/views: '5 me gusta', '1,2 mil', '12K'..."""
    if not label:
        return 0
    s = label.lower().strip()
    m = re.search(r"([\d]+(?:[.,]\d+)?)", s)
    if not m:
        return 0
    num = float(m.group(1).replace(",", "."))
    rest = s[m.end():]
    if "millon" in rest or re.search(r"\bm\b", rest):
        num *= 1_000_000
    elif "mil" in rest or re.search(r"\bk\b", rest):
        num *= 1_000
    return int(num)


def find_viral_hot_tweet(used_urls: set = None,
                         max_age_minutes: int = 20,
                         min_engagement: int = 30,
                         headless: bool = True) -> Optional[dict]:
    """Busca tweets RECIENTES (<20 min) y con BUEN ENGAGEMENT entre las tendencias
    actuales de X. No usa pool de cuentas. Vuelve a quien tiene mejor ratio
    likes+rts en los primeros minutos."""
    from datetime import datetime, timezone, timedelta
    import urllib.parse as _u

    if used_urls is None:
        used_urls = set()
    if not PROFILE_DIR.exists():
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    best: Optional[dict] = None
    best_score = 0

    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                channel="chrome",
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 1200},
            )
            page = context.pages[0] if context.pages else context.new_page()
            try:
                # 1) Obtener tendencias DENTRO de la misma sesión Chrome
                trends: list[str] = []
                try:
                    page.goto("https://x.com/explore/tabs/news", wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(4000)
                    items = page.locator('[data-testid="trend"]').all()
                    seen = set()
                    for it in items[:20]:
                        try:
                            spans = it.locator('span').all_inner_texts()
                            for s in spans:
                                ss = s.strip()
                                if 3 < len(ss) < 60 and "publicaciones" not in ss.lower() and ss.lower() not in seen:
                                    seen.add(ss.lower())
                                    trends.append(ss)
                                    break
                        except Exception:
                            continue
                    log.info(f"Viral-hunt: tendencias detectadas: {trends[:10]}")
                except Exception as e:
                    log.warning(f"Viral-hunt: no se pudieron leer tendencias: {e}")

                if not trends:
                    log.warning("Viral-hunt: sin tendencias")
                    return None

                # Filtramos tendencias claramente no-news
                candidates_trends = [t for t in trends if len(t.lstrip("#")) >= 4 and not t.replace(" ", "").isdigit()]
                log.info(f"Viral-hunt: probando {len(candidates_trends[:6])} tendencias")

                for trend in candidates_trends[:6]:
                    clean = trend.lstrip("#").strip()
                    query = _u.quote(clean)
                    url = f"https://x.com/search?q={query}&f=top"
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=20000)
                        page.wait_for_timeout(5000)
                    except Exception as e:
                        log.warning(f"No se pudo cargar search {clean}: {e}")
                        continue

                    articles = page.locator('article').all()
                    log.info(f"  Tendencia {clean!r}: {len(articles)} tweets visibles")

                    for art in articles[:10]:
                        try:
                            # URL del tweet
                            link = art.locator('a[href*="/status/"]').first
                            href = link.get_attribute("href", timeout=2000)
                            if not href:
                                continue
                            tweet_url = "https://x.com" + href if href.startswith("/") else href
                            tweet_url = tweet_url.split("?")[0]
                            if not re.search(r"/status/\d+$", tweet_url):
                                continue
                            if tweet_url in used_urls:
                                continue

                            # Datetime
                            try:
                                ts = art.locator('time').first.get_attribute('datetime', timeout=1500)
                                if not ts:
                                    continue
                                post_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                                if post_dt < cutoff:
                                    continue
                            except Exception:
                                continue

                            # Texto
                            try:
                                text = art.locator('[data-testid="tweetText"]').first.inner_text(timeout=2000)
                            except Exception:
                                text = ""
                            if len(text) < 30:
                                continue

                            # Engagement: likes + retweets + replies
                            likes = retweets = replies = 0
                            for key, var in (("like", "likes"), ("retweet", "retweets"), ("reply", "replies")):
                                try:
                                    el = art.locator(f'[data-testid="{key}"]').first
                                    label = el.get_attribute("aria-label", timeout=1000) or ""
                                    if var == "likes":
                                        likes = _parse_count_label(label)
                                    elif var == "retweets":
                                        retweets = _parse_count_label(label)
                                    elif var == "replies":
                                        replies = _parse_count_label(label)
                                except Exception:
                                    pass

                            score = likes + retweets * 2 + replies
                            if score < min_engagement:
                                continue

                            # Autor
                            author = ""
                            m = re.search(r"/([^/]+)/status/", tweet_url)
                            if m:
                                author = m.group(1)

                            if score > best_score:
                                best_score = score
                                best = {
                                    "url": tweet_url,
                                    "author": author,
                                    "text": text,
                                    "datetime": post_dt.isoformat(),
                                    "likes": likes,
                                    "retweets": retweets,
                                    "replies": replies,
                                    "score": score,
                                    "trend": clean,
                                }
                        except Exception:
                            continue
            finally:
                context.close()
    except Exception as e:
        log.warning(f"Error viral-hunt: {e}")
        return None

    if best:
        log.info(
            f"Viral-hunt GANADOR: @{best['author']} (score={best_score}, "
            f"likes={best['likes']}, rts={best['retweets']}, replies={best['replies']}, "
            f"trend={best['trend']!r})"
        )
    else:
        log.info("Viral-hunt: sin tweets que cumplan los criterios")
    return best


def find_freshest_any_topic(used_urls: set = None,
                            used_accounts: set = None,
                            scan_count: int = 20,
                            headless: bool = True,
                            early_exit_minutes: int = 30) -> Optional[dict]:
    """RADAR GLOBAL: escanea cuentas de TODOS los pools y devuelve el post
    más reciente, con su tema. El reply se hará sobre ese tema concreto."""
    from datetime import datetime, timezone, timedelta
    from big_accounts import sample_accounts_all_topics
    if used_urls is None:
        used_urls = set()
    if used_accounts is None:
        used_accounts = set()

    pairs = sample_accounts_all_topics(scan_count, exclude=used_accounts)
    if not pairs:
        log.warning("Sin cuentas disponibles en ningún tema")
        return None

    log.info(f"Radar GLOBAL: escaneando hasta {len(pairs)} cuentas de todos los temas")

    fast_path_cutoff = datetime.now(timezone.utc) - timedelta(minutes=early_exit_minutes)
    best: Optional[dict] = None
    best_dt: Optional[datetime] = None

    for topic, account in pairs:
        result = _scrape_profile_simple(account, used_urls, headless, max_age_hours=24)
        if not result:
            continue
        # Inyectamos el topic asociado a la cuenta
        result["topic"] = topic

        dt_str = result.get("datetime")
        if not dt_str:
            if not best:
                best = result
            continue

        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            continue

        if dt > fast_path_cutoff:
            log.info(f"Radar GLOBAL: FRESCO (<{early_exit_minutes}min) de @{account} ({topic}) | {dt.isoformat()}")
            return result

        if not best_dt or dt > best_dt:
            best = result
            best_dt = dt

    if best:
        log.info(
            f"Radar GLOBAL: más reciente @{best['author']} (tema {best.get('topic', '?')}, "
            f"{best.get('datetime', '?')})"
        )
    else:
        log.warning("Radar GLOBAL: sin candidatos")
    return best


def find_freshest_post_radar(topic: str, used_urls: set = None,
                             used_accounts: set = None,
                             scan_count: int = 15,
                             headless: bool = True,
                             early_exit_minutes: int = 30) -> Optional[dict]:
    """RADAR MEJORADO:
    - Escanea hasta `scan_count` cuentas del pool
    - Sale antes si encuentra un post de menos de `early_exit_minutes`
    - Si no, devuelve el más reciente entre las escaneadas
    """
    from datetime import datetime, timezone, timedelta
    from big_accounts import sample_accounts
    if used_urls is None:
        used_urls = set()
    if used_accounts is None:
        used_accounts = set()

    accounts = sample_accounts(topic, scan_count, exclude=used_accounts)
    if not accounts:
        log.warning(f"Sin cuentas para tema {topic} (todas usadas)")
        return None

    log.info(f"Radar tema {topic}: escaneando hasta {len(accounts)} cuentas")

    fast_path_cutoff = datetime.now(timezone.utc) - timedelta(minutes=early_exit_minutes)
    best: Optional[dict] = None
    best_dt: Optional[datetime] = None

    for account in accounts:
        result = _scrape_profile_simple(account, used_urls, headless, max_age_hours=24)
        if not result:
            continue

        dt_str = result.get("datetime")
        if not dt_str:
            # Sin datetime, lo guardamos pero no podemos comparar
            if not best:
                best = result
            continue

        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            continue

        # VÍA RÁPIDA: si está dentro de los últimos N minutos, lo usamos ya
        if dt > fast_path_cutoff:
            log.info(f"Radar: post FRESCO (<{early_exit_minutes}min) de @{account} | {dt.isoformat()}")
            return result

        # Si no, comparamos con el mejor hasta ahora
        if not best_dt or dt > best_dt:
            best = result
            best_dt = dt

    if best:
        log.info(
            f"Radar: sin post <{early_exit_minutes}min. "
            f"Más reciente: @{best['author']} ({best.get('datetime', '?')})"
        )
    else:
        log.warning("Radar: sin candidatos en ninguna cuenta")
    return best


def _scrape_profile_simple(account: str, used_urls: set, headless: bool,
                           max_age_hours: int = 24) -> Optional[dict]:
    """Variante simplificada: devuelve el post más reciente del perfil que sea
    sustancial y no promocional. Si max_age_hours es muy grande (24+), apenas filtra."""
    from datetime import datetime, timezone, timedelta
    url_profile = f"https://x.com/{account}"
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR),
                channel="chrome",
                headless=headless,
                args=["--disable-blink-features=AutomationControlled"],
                viewport={"width": 1280, "height": 1200},
            )
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(url_profile, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(7000)
                page.mouse.wheel(0, 1500)
                page.wait_for_timeout(2000)

                articles = page.locator('article').all()
                log.info(f"@{account}: {len(articles)} tweets visibles")

                for art in articles[:15]:
                    try:
                        link = art.locator('a[href*="/status/"]').first
                        href = link.get_attribute("href", timeout=2000)
                        if not href:
                            continue
                        url = "https://x.com" + href if href.startswith("/") else href
                        url = url.split("?")[0]
                        if not re.search(r"/status/\d+$", url):
                            continue
                        if url in used_urls:
                            continue
                        if f"/{account.lower()}/status/" not in url.lower():
                            continue

                        # Filtro de recencia + capturar datetime para ordenar
                        post_dt = None
                        try:
                            time_el = art.locator('time').first
                            datetime_str = time_el.get_attribute('datetime', timeout=2000)
                            if datetime_str:
                                post_dt = datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
                                if post_dt < cutoff:
                                    log.info(f"@{account}: post antiguo ({post_dt.isoformat()}), saltando")
                                    continue
                        except Exception:
                            pass

                        text = ""
                        try:
                            text = art.locator('[data-testid="tweetText"]').first.inner_text(timeout=2000)
                        except Exception:
                            pass
                        if len(text) < 30:
                            continue
                        if _is_promo(text):
                            continue

                        # Filtro TEMA: el tweet debe ser sobre tech china (o IA/tech en general).
                        # Si la cuenta postea sobre Gaza/política/famosos, lo descartamos.
                        if not _is_futbol_topic(text):
                            log.info(f"@{account}: tweet off-niche, saltando: {text[:60]}")
                            continue

                        log.info(f"Reply target: @{account} | {url} ({post_dt.isoformat() if post_dt else '?'})")
                        return {"url": url, "author": account, "text": text,
                                "datetime": post_dt.isoformat() if post_dt else None}
                    except Exception:
                        continue
                return None
            finally:
                context.close()
    except Exception as e:
        log.warning(f"Error leyendo @{account}: {e}")
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for topic in ["historia", "ciencia", "ia", "naturaleza"]:
        print(f"\n=== {topic} ===")
        r = find_big_account_post(topic)
        print(r)
