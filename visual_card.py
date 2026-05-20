"""
Tarjetas visuales (PNG) para los posts: diseño en HTML/CSS renderizado a imagen
con Playwright (Chromium headless) → calidad tipo Canva. Si Playwright falla,
cae a un render simple con Pillow (respaldo).

El bot las adjunta al publicar. El diseño vive en THEME + el template HTML, para
que el agente `disenador-visual` lo afine sin tocar la lógica.

    from visual_card import render_listicle_card, render_quote_card
    path = render_listicle_card("7 señales de X", ["punto 1", "punto 2", ...])
"""
import html as _html
import logging
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TEMA (editable por el agente disenador-visual). Paleta y tipografía.
# ---------------------------------------------------------------------------
THEME = {
    # Degradado de fondo (diagonal). Vivo pero adulto.
    "bg": "linear-gradient(135deg, #5b2a86 0%, #2b3a9e 55%, #1f6fb2 100%)",
    "title_color": "#ffffff",
    "item_color": "#eaf0ff",
    "badge_bg": "linear-gradient(135deg, #ffd24d 0%, #ff8a3d 100%)",  # insignia número
    "badge_text": "#2a1a4a",
    "accent": "#ffd24d",          # línea de acento bajo el título
    "footer_color": "rgba(255,255,255,0.55)",
    "font": "'Poppins', 'Segoe UI', system-ui, sans-serif",
    "handle": "",                 # p.ej. "@tucuenta" — vacío = sin pie
}

W, H = 1080, 1350


def _tmp_png() -> Path:
    f = tempfile.NamedTemporaryFile(prefix="card_", suffix=".png", delete=False)
    f.close()
    return Path(f.name)


def _sizes(n_items: int) -> tuple[int, int]:
    """Tamaño de fuente (título, puntos) según cuántos puntos haya, para que quepa."""
    if n_items <= 6:
        return 60, 40
    if n_items <= 8:
        return 56, 35
    return 52, 30


def _listicle_html(title: str, items: list[str]) -> str:
    t = THEME
    title_size, item_size = _sizes(len(items))
    rows = "\n".join(
        f'<li><span class="badge">{i}</span><span class="txt">{_html.escape(it)}</span></li>'
        for i, it in enumerate(items, 1)
    )
    handle = (
        f'<div class="footer">{_html.escape(t["handle"])}</div>' if t["handle"] else ""
    )
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap" rel="stylesheet">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:{W}px; height:{H}px; }}
  body {{
    background:{t['bg']}; font-family:{t['font']};
    padding:90px 80px; display:flex; flex-direction:column;
  }}
  h1 {{
    color:{t['title_color']}; font-weight:800; font-size:{title_size}px;
    line-height:1.12; letter-spacing:-0.5px; margin-bottom:18px;
  }}
  .rule {{ width:130px; height:8px; border-radius:8px; background:{t['accent']}; margin-bottom:44px; }}
  ul {{ list-style:none; display:flex; flex-direction:column; gap:26px; }}
  li {{ display:flex; align-items:center; gap:26px; }}
  .badge {{
    flex:0 0 auto; width:62px; height:62px; border-radius:50%;
    background:{t['badge_bg']}; color:{t['badge_text']};
    font-weight:800; font-size:30px; display:flex; align-items:center; justify-content:center;
    box-shadow:0 6px 18px rgba(0,0,0,0.25);
  }}
  .txt {{ color:{t['item_color']}; font-weight:600; font-size:{item_size}px; line-height:1.25; }}
  .footer {{ margin-top:auto; color:{t['footer_color']}; font-weight:600; font-size:30px; }}
</style></head>
<body>
  <h1>{_html.escape(title)}</h1>
  <div class="rule"></div>
  <ul>{rows}</ul>
  {handle}
</body></html>"""


def _quote_html(text: str) -> str:
    t = THEME
    handle = (
        f'<div class="footer">{_html.escape(t["handle"])}</div>' if t["handle"] else ""
    )
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@600;800&display=swap" rel="stylesheet">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:{W}px; height:{H}px; }}
  body {{ background:{t['bg']}; font-family:{t['font']}; padding:110px 90px;
          display:flex; flex-direction:column; justify-content:center; }}
  .quote {{ color:{t['title_color']}; font-weight:800; font-size:62px; line-height:1.3; letter-spacing:-0.5px; }}
  .footer {{ position:absolute; bottom:90px; left:90px; color:{t['footer_color']}; font-weight:600; font-size:30px; }}
</style></head>
<body><div class="quote">{_html.escape(text)}</div>{handle}</body></html>"""


def _render_html(html_str: str) -> Path:
    """Renderiza un HTML a PNG 1080x1350 con Playwright (Chromium headless)."""
    from playwright.sync_api import sync_playwright
    out = _tmp_png()
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": W, "height": H},
                                device_scale_factor=2)
        page.set_content(html_str, wait_until="networkidle")
        try:
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(250)
        except Exception:
            pass
        page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": W, "height": H})
        browser.close()
    return out


def render_listicle_card(title: str, items: list[str], footer: str | None = None) -> Path:
    if footer is not None:
        THEME["handle"] = footer
    try:
        return _render_html(_listicle_html(title, items))
    except Exception as e:
        log.warning(f"Render HTML falló ({e}); uso respaldo Pillow.")
        return _render_listicle_pillow(title, items)


def render_quote_card(text: str, footer: str | None = None) -> Path:
    if footer is not None:
        THEME["handle"] = footer
    try:
        return _render_html(_quote_html(text))
    except Exception as e:
        log.warning(f"Render HTML (quote) falló ({e}); uso respaldo Pillow.")
        return _render_listicle_pillow(text, [])


# ---------------------------------------------------------------------------
# RESPALDO Pillow (por si Playwright no está disponible). Diseño simple.
# ---------------------------------------------------------------------------
def _render_listicle_pillow(title: str, items: list[str]) -> Path:
    from PIL import Image, ImageDraw, ImageFont
    bg_top, bg_bottom = (40, 30, 70), (25, 35, 90)
    img = Image.new("RGB", (W, H), bg_top)
    draw = ImageDraw.Draw(img)
    for y in range(H):
        tt = y / (H - 1)
        draw.line([(0, y), (W, y)],
                  fill=tuple(int(bg_top[i] + (bg_bottom[i] - bg_top[i]) * tt) for i in range(3)))
    tf = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 58)
    itf = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 40)
    margin = 80

    def wrap(txt, font, mw):
        words, lines, cur = txt.split(), [], ""
        for w in words:
            if draw.textlength((cur + " " + w).strip(), font=font) <= mw:
                cur = (cur + " " + w).strip()
            else:
                lines.append(cur); cur = w
        if cur:
            lines.append(cur)
        return lines

    y = margin
    for ln in wrap(title, tf, W - 2 * margin):
        draw.text((margin, y), ln, font=tf, fill=(255, 255, 255)); y += 66
    draw.rectangle([margin, y + 8, margin + 120, y + 16], fill=(255, 210, 77)); y += 60
    for i, it in enumerate(items, 1):
        draw.text((margin, y), f"{i}", font=tf, fill=(255, 210, 77))
        for ln in wrap(it, itf, W - 2 * margin - 70):
            draw.text((margin + 70, y), ln, font=itf, fill=(234, 240, 255)); y += 52
        y += 24
    out = _tmp_png()
    img.save(out, "PNG")
    return out


if __name__ == "__main__":
    p = render_listicle_card(
        "7 señales de que alguien es más inteligente de lo que aparenta",
        [
            "Escucha mucho más de lo que habla",
            "Admite sin problema cuando no sabe algo",
            "Hace preguntas en vez de dar sermones",
            "Cambia de opinión ante buenos argumentos",
            "No necesita demostrar que tiene razón",
            "Se ríe de sí mismo con facilidad",
            "Observa antes de opinar",
        ],
    )
    print("Listicle card:", p, p.stat().st_size, "bytes")
