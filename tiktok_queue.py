"""
Cola de TikTok: tras publicar un vídeo en X, el bot COPIA el .mp4 y deja un
.txt con el caption en C:\\Users\\34696\\tiktok_queue\\ para que tú lo subas
manualmente desde el navegador (tiktok.com/upload).

Naming: AAAA-MM-DD_HH-MM_slug.mp4 y mismo nombre .txt.
Limpieza automática: borra archivos de más de 7 días para no acumular.
"""
import logging
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

# Carpeta de la cola (raíz del usuario, fácil de encontrar)
QUEUE_DIR = Path.home() / "tiktok_queue"
KEEP_DAYS = 7   # días que conserva los .mp4/.txt antes de borrarlos

# CTAs rotativos al final del caption (TikTok → manda gente a X).
# Misma intención, distintas formas para no sonar repetitivo en el feed.
TIKTOK_CTAS = [
    "Síguenos en X → @armentero85022",
    "Más clips en X → @armentero85022",
    "🐾 X: @armentero85022",
    "Cada día más en X → @armentero85022",
    "Si te ríes, en X hay más → @armentero85022",
]


def _pick_cta() -> str:
    import random
    return random.choice(TIKTOK_CTAS)


def _slug(text: str) -> str:
    """Slug seguro para nombres de archivo en Windows."""
    if not text:
        return "clip"
    # Quita caracteres prohibidos en NTFS y limita longitud.
    s = re.sub(r"[^\w\s.-]", "", text, flags=re.UNICODE).strip()
    s = re.sub(r"\s+", "-", s)
    return (s[:40] or "clip")


def _prune_old(days: int = KEEP_DAYS) -> None:
    cutoff = time.time() - days * 86400
    if not QUEUE_DIR.exists():
        return
    for f in QUEUE_DIR.iterdir():
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
        except Exception as e:
            log.warning(f"No pude borrar {f.name}: {e}")


def save_for_tiktok(video_path: Path, caption: str, source_title: str = "") -> Path | None:
    """Copia el .mp4 publicado a la cola y escribe un .txt con el caption.
    Devuelve la ruta del .mp4 copiado (o None si falla)."""
    try:
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        _prune_old()
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        slug = _slug(source_title)
        base = f"{stamp}_{slug}"
        dest_mp4 = QUEUE_DIR / f"{base}.mp4"
        dest_txt = QUEUE_DIR / f"{base}.txt"
        # Si chocan nombres (poco probable), añade segundos
        if dest_mp4.exists():
            stamp2 = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            base = f"{stamp2}_{slug}"
            dest_mp4 = QUEUE_DIR / f"{base}.mp4"
            dest_txt = QUEUE_DIR / f"{base}.txt"
        shutil.copy2(str(video_path), str(dest_mp4))
        # Caption + CTA rotativo para que TikTok mande gente a X.
        full_caption = caption.strip() + "\n\n" + _pick_cta() + "\n"
        dest_txt.write_text(full_caption, encoding="utf-8")
        log.info(f"[TikTok queue] guardado: {dest_mp4.name}")
        return dest_mp4
    except Exception as e:
        log.warning(f"[TikTok queue] no se pudo guardar: {e}")
        return None
