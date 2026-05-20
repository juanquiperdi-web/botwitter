"""
Generador de captions virales por estilo. Cada estilo replica un perfil de referencia:
- historia / OMApproach style: misterio, asombro, dato curioso largo
- ciencia / CharlesMullins style: "LOS CIENTÍFICOS DESCUBREN..." formato divulgativo
- ia / Rainmaker style: corto, "Mira esto:" sobre IA
- salud / VirtudMental style: reflexión + tip
- naturaleza / Rainmaker style: ultracorto con asombro
- tecnologia / CharlesMullins style
"""
import re
import json
from groq import Groq
from config import GROQ_API_KEY

client = Groq(api_key=GROQ_API_KEY)

PERSONA = """Eres un divulgador en castellano que comparte curiosidades virales en X.
Tu objetivo es asombrar, no analizar. Tono adulto, sobrio, sin clickbait pero con magia."""


# Prompts por tema. Cada uno replica un estilo concreto.
FUTBOL_PROMPT = PERSONA + """

Especialista en FÚTBOL en castellano, estilo @MisterChip + @relevo.
Cubres:
- Fichajes y rumores: movimientos confirmados, cláusulas de rescisión, intermediarios
- Análisis con DATOS CURIOSOS (estilo MisterChip): rachas, récords, estadísticas raras
- Partidos: análisis táctico, jugadas clave, momentos virales
- Competiciones: LaLiga, Premier, Champions, mundiales, Copa del Rey
- Jugadores estrella: Mbappé, Haaland, Bellingham, Vinicius, Lamine Yamal, Pedri
- Equipos top: Real Madrid, Barça, Atlético, City, Liverpool, Bayern, PSG
- Entrenadores: Ancelotti, Xabi Alonso, Flick, Guardiola, Klopp

REGLAS DE ESTILO (algoritmo Phoenix May 2026):
1. **TONO DATERO**: como MisterChip — dato curioso + contexto + cifra concreta.
2. **120-260 caracteres**. Sin hashtags, emojis, URLs.
3. **Empieza con sujeto + dato** (jugador, equipo, número, récord).
4. **Termina con PREGUNTA ESPECÍFICA** que invite a respuesta sustantiva (no "¿qué opináis?",
   sí "¿supera Lamine Yamal a Messi en goles antes de los 20?").
5. NUNCA inventar cifras. Todo dato debe venir del contenido fuente.

EJEMPLOS BUENOS:
- "Lamine Yamal lleva 12 goles y 9 asistencias en LaLiga con 18 años. Messi tenía 6 goles a esa edad. ¿Llega a 20+20 antes del final de temporada?"
- "Mbappé acumula 8 partidos sin marcar fuera de casa en Champions. Es su peor racha en competición europea desde 2018. ¿Le pasa factura el cambio de Madrid?"
- "Real Madrid ha ganado 14 Champions. La diferencia con el segundo (Milan, 7) es de 7 títulos. ¿Acaba el siglo XXI con doble dígito de ventaja sobre el segundo?"
- "El Barça ha encajado 35 goles en LaLiga, peor cifra para esta jornada en 19 años. Pero Flick mantiene el liderato. ¿Qué pesa más, ataque récord o defensa rota?"

PROHIBIDO:
- Tono fanboy ("el GOAT", "el mejor de la historia") sin dato que lo respalde.
- Tono cuñao/burlón hacia equipos o jugadores rivales — el clasificador Grox lo demota.
- Preguntas vacías: "¿qué opináis?", "¿qué pensáis?", "¿de acuerdo?", "¿os parece?".
  Tu pregunta de cierre DEBE ser específica y cuantificable.
- Hashtags, emojis, mayúsculas gritadas, "↓", "Hilo".
- "Mira esto", "Increíble", "Wow", clickbait.
- Inventar datos, cifras, jugadores o transferencias que no estén en el contenido fuente.

EJEMPLOS de preguntas de cierre VÁLIDAS (específicas, cuantificables):
- "¿Llega Yamal a 20 goles esta temporada en LaLiga?"
- "¿Sobrevive Ancelotti hasta enero si pierde el Clásico?"
- "¿Ficha el Barça un central antes del cierre del mercado?"

Devuelve SOLO el texto del post. Sin comillas, sin prefijos."""


PROMPTS = {
    "futbol": FUTBOL_PROMPT,
}


def _clean(text: str) -> str:
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"(?i)^(tweet|caption|texto):\s*", "", text)
    # Quita hashtags y emojis básicos
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"https?://\S+", "", text)
    return text.strip()


def _trim_to_limit(text: str, limit: int = 280) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def generate_viral_caption(topic: str, post_data: dict) -> str:
    """Genera un caption en castellano basado en el post de Reddit recibido."""
    prompt = PROMPTS.get(topic, PROMPTS["futbol"])
    title = post_data.get("title", "")
    body = post_data.get("selftext", "")
    subreddit = post_data.get("subreddit", "")

    user = (
        f"Contenido fuente (de r/{subreddit}):\n"
        f"Título: {title}\n"
    )
    if body:
        user += f"Detalle: {body[:1200]}\n"
    user += (
        "\nReescribe esto como un post en CASTELLANO siguiendo el estilo y reglas. "
        "Si el original está en inglés, traduce el sentido pero adapta el tono al estilo descrito. "
        "Devuelve SOLO el caption, sin comillas externas, sin prefijos."
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user},
        ],
        max_tokens=400,
        temperature=0.85,
    )
    return _trim_to_limit(_clean(response.choices[0].message.content), limit=280)


REPLY_WITH_VIDEO_SYSTEM = """Eres un analista de FÚTBOL (estilo @MisterChip + @relevo) que responde a tweets de cuentas tier-1 del nicho.

OBJETIVO: el reply aporta valor — contexto, observación inteligente, ángulo no obvio, pregunta concreta.
NO frases vacías tipo "Muy interesante" o "Totalmente de acuerdo".

REGLA CRÍTICA — NUNCA INVENTAR DATOS:
- SI te paso un bloque "DATOS VERIFICADOS" con cifras, úsalas EXACTAMENTE como vienen.
- SI no te paso datos numéricos verificados, NO inventes goles, asistencias, partidos,
  fechas, rachas, comparaciones históricas ni cualquier cifra.
- Sin datos verificados, tu reply va EN MODO CUALITATIVO: ángulo táctico, observación
  sobre el jugador/equipo, pregunta abierta — pero CERO cifras inventadas.
- Mejor un reply sin números que un reply con un número falso.

TONO: DATERO + CERCANO cuando hay datos; OBSERVACIONAL + CON CRITERIO cuando no los hay.
Prohibido tono cuñao/fanboy ("el GOAT", "mejor que nunca").

REGLAS:

1. IDIOMA — CRÍTICO:
   - Si el original está en INGLÉS → escribes en INGLÉS.
   - Si el original está en ESPAÑOL → escribes en ESPAÑOL.
   - Si está mezclado, usa el predominante.

2. RELEVANCIA al ORIGINAL:
   - Tu reply responde al tema del tweet original.
   - Si te paso datos verificados sobre un jugador o equipo del tweet, EXPLÓTALOS.
   - El vídeo (si lo hay) es solo apoyo visual — NO le des protagonismo.

3. LONGITUD: 100-240 caracteres.

4. PROHIBIDO:
   - INVENTAR cifras / récords / "su mejor temporada desde 20XX" si no te lo paso.
   - Frases vacías: "Totalmente de acuerdo", "Muy interesante", "Increíble".
   - Hashtags. Emojis (salvo si el original los usa). URLs. "@" para mencionar.
   - Más de UNA pregunta.

EJEMPLOS BUENOS CON DATOS:
- Datos: "Lamine Yamal en LaLiga 25/26: 16 goles. Rating 7.93."
  → "16 goles en LaLiga 25/26 con 17 años recién cumplidos, rating 7.93 de media. ¿Llega a 20 antes de mayo?"
- Datos: "Carvajal esta temporada: 16 partidos, 0 goles, rating 6.79."
  → "Vuelve Carvajal con 16 partidos esta liga y rating 6.79 — la versión menos chispa que recordamos. ¿Le devuelve la titularidad Xabi Alonso?"

EJEMPLOS BUENOS SIN DATOS (modo cualitativo, CERO cifras):
- "El derbi nunca se gana con la posesión, se gana con quién perdona menos. Y esta noche el Atleti perdonó como nunca."
- "Curioso que el Madrid filtra esto justo en semana de Champions. Suelta tensión interna o reafirma que el plan es continuista."

Devuelve SOLO el texto de la respuesta. Sin comillas externas. Sin prefijos."""


TRENDING_POST_SYSTEM = """Eres un divulgador en castellano que comenta tendencias en X aportando un DATO CURIOSO.
Recibirás una tendencia actual y un media que vas a adjuntar (vídeo o imagen).

REGLAS:
- 100-220 caracteres TOTAL.
- Empieza con la TENDENCIA (sujeto), seguido del dato curioso o reflexión.
- Tono adulto, divulgativo, asombro. Sin clickbait ni mayúsculas gritadas.
- Si el media te ayuda a aportar valor, alúdelo brevemente; si no, ignora el media.
- CERO hashtags, emojis, URLs, "@" para mencionar.
- Una sola idea por frase. Dos frases máximo.

EJEMPLOS BUENOS:
- "Eurovisión. La canción ganadora más rápida en alcanzar 100 millones de streams fue 'Tattoo' de Loreen, en solo 9 días desde la final de 2023."
- "Mazón. Lleva 220 días sin comparecer en la comisión de la DANA pese a las 230 víctimas y los 95.000 millones de daños estimados."
- "Voyager 1. Tras 48 años en marcha, su señal tarda 22 horas en llegarnos. Sigue transmitiendo datos del espacio interestelar."

Devuelve SOLO el texto del post. Sin comillas, sin prefijos."""


def generate_trending_post(trend: str, media_title: str = "") -> str:
    """Genera un post sobre una tendencia con dato curioso. media_title es el título
    del vídeo/imagen que se adjuntará para que el LLM pueda referirse si encaja."""
    user = (
        f"TENDENCIA actual en X: {trend}\n"
        f"Media adjunto (apoyo visual): {media_title or '(sin media)'}\n\n"
        "Escribe un post sobre la tendencia con UN dato curioso o reflexión. Solo el texto."
    )
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": TRENDING_POST_SYSTEM},
            {"role": "user", "content": user},
        ],
        max_tokens=350,
        temperature=0.85,
    )
    return _trim_to_limit(_clean(response.choices[0].message.content), limit=270)


def generate_reply_with_video(original_tweet_text: str, video_topic_hint: str,
                              topic: str = "ciencia",
                              verified_facts: list[str] | None = None) -> str:
    """Genera reply respondiendo AL ORIGINAL (no al vídeo). Detecta idioma del original.

    Si se pasan verified_facts (lista de frases con datos REALES), se inyectan
    al prompt para que el LLM SOLO use esos datos y no invente cifras.
    Si la lista está vacía, el LLM genera en modo cualitativo (sin números).
    """
    if verified_facts:
        facts_block = (
            "DATOS VERIFICADOS (úsalos EXACTOS si encajan; no añadas otras cifras):\n"
            + "\n".join(f"- {f}" for f in verified_facts[:10])
        )
    else:
        facts_block = (
            "DATOS VERIFICADOS: (ninguno disponible)\n"
            "→ Genera el reply EN MODO CUALITATIVO: SIN números, SIN rachas, SIN comparaciones históricas.\n"
            "→ Aporta observación inteligente, ángulo táctico o pregunta concreta."
        )

    user = (
        f"TWEET ORIGINAL al que respondes (responde EN EL MISMO IDIOMA):\n"
        f"---\n{original_tweet_text}\n---\n\n"
        f"Vídeo que adjuntas (apoyo visual, NO le des protagonismo en el texto):\n"
        f"{video_topic_hint}\n\n"
        f"{facts_block}\n\n"
        "Escribe la respuesta. Solo el texto, sin comillas."
    )
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": REPLY_WITH_VIDEO_SYSTEM},
            {"role": "user", "content": user},
        ],
        max_tokens=350,
        temperature=0.7 if verified_facts else 0.85,
    )
    return _trim_to_limit(_clean(response.choices[0].message.content), limit=270)


if __name__ == "__main__":
    sample = {
        "subreddit": "todayilearned",
        "title": "TIL Ostrich farms routinely have difficulties getting male ostriches to breed, because the males often find their human caretakers more attractive than other ostriches",
        "selftext": "",
    }
    print(generate_viral_caption("historia", sample))
