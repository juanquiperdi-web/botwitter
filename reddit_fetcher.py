"""
Fuente de contenido viral: lee /r/SUBREDDIT/hot.json sin clave API.
Devuelve posts con media (vídeo o imagen) sobre el tema solicitado.
Reddit acepta JSON anónimo si pasamos un User-Agent decente.
"""
import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger(__name__)

USER_AGENT = "GeopoliticsBot/1.0 (curated curiosity content)"

# Mapeo tema -> lista de subreddits a explorar.
# Cada lista mantiene subreddits FIELES al tema. El sistema buscará vídeo primero
# entre estos; si no encuentra, acepta imagen del MISMO tema.
# Orden: VÍDEO-PESADO primero, imagen/texto como respaldo.
TOPIC_SUBREDDITS = {
    # Vídeo enganchón para posts de vídeo (clips virales/satisfying/curiosos).
    # OJO: contenido de terceros — vetar copyright; preferir Pexels si hay duda.
    "video": [
        # Mapeado a los 7 patrones de las cuentas de referencia (virales variados):
        "oddlysatisfying",        # satisfying / proceso
        "nextfuckinglevel",       # ingeniería / talento / skill
        "BeAmazed",               # asombro
        "Damnthatsinteresting",   # curioso / ciencia
        "interestingasfuck",      # curioso
        "CookingVideos",          # cocina
        "foodhacks",              # trucos de cocina
        "GifRecipes",             # recetas
        "aww",                    # animales tiernos
        "AnimalsBeingDerps",      # animales graciosos
        "Awwducational",          # animales + dato curioso
        "NatureIsFuckingLit",     # naturaleza / animales espectacular
        "ContagiousLaughter",     # gracioso
        "MadeMeSmile",            # feel-good / relatable
        "humansbeingbros",        # gente ayudando (emotivo)
        "educationalgifs",        # cómo funciona algo (asombro/ciencia)
    ],
    # Nicho psicología / autoconocimiento (curiosidades de comportamiento, texto):
    "psicologia": [
        "psychology",
        "GetMotivated",
        "DecidingToBeBetter",
        "socialskills",
        "YouShouldKnow",
        "LifeProTips",
        "todayilearned",
        "Showerthoughts",
    ],
    "futbol": [
        # Subs con MUCHO vídeo de fútbol (highlights, goles, jugadas):
        "soccer",                    # principal, muchos clips
        "footballhighlights",
        "soccerhighlights",
        "ChampionsLeague",
        "LaLiga",
        "PremierLeague",
        "realmadrid",
        "Barca",
        "fcbayern",
        "footballreplays",
        # Imagen/texto como respaldo:
        "FantasyPL",
        "soccerporn",
    ],
}


def _is_video_post(post: dict) -> bool:
    if post.get("is_video"):
        return True
    media = post.get("secure_media") or {}
    if media and media.get("reddit_video"):
        return True
    url = (post.get("url") or "").lower()
    if "v.redd.it" in url or "gfycat.com" in url:
        return True
    return False


def _is_image_post(post: dict) -> bool:
    url = (post.get("url") or "").lower()
    if any(url.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
        return True
    if "i.redd.it" in url or "i.imgur.com" in url:
        return True
    return False


def _get_media_url(post: dict) -> tuple[Optional[str], str]:
    """Devuelve (url, tipo) donde tipo es 'video', 'image' o ''."""
    # Vídeo nativo de Reddit
    media = post.get("secure_media") or {}
    if media and media.get("reddit_video"):
        rv = media["reddit_video"]
        # fallback_url es mp4 directo
        return rv.get("fallback_url"), "video"
    # Imagen directa
    url = post.get("url") or ""
    if _is_image_post(post):
        return url, "image"
    # Preview de Reddit
    preview = post.get("preview") or {}
    images = preview.get("images") or []
    if images:
        src = images[0].get("source") or {}
        if src.get("url"):
            # Unescape HTML entities
            return src["url"].replace("&amp;", "&"), "image"
    return None, ""


def _fetch_subreddit_hot(subreddit: str, limit: int = 25, time_filter: str = "day") -> list[dict]:
    """Llama a Reddit JSON API anónima para /r/X/hot."""
    try:
        url = f"https://www.reddit.com/r/{subreddit}/hot.json"
        r = requests.get(
            url,
            params={"limit": limit, "t": time_filter},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        children = data.get("data", {}).get("children", [])
        return [c.get("data", {}) for c in children]
    except Exception as e:
        log.warning(f"Error fetching r/{subreddit}: {e}")
        return []


def _valid_post(p: dict, used_post_ids: set) -> bool:
    pid = p.get("id")
    if not pid or pid in used_post_ids:
        return False
    if p.get("stickied") or p.get("pinned"):
        return False
    if p.get("over_18"):
        return False
    title = p.get("title", "").strip()
    if len(title) < 20:
        return False
    ups = p.get("ups", 0)
    if ups < 100:
        return False
    return True


def _post_to_dict(p: dict, subreddit: str, media_url: str, media_type: str) -> dict:
    permalink = "https://www.reddit.com" + p.get("permalink", "")
    return {
        "id": p.get("id"),
        "subreddit": subreddit,
        "title": p.get("title", "").strip(),
        "selftext": (p.get("selftext") or "").strip()[:1500],
        "ups": p.get("ups", 0),
        "permalink": permalink,
        "media_type": media_type,
        "media_url": media_url,
    }


def _extract_keywords(tweet_text: str, max_words: int = 4) -> str:
    """Saca 2-4 palabras clave del tweet para buscar en Reddit."""
    import re as _re
    # Quita URLs y @mentions
    txt = _re.sub(r"https?://\S+", " ", tweet_text)
    txt = _re.sub(r"@\w+", " ", txt)
    # Prioriza nombres propios (palabras Capitalizadas no al inicio de frase)
    proper = _re.findall(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,}\b", txt)
    # Resto de palabras significativas
    stop_es = {"el", "la", "los", "las", "un", "una", "y", "o", "de", "del", "al", "a",
               "en", "con", "por", "para", "que", "se", "su", "es", "son", "ha", "han",
               "este", "esta", "como", "tras", "más", "sobre", "entre", "mientras",
               "hace", "hacen"}
    stop_en = {"the", "and", "of", "in", "to", "for", "on", "is", "was", "are", "this",
               "that", "with", "from", "by", "as", "an", "be", "at", "or"}
    stopwords = stop_es | stop_en
    cleaned = _re.sub(r"[^\wáéíóúñÁÉÍÓÚÑ ]+", " ", txt.lower())
    words = [w for w in cleaned.split() if len(w) >= 4 and w not in stopwords]
    # Mantén primero nombres propios, luego palabras significativas
    out: list[str] = []
    seen = set()
    for w in [p.lower() for p in proper] + words:
        if w not in seen:
            seen.add(w)
            out.append(w)
        if len(out) >= max_words:
            break
    return " ".join(out)


def fetch_post_by_keywords(keywords: str, used_post_ids: set = None,
                          video_only: bool = True) -> Optional[dict]:
    """Busca en TODO Reddit posts con VÍDEO que matcheen los keywords del tweet original.
    Si video_only=True (default), descarta imágenes. Si no encuentra vídeo, devuelve None."""
    if not keywords or not keywords.strip():
        return None
    if used_post_ids is None:
        used_post_ids = set()

    try:
        r = requests.get(
            "https://www.reddit.com/search.json",
            params={"q": keywords, "sort": "relevance", "t": "year", "limit": 30},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        posts = [c.get("data", {}) for c in data.get("data", {}).get("children", [])]
    except Exception as e:
        log.warning(f"Error buscando Reddit por keywords '{keywords}': {e}")
        return None

    log.info(f"Reddit search '{keywords}': {len(posts)} resultados")

    # Solo vídeos
    for p in posts:
        if not _valid_post(p, used_post_ids):
            continue
        media_url, media_type = _get_media_url(p)
        if media_type != "video":
            continue
        log.info(f"Match keyword VIDEO: r/{p.get('subreddit', '?')} ({p.get('ups', 0)} ups)")
        return _post_to_dict(p, p.get("subreddit", ""), media_url, media_type)

    if not video_only:
        # Fallback: cualquier media
        for p in posts:
            if not _valid_post(p, used_post_ids):
                continue
            media_url, media_type = _get_media_url(p)
            if not media_url:
                continue
            return _post_to_dict(p, p.get("subreddit", ""), media_url, media_type or "")

    log.info(f"Sin VÍDEO coherente para keywords '{keywords}'")
    return None


def fetch_topic_post(topic: str, used_post_ids: set = None,
                     require_media: bool = True,
                     prefer_video: bool = True) -> Optional[dict]:
    """Devuelve un post 'hot' del tema solicitado con media (vídeo/imagen).

    Estrategia con prefer_video=True (default):
      PASE 1: busca SOLO vídeos en todos los subreddits del tema.
      PASE 2: si no encuentra vídeo, acepta imágenes.

    Estructura devuelta:
    {
        "id": "abc123", "subreddit": "...", "title": "...",
        "selftext": "...", "ups": 12500,
        "permalink": "...", "media_type": "video"|"image", "media_url": "..."
    }
    """
    if used_post_ids is None:
        used_post_ids = set()
    subreddits = TOPIC_SUBREDDITS.get(topic, [])
    if not subreddits:
        log.warning(f"Tema desconocido: {topic}")
        return None

    # PASE 1: solo vídeos
    if prefer_video:
        for sub in subreddits:
            posts = _fetch_subreddit_hot(sub, limit=25)
            for p in posts:
                if not _valid_post(p, used_post_ids):
                    continue
                media_url, media_type = _get_media_url(p)
                if media_type != "video":
                    continue
                log.info(f"Post elegido (VIDEO): r/{sub} ({p.get('ups', 0)} ups) | {p.get('title', '')[:80]}")
                return _post_to_dict(p, sub, media_url, media_type)

    # PASE 2: cualquier media
    for sub in subreddits:
        posts = _fetch_subreddit_hot(sub, limit=25)
        for p in posts:
            if not _valid_post(p, used_post_ids):
                continue
            media_url, media_type = _get_media_url(p)
            if require_media and not media_url:
                continue
            log.info(f"Post elegido ({media_type or 'no-media'}): r/{sub} ({p.get('ups', 0)} ups) | {p.get('title', '')[:80]}")
            return _post_to_dict(p, sub, media_url, media_type or "")
    return None


def download_media(media_url: str, media_type: str, max_size_mb: int = 12) -> Optional[Path]:
    """Descarga un vídeo o imagen y devuelve la ruta local. None si falla."""
    if not media_url:
        return None
    try:
        r = requests.get(
            media_url,
            stream=True,
            timeout=20,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        )
        r.raise_for_status()
        if media_type == "video":
            ext = ".mp4"
        else:
            # Intenta detectar extensión
            url_low = media_url.lower().split("?")[0]
            for e in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                if url_low.endswith(e):
                    ext = e
                    break
            else:
                ext = ".jpg"

        tmp = Path(tempfile.gettempdir()) / f"reddit_{abs(hash(media_url))}{ext}"
        size = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
                size += len(chunk)
                if size > max_size_mb * 1024 * 1024:
                    log.warning(f"Media demasiado grande, abortando: {media_url}")
                    tmp.unlink(missing_ok=True)
                    return None
        if tmp.stat().st_size < 8_000:
            log.warning(f"Media demasiado pequeña: {tmp.stat().st_size} bytes")
            tmp.unlink(missing_ok=True)
            return None
        log.info(f"Media descargada ({media_type}, {tmp.stat().st_size} bytes): {tmp}")
        return tmp
    except Exception as e:
        log.warning(f"Error descargando media {media_url[:80]}: {e}")
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for topic in ["historia", "ciencia", "ia", "naturaleza"]:
        print(f"\n=== {topic.upper()} ===")
        post = fetch_topic_post(topic)
        if post:
            print(f"  r/{post['subreddit']} ({post['ups']} ups, {post['media_type']})")
            print(f"  {post['title'][:120]}")
            if post['selftext']:
                print(f"  Selftext: {post['selftext'][:200]}")
            print(f"  Media: {post['media_url'][:80] if post['media_url'] else 'None'}")
        else:
            print("  Sin post")
