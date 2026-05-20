"""
Cola de contenido (puente entre los AGENTES de Claude Code y el bot Python).

Los agentes (curador-cola, redactor-posts, revisor-engagement) generan y vetan
posts y los DEPOSITAN aquí. El bot (`runner_scheduled.py`), en cada disparo,
SACA el siguiente post del modo que toca y lo publica. Si la cola está vacía,
el bot cae a su generación propia con Groq (degradación elegante).

Formato de cada item:
{
  "id": "listicle-1716200000",
  "mode": "listicle|personality|curiosity|sexo|country_data",
  "tweets": ["texto tweet 1", "texto tweet 2", ...],   # 1 = post simple, >1 = hilo
  "title": "etiqueta para anti-repetición (opcional)",
  "added": "2026-05-20T08:00:00",
  "source": "curador"
}

CLI (para que los agentes la llenen de forma fiable y validada):
  python queue_manager.py add-file ruta.json   # ingiere [{item}, ...] o {item}
  python queue_manager.py status                # cuántos hay por modo
  python queue_manager.py list                  # vuelca la cola
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

QUEUE_FILE = Path(__file__).parent / "content_queue.json"

VALID_MODES = {"listicle", "personality", "curiosity", "sexo", "country_data"}
TWEET_LIMIT = 280


def load_queue() -> list[dict]:
    if QUEUE_FILE.exists():
        try:
            data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
            return data.get("items", []) if isinstance(data, dict) else []
        except Exception:
            return []
    return []


def save_queue(items: list[dict]) -> None:
    QUEUE_FILE.write_text(
        json.dumps({"items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def validate_item(item: dict) -> tuple[bool, str]:
    """Devuelve (ok, motivo). No muta el item."""
    mode = item.get("mode")
    if mode not in VALID_MODES:
        return False, f"modo inválido: {mode!r} (válidos: {sorted(VALID_MODES)})"
    tweets = item.get("tweets")
    if not isinstance(tweets, list) or not tweets:
        return False, "'tweets' debe ser una lista no vacía"
    for i, t in enumerate(tweets):
        if not isinstance(t, str) or not t.strip():
            return False, f"tweet {i+1} vacío o no es texto"
        if len(t) > TWEET_LIMIT:
            return False, f"tweet {i+1} excede {TWEET_LIMIT} chars ({len(t)})"
    return True, "ok"


def add_items(new_items) -> tuple[int, list[str]]:
    """Añade uno o varios items validados. Devuelve (añadidos, errores)."""
    if isinstance(new_items, dict):
        new_items = [new_items]
    items = load_queue()
    added, errors = 0, []
    for it in new_items:
        ok, why = validate_item(it)
        if not ok:
            errors.append(why)
            continue
        it.setdefault("id", f"{it['mode']}-{int(time.time()*1000)}")
        it.setdefault("added", datetime.now().isoformat(timespec="seconds"))
        it.setdefault("source", "agente")
        items.append(it)
        added += 1
    save_queue(items)
    return added, errors


def pop_item(mode: str | None = None) -> dict | None:
    """Saca (y elimina) el item más antiguo del modo dado (o cualquiera si None).
    Devuelve None si no hay nada."""
    items = load_queue()
    for idx, it in enumerate(items):
        if mode is None or it.get("mode") == mode:
            chosen = items.pop(idx)
            save_queue(items)
            return chosen
    return None


def counts() -> dict:
    items = load_queue()
    out = {}
    for it in items:
        out[it.get("mode", "?")] = out.get(it.get("mode", "?"), 0) + 1
    return out


def _cli():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "add-file":
        path = Path(sys.argv[2])
        payload = json.loads(path.read_text(encoding="utf-8"))
        added, errors = add_items(payload)
        print(f"Añadidos: {added}")
        for e in errors:
            print(f"  RECHAZADO: {e}")
        print("Cola por modo:", counts())
    elif cmd == "status":
        print("Cola por modo:", counts(), "| total:", sum(counts().values()))
    elif cmd == "list":
        print(json.dumps({"items": load_queue()}, ensure_ascii=False, indent=2))
    elif cmd == "clear":
        save_queue([])
        print("Cola vaciada.")
    else:
        print(f"Comando desconocido: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    _cli()
