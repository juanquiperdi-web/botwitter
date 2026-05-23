"""
Fuente de VÍDEO para los posts del bot. Dos orígenes:
  1) Reddit  → clip viral/curioso de subreddits de vídeo (engaging). Contenido de
     terceros: vetar copyright; puede no pegar con el texto.
  2) Pexels  → vídeo de stock con licencia libre, buscado por tema (seguro y coherente).

Devuelve la ruta a un .mp4 temporal listo para adjuntar con twitter_poster.
Nota: tanto Reddit (v.redd.it) como Pexels suelen venir SIN audio — son clips
visuales; el caption lleva el mensaje.
"""
import logging
import os
import random
import tempfile
from pathlib import Path
from typing import Optional

import requests

from config import GROQ_API_KEY  # noqa: F401  (asegura carga de .env vía config)

log = logging.getLogger(__name__)
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

# Banco de temas visuales (en inglés, que es lo que entiende Pexels) para clips
# que pegan con contenido de psicología/calma/curiosidad.
PEXELS_THEMES = [
    "calm nature", "ocean waves", "forest fog", "rain on window", "mountains aerial",
    "abstract motion", "slow motion water", "sunset sky", "minimal abstract loop",
    "city night timelapse", "coffee morning", "candle flame", "stars night sky",
    "person silhouette walking", "clouds timelapse",
]


# --------------------------- Pexels ---------------------------
def _pexels_search(query: str, per_page: int = 8) -> list[dict]:
    if not PEXELS_API_KEY:
        log.warning("PEXELS_API_KEY no configurada")
        return []
    try:
        r = requests.get(
            "https://api.pexels.com/videos/search",
            params={"query": query, "per_page": per_page, "orientation": "portrait"},
            headers={"Authorization": PEXELS_API_KEY}, timeout=12,
        )
        r.raise_for_status()
        return r.json().get("videos", [])
    except Exception as e:
        log.warning(f"Pexels search '{query}' falló: {e}")
        return []


def _pick_mp4(video: dict) -> Optional[str]:
    files = [f for f in video.get("video_files", []) if f.get("file_type") == "video/mp4"]
    # Preferimos vertical/cuadrado de calidad media (bueno para móvil), 480-1080 alto.
    files.sort(key=lambda f: abs((f.get("height") or 0) - 1080))
    return files[0].get("link") if files else None


def get_pexels_video(query: str = "", max_size_mb: int = 14) -> Optional[Path]:
    """Descarga un vídeo de stock de Pexels. Si no se da query, elige un tema al azar."""
    if not PEXELS_API_KEY:
        return None
    q = query or random.choice(PEXELS_THEMES)
    log.info(f"Pexels: buscando vídeo '{q}'")
    for v in _pexels_search(q):
        url = _pick_mp4(v)
        if not url:
            continue
        try:
            resp = requests.get(url, stream=True, timeout=20)
            resp.raise_for_status()
            length = int(resp.headers.get("content-length", "0"))
            if length and length > max_size_mb * 1024 * 1024:
                continue
            tmp = Path(tempfile.gettempdir()) / f"pexels_{v.get('id')}.mp4"
            with open(tmp, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            if tmp.stat().st_size < 200_000:
                tmp.unlink(missing_ok=True)
                continue
            log.info(f"Pexels vídeo OK: id={v.get('id')} ({tmp.stat().st_size} bytes)")
            return tmp
        except Exception as e:
            log.warning(f"Descarga Pexels falló: {e}")
    return None


# --------------------------- Reddit ---------------------------
def get_reddit_video(used_ids: set | None = None, attempts: int = 5,
                     min_ups: int = 3000) -> tuple[Optional[Path], dict]:
    """Descarga un vídeo viral de los subreddits de vídeo. Filtro por ups (clips
    YA validados como virales) + reintenta otro post si la descarga falla.
    Devuelve (ruta, post_dict)."""
    from reddit_fetcher import fetch_topic_post, download_media
    used = set(used_ids or set())
    for _ in range(attempts):
        post = fetch_topic_post("video", used_post_ids=used,
                                require_media=True, prefer_video=True,
                                min_ups=min_ups)
        if not post or post.get("media_type") != "video":
            # Si no hay nada con el umbral alto, relájalo en el último intento.
            if min_ups > 0:
                log.info(f"Sin clips ≥{min_ups} ups; relajando umbral a 1000.")
                min_ups = 1000
                continue
            break
        path = download_media(post["media_url"], "video")
        if path:
            return path, post
        # Descarga fallida: excluimos este post y probamos otro.
        if post.get("id"):
            used.add(post["id"])
        log.info(f"Descarga falló para r/{post.get('subreddit','')}; reintento otro clip.")
    return None, {}


# --------------------------- Orquestador ---------------------------
def get_video(prefer: str = "reddit", used_ids: set | None = None,
              pexels_query: str = "") -> tuple[Optional[Path], str, dict]:
    """Devuelve (ruta_video, fuente, meta). prefer = 'reddit' | 'pexels'.
    Intenta la fuente preferida y cae a la otra."""
    order = ["reddit", "pexels"] if prefer == "reddit" else ["pexels", "reddit"]
    for src in order:
        if src == "reddit":
            path, post = get_reddit_video(used_ids)
            if path:
                return path, "reddit", post
        else:
            path = get_pexels_video(pexels_query)
            if path:
                return path, "pexels", {}
    return None, "", {}


def extract_frame(video_path: Path, t: float = 1.0) -> Optional[Path]:
    """Extrae un fotograma del vídeo a PNG (para previsualizar sin reproducir)."""
    try:
        from moviepy import VideoFileClip
        out = Path(tempfile.gettempdir()) / f"frame_{abs(hash(str(video_path)))}.png"
        with VideoFileClip(str(video_path)) as clip:
            ts = min(t, max(0.0, clip.duration - 0.1))
            clip.save_frame(str(out), t=ts)
        return out
    except Exception as e:
        log.warning(f"No se pudo extraer fotograma: {e}")
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for pref in ("pexels", "reddit"):
        p, src, meta = get_video(prefer=pref)
        print(f"[{pref}] -> fuente={src} ruta={p}")
        if p:
            fr = extract_frame(p)
            print(f"    fotograma: {fr}")
