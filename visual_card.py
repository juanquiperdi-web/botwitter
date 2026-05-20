"""
Genera tarjetas visuales (PNG) para los posts: "texto sobre fondo".
Pensado para los listicles ("10 señales de…") y para citas/curiosidades.

El bot las adjunta al publicar (twitter_poster acepta image_path). El estilo vive
en STYLE para que el agente `disenador-visual` lo pueda afinar sin tocar la lógica.

Uso:
    from visual_card import render_listicle_card, render_quote_card
    path = render_listicle_card("7 señales de X", ["punto 1", "punto 2", ...])
    # -> Path a un PNG temporal listo para adjuntar
"""
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# ESTILO (editable por el agente disenador-visual)
# ---------------------------------------------------------------------------
STYLE = {
    "size": (1080, 1350),          # 4:5 vertical (formato que más ocupa en el feed)
    "bg_top": (24, 26, 48),        # degradado vertical: arriba
    "bg_bottom": (12, 16, 32),     # ...abajo
    "title_color": (255, 255, 255),
    "item_color": (223, 230, 242),
    "accent": (88, 166, 255),      # número de cada punto + línea bajo el título
    "footer_color": (130, 140, 165),
    "margin": 80,
    "title_size": 60,
    "item_size": 42,
    "footer_size": 30,
    "line_gap": 16,                # separación entre líneas del mismo punto
    "item_gap": 30,                # separación entre puntos
    "font_regular": "C:/Windows/Fonts/segoeui.ttf",
    "font_bold": "C:/Windows/Fonts/segoeuib.ttf",
    "footer": "",                  # handle/marca opcional, p.ej. "@tucuenta"
}


def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    path = STYLE["font_bold"] if bold else STYLE["font_regular"]
    return ImageFont.truetype(path, size)


def _gradient(size, top, bottom) -> Image.Image:
    w, h = size
    base = Image.new("RGB", size, top)
    draw = ImageDraw.Draw(base)
    for y in range(h):
        t = y / max(1, h - 1)
        col = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (w, y)], fill=col)
    return base


def _wrap(draw, text, font, max_w) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for wd in words:
        test = (cur + " " + wd).strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def _tmp_png() -> Path:
    f = tempfile.NamedTemporaryFile(prefix="card_", suffix=".png", delete=False)
    f.close()
    return Path(f.name)


def render_listicle_card(title: str, items: list[str], footer: str | None = None) -> Path:
    """Renderiza un listicle como tarjeta. Auto-reduce el tamaño de los puntos si
    no caben, para que SIEMPRE quepa todo en la imagen."""
    s = STYLE
    w, h = s["size"]
    margin = s["margin"]
    max_w = w - 2 * margin
    footer = footer if footer is not None else s["footer"]

    img = _gradient(s["size"], s["bg_top"], s["bg_bottom"])
    draw = ImageDraw.Draw(img)

    title_font = _font(True, s["title_size"])
    footer_font = _font(True, s["footer_size"])

    # Título (envuelto)
    title_lines = _wrap(draw, title, title_font, max_w)
    title_h = sum(title_font.getbbox(l)[3] - title_font.getbbox(l)[1] + 8 for l in title_lines)

    footer_h = (footer_font.getbbox(footer)[3] + 20) if footer else 0
    top_y = margin
    content_top = top_y + title_h + 40           # tras título + línea de acento
    content_bottom = h - margin - footer_h
    avail_h = content_bottom - content_top

    # Ajuste automático del tamaño de los puntos para que quepan.
    item_size = s["item_size"]
    while item_size >= 26:
        item_font = _font(False, item_size)
        num_font = _font(True, item_size)
        total = 0
        per_item_lines = []
        for it in items:
            wrapped = _wrap(draw, it, item_font, max_w - 70)  # 70px para el número
            per_item_lines.append(wrapped)
            lh = item_font.getbbox("Ag")[3] - item_font.getbbox("Ag")[1]
            total += len(wrapped) * (lh + s["line_gap"]) + s["item_gap"]
        if total <= avail_h:
            break
        item_size -= 3

    # --- Dibujo ---
    # Título
    y = top_y
    for l in title_lines:
        draw.text((margin, y), l, font=title_font, fill=s["title_color"])
        bb = title_font.getbbox(l)
        y += (bb[3] - bb[1]) + 8
    # Línea de acento bajo el título
    draw.rectangle([margin, y + 10, margin + 120, y + 16], fill=s["accent"])

    # Puntos numerados — pegados bajo el título (alineación superior, más cohesivo).
    y = content_top
    lh = item_font.getbbox("Ag")[3] - item_font.getbbox("Ag")[1]
    for idx, wrapped in enumerate(per_item_lines, 1):
        draw.text((margin, y), f"{idx}", font=num_font, fill=s["accent"])
        for j, line in enumerate(wrapped):
            draw.text((margin + 70, y), line, font=item_font, fill=s["item_color"])
            y += lh + s["line_gap"]
        y += s["item_gap"]

    # Footer
    if footer:
        draw.text((margin, h - margin - footer_font.getbbox(footer)[3]),
                  footer, font=footer_font, fill=s["footer_color"])

    out = _tmp_png()
    img.save(out, "PNG")
    return out


def render_quote_card(text: str, footer: str | None = None) -> Path:
    """Tarjeta de cita/curiosidad: un bloque de texto centrado verticalmente.
    Útil para curiosity / personality / sexo si se quiere imagen en vez de texto."""
    s = STYLE
    w, h = s["size"]
    margin = s["margin"]
    max_w = w - 2 * margin
    footer = footer if footer is not None else s["footer"]

    img = _gradient(s["size"], s["bg_top"], s["bg_bottom"])
    draw = ImageDraw.Draw(img)
    footer_font = _font(True, s["footer_size"])

    # Tamaño de fuente que haga que el texto ocupe bien sin desbordar.
    size = 64
    while size >= 34:
        font = _font(True, size)
        lines = _wrap(draw, text, font, max_w)
        lh = font.getbbox("Ag")[3] - font.getbbox("Ag")[1]
        block_h = len(lines) * (lh + 18)
        if block_h <= h - 2 * margin - 80:
            break
        size -= 4

    y = (h - block_h) // 2
    for line in lines:
        draw.text((margin, y), line, font=font, fill=s["title_color"])
        y += lh + 18

    if footer:
        draw.text((margin, h - margin - footer_font.getbbox(footer)[3]),
                  footer, font=footer_font, fill=s["footer_color"])

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
        footer="",
    )
    print("Listicle card:", p, p.stat().st_size, "bytes")
    q = render_quote_card(
        "Tu cerebro recuerda mejor lo que dejaste a medias que lo que terminaste. "
        "Por eso no puedes dejar de pensar en ese mensaje sin responder."
    )
    print("Quote card:", q, q.stat().st_size, "bytes")
