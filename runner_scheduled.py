"""
Ejecuta un único slot de publicación y termina.
Diseñado para ser invocado por el Programador de Tareas de Windows (cada 30 min).

Bot CAZA-NICHOS (psicología / autoconocimiento / relaciones). Cada slot del
TWEET_SCHEDULE (config.py) tiene un MODO:
- listicle     → "10 señales de…" (hilo)
- personality  → "lo que tu forma de X dice de ti"
- curiosity    → dato curioso de comportamiento (Reddit o LLM)
- sexo         → psicología de atracción/relaciones (tono adulto, no explícito)
- country_data → "media por país" con datos reales del Banco Mundial
"""
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
os.chdir(SCRIPT_DIR)
sys.path.insert(0, str(SCRIPT_DIR))

from config import TWEET_SCHEDULE

LOG_FILE = SCRIPT_DIR / "bot.log"
STATE_FILE = SCRIPT_DIR / "publish_state.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(LOG_FILE), encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _today_key() -> str:
    return date.today().isoformat()


# Ventana de deduplicación (días). Aplica a reddit_ids y media_keys para evitar
# repetir el mismo clip (o crossposts del mismo vídeo) durante este periodo.
DEDUP_DAYS = 14


def _used_post_ids(days: int = DEDUP_DAYS) -> set:
    """IDs de posts de Reddit ya publicados en los últimos N días."""
    state = _load_state()
    used = set()
    for k, v in state.items():
        if k.endswith("_reddit_ids") and isinstance(v, list):
            used.update(v)
    return used


def _used_media_keys(days: int = DEDUP_DAYS) -> set:
    """Claves de media (p.ej. ID de v.redd.it) ya publicadas en los últimos N días.
    Sirve para no repetir el MISMO vídeo aunque venga de otro subreddit (crossposts)."""
    state = _load_state()
    used = set()
    for k, v in state.items():
        if k.endswith("_media_keys") and isinstance(v, list):
            used.update(v)
    return used


def _mark_published(slot: int, post_id: str = "", media_key: str = "") -> None:
    today = _today_key()
    from datetime import date, timedelta
    today_dt = date.today()
    # Conservamos los últimos DEDUP_DAYS + 1 días para que la ventana de dedup
    # tenga datos suficientes.
    valid_prefixes = {(today_dt - timedelta(days=d)).isoformat() for d in range(DEDUP_DAYS + 1)}
    state = _load_state()
    state = {k: v for k, v in state.items() if any(k.startswith(p) for p in valid_prefixes)}
    state.setdefault(today, [])
    if slot not in state[today]:
        state[today].append(slot)
    if post_id:
        state.setdefault(today + "_reddit_ids", [])
        if post_id not in state[today + "_reddit_ids"]:
            state[today + "_reddit_ids"].append(post_id)
    if media_key:
        state.setdefault(today + "_media_keys", [])
        if media_key not in state[today + "_media_keys"]:
            state[today + "_media_keys"].append(media_key)
    _save_state(state)


def _slot_key_to_minutes(key) -> int:
    """Convierte 'HH:MM' o int (hora) en minutos desde medianoche."""
    if isinstance(key, int):
        return key * 60
    h, m = key.split(":")
    return int(h) * 60 + int(m)


def _pick_slot():
    """Devuelve (slot_key, (mode, topic)) del slot pendiente más antiguo de hoy.
    Si un slot tiene >90 min desde su hora programada, se descarta del candidato
    pool (evita bloquear el día entero si un slot concreto falla repetidamente)."""
    now = datetime.now()
    now_minutes = now.hour * 60 + now.minute
    today = _today_key()
    state = _load_state()
    published_today = set(state.get(today, []))
    attempted_today = set(state.get(today + "_attempted", []))

    candidates = []
    for k in TWEET_SCHEDULE:
        slot_min = _slot_key_to_minutes(k)
        if slot_min > now_minutes:
            continue
        if k in published_today or k in attempted_today:
            continue
        # Si la ventana del slot ya pasó (>90 min), lo descartamos del día
        if now_minutes - slot_min > 90:
            continue
        candidates.append(k)
    candidates.sort(key=_slot_key_to_minutes)

    if not candidates:
        log.info(
            f"{now.strftime('%H:%M')}: nada pendiente. "
            f"Publicados: {sorted(published_today, key=_slot_key_to_minutes)} | "
            f"Intentados sin éxito: {sorted(attempted_today, key=_slot_key_to_minutes)}"
        )
        return None

    slot = candidates[0]
    return slot, TWEET_SCHEDULE[slot]


def _mark_attempted(slot) -> None:
    """Marca un slot como intentado-fallido (no vuelve a tomarlo hoy)."""
    today = _today_key()
    state = _load_state()
    state.setdefault(today + "_attempted", [])
    if slot not in state[today + "_attempted"]:
        state[today + "_attempted"].append(slot)
    _save_state(state)


def _recent_angles(days: int = 5) -> set:
    """Ángulos/títulos usados en los últimos N días (anti-repetición)."""
    state = _load_state()
    used = set()
    for k, v in state.items():
        if k.endswith("_niche_titles") and isinstance(v, list):
            used.update(v)
    return used


def _mark_niche_title(title: str) -> None:
    today = _today_key()
    from datetime import date, timedelta
    valid = {(date.today() - timedelta(days=d)).isoformat() for d in range(5)}
    state = _load_state()
    state = {k: v for k, v in state.items()
             if not k.endswith("_niche_titles") or k.split("_niche_titles")[0] in valid}
    key = today + "_niche_titles"
    state.setdefault(key, [])
    if title not in state[key]:
        state[key].append(title)
    _save_state(state)


def run_listicle_post() -> bool:
    """Publica un listicle de psicología ('10 hábitos de…') como hilo."""
    import random
    from niche_generator import (
        generate_listicle, render_listicle_thread, LISTICLE_ANGLES,
    )
    from twitter_poster import post_thread

    n = random.choice([6, 7, 7, 8, 9, 10])  # número de puntos variado
    # Elige un ángulo no usado recientemente.
    used = _recent_angles()
    fresh = [a for a in LISTICLE_ANGLES if a[0].format(n=n) not in used]
    angle = random.choice(fresh) if fresh else random.choice(LISTICLE_ANGLES)

    try:
        data = generate_listicle(n=n, angle=angle)
    except Exception as e:
        log.error(f"Listicle generación falló: {e}")
        return False

    # Formato preferido: TARJETA VISUAL (texto sobre fondo) + caption con la pregunta.
    try:
        from visual_card import render_listicle_card
        from twitter_poster import post_tweet
        card = render_listicle_card(data["raw_title"], data["items"])
        caption = data.get("cta", "").strip() or "¿Cuántas cumples?"
        log.info(f"Listicle (tarjeta): '{data['raw_title']}' | caption: {caption}")
        result = post_tweet(caption, image_path=card)
        log.info(f"Listicle (imagen) publicado: id={result}")
        _mark_niche_title(data["raw_title"])
        return True
    except Exception as e:
        log.warning(f"Listicle imagen falló ({e}); caigo a hilo de texto.")

    # Respaldo: hilo de texto.
    tweets = render_listicle_thread(data)
    log.info(f"Listicle (texto): '{data['raw_title']}' → {len(tweets)} tweets")
    try:
        result = post_thread(tweets)
        log.info(f"Listicle publicado: id={result}")
        _mark_niche_title(data["raw_title"])
        return True
    except Exception as e:
        log.error(f"Listicle post falló: {e}")
        return False


def run_personality_post() -> bool:
    """Publica un gancho de personalidad ('lo que tu forma de X dice de ti')."""
    from niche_generator import generate_personality_post
    from twitter_poster import post_tweet
    try:
        text = generate_personality_post()
    except Exception as e:
        log.error(f"Personality generación falló: {e}")
        return False
    log.info(f"Personality ({len(text)} chars):\n{text}")
    try:
        result = post_tweet(text)
        log.info(f"Personality publicado: id={result}")
        return True
    except Exception as e:
        log.error(f"Personality post falló: {e}")
        return False


def run_sex_post() -> bool:
    """Publica un post de psicología de la atracción/relaciones (tema sexo, no explícito)."""
    import random
    from niche_generator import generate_sex_post, SEX_ANGLES
    from twitter_poster import post_tweet
    used = _recent_angles()
    fresh = [a for a in SEX_ANGLES if f"sexo:{a}" not in used] or SEX_ANGLES
    angle = random.choice(fresh)
    try:
        text = generate_sex_post(angle)
    except Exception as e:
        log.error(f"Sex generación falló: {e}")
        return False
    log.info(f"Sex ({len(text)} chars):\n{text}")
    try:
        result = post_tweet(text)
        log.info(f"Sex publicado: id={result}")
        _mark_niche_title(f"sexo:{angle}")
        return True
    except Exception as e:
        log.error(f"Sex post falló: {e}")
        return False


def run_curiosity_post() -> bool:
    """Publica un dato curioso de psicología. Intenta fuente de Reddit; si no, LLM puro."""
    from niche_generator import generate_curiosity_post
    from twitter_poster import post_tweet
    source = None
    try:
        from reddit_fetcher import fetch_topic_post
        source = fetch_topic_post("psicologia", used_post_ids=_used_post_ids(),
                                  require_media=False, prefer_video=False)
    except Exception as e:
        log.info(f"Curiosity sin fuente Reddit ({e}); uso LLM puro.")

    try:
        text = generate_curiosity_post(source)
    except Exception as e:
        log.error(f"Curiosity generación falló: {e}")
        return False
    log.info(f"Curiosity ({len(text)} chars):\n{text}")
    try:
        result = post_tweet(text)
        log.info(f"Curiosity publicado: id={result}")
        if source and source.get("id"):
            _mark_published(0, post_id=source["id"])
        return True
    except Exception as e:
        log.error(f"Curiosity post falló: {e}")
        return False


def run_country_data_post() -> bool:
    """Publica un ranking 'media por país' con datos reales del Banco Mundial.
    Rota de indicador (anti-repetición 5 días). El LLM solo escribe el cierre."""
    import random
    from agentes.country_data import INDICATORS, build_country_ranking
    from twitter_poster import post_thread
    from niche_generator import client, MODEL

    used = _recent_angles()
    codes = [c for c in INDICATORS if f"pais:{c}" not in used] or list(INDICATORS)
    random.shuffle(codes)

    data = None
    chosen = None
    for code in codes:                 # prueba indicadores hasta que uno traiga datos
        data = build_country_ranking(code, top=10)
        if data:
            chosen = code
            break
    if not data:
        log.error("country_data: ningún indicador devolvió datos")
        return False

    header = f"{data['title']} por país ({data['year']}):"
    body = "\n".join(data["lines"])

    # Cierre LLM: observación + pregunta, SIN inventar cifras nuevas.
    closing = "¿Te sorprende algún puesto?"
    try:
        sys_msg = (
            "Eres un divulgador en castellano. Recibes un ranking real por país. "
            "Escribe SOLO una línea de cierre (50-130 chars) con una observación breve "
            "y una pregunta que invite a comentar. PROHIBIDO inventar cifras nuevas, "
            "repetir el ranking, usar hashtags o emojis."
        )
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": sys_msg},
                      {"role": "user", "content": f"Ranking: {data['title']}\n{body}\n\nLínea de cierre:"}],
            max_tokens=120, temperature=0.8,
        )
        c = resp.choices[0].message.content.strip()
        if c and c[0] in '"«' and c[-1] in '"»':
            c = c[1:-1].strip()
        if c:
            closing = c
    except Exception as e:
        log.warning(f"country_data cierre LLM falló: {e}")

    # Reparte el ranking en tweets <=275 chars (header en el 1º). Las 10 líneas
    # con banderas no caben en un solo tweet, así que se hace hilo.
    src = f"Datos: {data['source']}"
    extra = []
    if data["spain_line"]:
        extra.append(data["spain_line"])
    extra.append(closing)
    extra.append(src)

    tweets, cur, first = [], [], True
    for line in data["lines"]:
        prospective = (header + "\n\n" if first and not cur else "") + "\n".join(cur + [line])
        if len(prospective) > 270 and cur:
            tweets.append(((header + "\n\n" if first else "") + "\n".join(cur)).rstrip())
            first, cur = False, [line]
        else:
            cur.append(line)
    if cur:
        tweets.append(((header + "\n\n" if first else "") + "\n".join(cur)).rstrip())

    # Cuelga spain/closing/source al final, creando tweet extra si no caben.
    for piece in extra:
        if len(tweets[-1]) + 2 + len(piece) <= 275:
            tweets[-1] += "\n\n" + piece
        else:
            tweets.append(piece)
    if len(tweets) > 1:
        tweets[0] += "\n\n↓"

    for i, t in enumerate(tweets):
        log.info(f"country_data tweet{i+1} ({len(t)} chars):\n{t}")

    try:
        result = post_thread(tweets)
        log.info(f"country_data publicado: id={result}")
        _mark_niche_title(f"pais:{chosen}")
        return True
    except Exception as e:
        log.error(f"country_data post falló: {e}")
        return False


def run_video_post() -> bool:
    """Publica un VÍDEO (Reddit viral, Pexels de respaldo) con un caption corto
    variado (curiosidad / personalidad / atracción)."""
    from video_source import get_video
    from twitter_poster import post_tweet
    from niche_generator import generate_viral_hook

    # 1) Vídeo: Reddit primero (viral, con título), Pexels de respaldo.
    # Filtra por IDs Y media (clave de v.redd.it) ya usados en los últimos 14 días.
    from video_source import media_key
    path, src, post = get_video(
        prefer="reddit",
        used_ids=_used_post_ids(),
        used_media=_used_media_keys(),
    )
    if not path:
        log.error("Video: ninguna fuente devolvió vídeo")
        return False

    # 2) Caption corto y enganchón que REACCIONA al clip (usa su título original).
    clip_title = post.get("title", "") if src == "reddit" else ""
    try:
        caption = generate_viral_hook(clip_title)
    except Exception as e:
        log.error(f"Video caption (hook) falló: {e}")
        return False
    log.info(f"Video post: fuente={src} | clip='{clip_title[:50]}' | caption={caption!r}")

    # 3) Publicar vídeo + caption.
    try:
        result = post_tweet(caption, video_path=path)
        log.info(f"Video publicado: id={result} (fuente {src})")
        if post.get("id") or post.get("media_url"):
            _mark_published(0, post_id=post.get("id", ""),
                            media_key=media_key(post.get("media_url", "")))
        return True
    except Exception as e:
        log.error(f"Video post falló: {e}")
        return False


# Mapa modo -> función de ejecución. Añadir un formato nuevo = una línea aquí.
RUNNERS = {
    "video":        run_video_post,
    "listicle":     run_listicle_post,
    "personality":  run_personality_post,
    "curiosity":    run_curiosity_post,
    "sexo":         run_sex_post,
    "country_data": run_country_data_post,
}


def _publish_from_queue(mode: str) -> bool:
    """Intenta publicar un item de la COLA de contenido (lo que dejan los agentes
    de Claude Code). Devuelve True si publicó; False si la cola no tenía nada de
    ese modo o falló la publicación (en cuyo caso main() cae a la generación Groq)."""
    try:
        from queue_manager import pop_item, add_items
    except Exception as e:
        log.warning(f"queue_manager no disponible ({e}); uso generación propia.")
        return False

    item = pop_item(mode)
    if not item:
        return False

    tweets = item["tweets"]
    log.info(f"[COLA] Publicando item {item.get('id')} (modo={mode}, {len(tweets)} tweets, fuente={item.get('source')})")
    try:
        from twitter_poster import post_tweet, post_thread
        result = post_thread(tweets) if len(tweets) > 1 else post_tweet(tweets[0])
        log.info(f"[COLA] Publicado: id={result}")
        if item.get("title"):
            _mark_niche_title(item["title"])
        return True
    except Exception as e:
        log.error(f"[COLA] Falló la publicación del item; lo devuelvo a la cola: {e}")
        # Reencola el item para no perderlo; main() caerá a generación Groq este slot.
        try:
            add_items(item)
        except Exception:
            pass
        return False


def main():
    pick = _pick_slot()
    if pick is None:
        return
    slot, (mode, topic) = pick
    log.info(f"=== Slot {slot} (modo={mode}, tema={topic}) ===")

    runner = RUNNERS.get(mode)
    if runner is None:
        log.error(f"Modo desconocido '{mode}' en el slot {slot}; nada que publicar.")
        _mark_attempted(slot)
        return

    # 1) Primero la COLA (contenido vetado por los agentes de Claude).
    # 2) Si está vacía, generación propia con Groq (degradación elegante).
    if _publish_from_queue(mode) or runner():
        _mark_published(slot)
    else:
        _mark_attempted(slot)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log.error(f"Error: {e}", exc_info=True)
