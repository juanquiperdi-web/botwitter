"""
Generador de contenido para el bot CAZA-NICHOS (psicología / autoconocimiento).

Reemplaza la lógica de fútbol. Produce los formatos virales de referencia:
- listicle   → "10 hábitos de…", "10 señales de…", "9 consejos para…", "7 cambios cuando…"
- personality → "Lo que tu forma de [X] dice de ti" (gancho de interacción)
- curiosity  → un dato curioso de psicología/comportamiento reescrito (Reddit o LLM)

Todo en castellano. El motor de publicación (twitter_poster) y el scheduler
(runner_scheduled) se reutilizan tal cual; aquí solo cambia QUÉ se escribe.
"""
import re
import json
import random
from groq import Groq
from config import GROQ_API_KEY

client = Groq(api_key=GROQ_API_KEY)

MODEL = "llama-3.3-70b-versatile"

PERSONA = """Eres un divulgador de PSICOLOGÍA y AUTOCONOCIMIENTO en castellano que escribe
para X (Twitter). Tu cuenta crece compartiendo observaciones sobre comportamiento humano,
hábitos, relaciones, sesgos cognitivos y lenguaje corporal de forma cercana y reveladora.
Tono: adulto, claro, cercano, con criterio. Nada de horóscopos ni autoayuda hueca.
Cada idea hace que el lector piense "esto me pasa a mí" o "esto es mi pareja/jefe/amigo".
Nunca dices que eres una IA."""


# ---------------------------------------------------------------------------
# BANCO DE ÁNGULOS — variedad para que el bot no se repita.
# Cada entrada: (plantilla_de_titulo, tema). El número lo decide el formato.
# ---------------------------------------------------------------------------
LISTICLE_ANGLES = [
    ("{n} hábitos de las personas mentalmente fuertes", "fortaleza mental"),
    ("{n} señales de que alguien es más inteligente de lo que aparenta", "inteligencia"),
    ("{n} señales de que estás agotado emocionalmente (y no es pereza)", "agotamiento emocional"),
    ("{n} hábitos diarios de la gente que envejece con la mente joven", "envejecimiento cognitivo"),
    ("{n} consejos para dejar de procrastinar que sí funcionan", "procrastinación"),
    ("{n} señales de que una persona tiene alta inteligencia emocional", "inteligencia emocional"),
    ("{n} frases que usan las personas manipuladoras sin que te des cuenta", "manipulación"),
    ("{n} hábitos de la gente que nunca pierde la calma", "autocontrol"),
    ("{n} señales de que creciste asumiendo demasiada responsabilidad", "parentificación"),
    ("{n} cambios que notas cuando por fin sanas tu autoestima", "autoestima"),
    ("{n} señales de que alguien finge seguridad pero por dentro duda", "inseguridad"),
    ("{n} hábitos nocturnos que sabotean tu descanso sin que lo sepas", "sueño"),
    ("{n} consejos para tener conversaciones que la gente recuerda", "comunicación"),
    ("{n} señales de que tu cuerpo te está pidiendo descanso, no café", "estrés"),
    ("{n} sesgos cognitivos que te hacen tomar malas decisiones a diario", "sesgos cognitivos"),
    ("{n} hábitos de la gente que cae bien sin esforzarse", "carisma"),
    ("{n} señales de que maduraste de verdad (no solo de edad)", "madurez"),
    ("{n} cosas que la gente con paz mental dejó de hacer", "paz mental"),
]

# Gancho de personalidad: "lo que tu forma de X dice de ti".
PERSONALITY_THEMES = [
    "cómo doblas la ropa", "tu forma de conducir", "cómo escribes los mensajes",
    "el orden de tu mesa de trabajo", "cómo reaccionas cuando te interrumpen",
    "tu forma de despedirte de la gente", "cómo organizas el móvil",
    "la forma en que comes cuando estás solo", "cómo respondes a un cumplido",
    "tu manera de caminar por la calle", "cómo gestionas un mensaje sin contestar",
]


def _clean(text: str) -> str:
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"(?i)^(tweet|caption|texto|post):\s*", "", text)
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"https?://\S+", "", text)
    return text.strip()


def _trim(text: str, limit: int = 280) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def _chat(system: str, user: str, max_tokens: int = 600, temperature: float = 0.85) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# FORMATO 1 — LISTICLE ("10 hábitos de…", "10 señales de…")
# Devuelve dict: {title, items: [str x N], cta}. El runner lo renderiza en hilo.
# ---------------------------------------------------------------------------
LISTICLE_SYSTEM = PERSONA + """

Vas a escribir una LISTA viral de divulgación psicológica.

REGLAS:
1. Devuelve SOLO un JSON válido con esta forma exacta:
   {"title": "...", "items": ["...", "...", ...], "cta": "..."}
2. "title": el titular sin numeración (ej. "Señales de que alguien es muy inteligente").
3. "items": EXACTAMENTE el número de puntos pedido. Cada punto:
   - Una frase de 40-110 caracteres, concreta y reveladora.
   - Empieza directa, sin "1." ni guion (el sistema numera).
   - Específica y observable, no genérica ("Escucha más de lo que habla", no "Es buena persona").
4. "cta": una línea de cierre de 40-120 chars con una PREGUNTA que invite a responder
   ("¿Cuántas cumples?", "¿Cuál te ha pasado hoy?", "¿Añadirías alguna?").
5. Castellano natural de España. Sin emojis, sin hashtags, sin clickbait gritón.
6. Nada de inventar estudios o cifras concretas ("según Harvard el 87%"): habla de
   comportamiento observable, no de estadísticas falsas.

Devuelve SOLO el JSON, sin texto alrededor."""


def generate_listicle(n: int = 7, angle: tuple | None = None) -> dict:
    """Genera una lista de N puntos. Si no se pasa 'angle', elige uno al azar.
    Devuelve {title, items, cta, raw_title}."""
    if angle is None:
        angle = random.choice(LISTICLE_ANGLES)
    title_tmpl, tema = angle
    raw_title = title_tmpl.format(n=n)

    user = (
        f"Tema: {tema}\n"
        f"Titular objetivo: {raw_title}\n"
        f"Número de puntos: {n}\n\n"
        "Genera la lista en el JSON pedido."
    )
    text = _chat(LISTICLE_SYSTEM, user, max_tokens=800, temperature=0.85)

    # Extrae el JSON aunque venga con texto alrededor.
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"El LLM no devolvió JSON: {text[:200]}")
    data = json.loads(m.group(0))

    items = [_clean(str(i)) for i in data.get("items", []) if str(i).strip()]
    items = items[:n]
    if len(items) < max(3, n - 2):
        raise ValueError(f"Lista demasiado corta: {len(items)} puntos")

    return {
        "title": _clean(data.get("title", raw_title)),
        "items": items,
        "cta": _clean(data.get("cta", "¿Cuántas cumples?")),
        "raw_title": raw_title,
    }


def render_listicle_thread(data: dict, limit: int = 275) -> list[str]:
    """Convierte el dict del listicle en una lista de tweets (hilo) para post_thread.
    Reparte los puntos en tweets de <=limit chars. Tweet 1 lleva el titular.
    Reserva margen para el indicador de continuación '↓' del primer tweet."""
    numbered = [f"{i+1}. {txt}" for i, txt in enumerate(data["items"])]
    cont = "\n\n↓"          # sufijo de continuación del tweet 1
    header = f"{data['raw_title']}:"

    tweets: list[str] = []
    current_lines: list[str] = []
    current_header = header   # solo el primer tweet lleva titular

    def flush():
        if current_lines:
            block = (current_header + "\n\n" if current_header else "") + "\n".join(current_lines)
            tweets.append(block.rstrip())

    for line in numbered:
        # margen extra que se reservará en el tweet 1 para el '↓'
        reserve = len(cont) if (not tweets and current_header) else 0
        prospective = (
            (current_header + "\n\n" if current_header else "")
            + "\n".join(current_lines + [line])
        )
        if len(prospective) + reserve > limit and current_lines:
            flush()
            current_lines = [line]
            current_header = ""   # los siguientes tweets ya no llevan titular
        else:
            current_lines.append(line)
    flush()

    # CTA: al último tweet si cabe, si no como tweet aparte.
    cta = data.get("cta", "").strip()
    if cta:
        if len(tweets[-1]) + 2 + len(cta) <= limit:
            tweets[-1] = tweets[-1] + "\n\n" + cta
        else:
            tweets.append(cta)

    # Indicador de continuación en el primer tweet (ya hay margen reservado).
    if len(tweets) > 1:
        tweets[0] = tweets[0] + cont
    return tweets


# ---------------------------------------------------------------------------
# FORMATO 2 — PERSONALITY HOOK ("lo que tu forma de X dice de ti")
# Post único de alta interacción: describe 3-4 perfiles y pide identificarse.
# ---------------------------------------------------------------------------
PERSONALITY_SYSTEM = PERSONA + """

Vas a escribir un post de gancho psicológico tipo "lo que tu forma de X dice de ti".

FORMATO (un solo tweet, máx 280 chars):
- Línea 1: la premisa ("Lo que [tema] dice de tu personalidad:").
- 2 a 3 líneas, cada una un "tipo" con su rasgo, formato "A → rasgo".
- Cierre corto que pide al lector identificarse ("¿Cuál eres tú?").

REGLAS:
- 200-280 caracteres TOTAL. Castellano de España.
- Concreto y con chispa, que dé ganas de responder cuál es cada uno.
- Sin emojis, sin hashtags, sin clickbait.

EJEMPLO:
"Cómo doblas la ropa dice mucho de ti:
Perfecta y por colores → necesitas control para estar en calma.
La tiras en la silla → vives en el presente, el orden te agobia.
Ni la doblas → tu cabeza va a mil, lo práctico gana.
¿Cuál eres?"

Devuelve SOLO el texto del post, sin comillas ni prefijos."""


def generate_personality_post(theme: str | None = None) -> str:
    if theme is None:
        theme = random.choice(PERSONALITY_THEMES)
    user = f"Tema: {theme}\n\nEscribe el post siguiendo el formato. Solo el texto."
    text = _clean(_chat(PERSONALITY_SYSTEM, user, max_tokens=400, temperature=0.9))
    return _trim(text, 280)


# ---------------------------------------------------------------------------
# FORMATO 3 — CURIOSITY (dato curioso de comportamiento, desde Reddit o solo LLM)
# ---------------------------------------------------------------------------
CURIOSITY_SYSTEM = PERSONA + """

Vas a escribir un post con UN dato curioso sobre la mente o el comportamiento humano.

REGLAS:
- 120-260 caracteres. Castellano de España.
- Empieza con el fenómeno (sujeto) y explica por qué pasa, de forma reveladora.
- Si te paso contenido fuente, reescríbelo con tu tono; si está en inglés, tradúcelo.
- Cierra con una micro-pregunta o reflexión que invite a comentar.
- Sin emojis, hashtags, URLs ni clickbait. No inventes cifras ni estudios concretos.

EJEMPLO:
"Tu cerebro recuerda mejor las tareas que dejaste a medias que las que terminaste. Se llama efecto Zeigarnik, y es la razón por la que no puedes dejar de pensar en ese mensaje sin responder. ¿Tienes alguna a medias rondándote ahora?"

Devuelve SOLO el texto del post, sin comillas ni prefijos."""


SEX_ANGLES = [
    "señales de que hay atracción real y no solo amabilidad",
    "lo que tu forma de besar dice de tu personalidad",
    "señales de que alguien piensa en ti más de lo que admite",
    "errores que matan el deseo en una relación larga",
    "lo que la ciencia dice sobre la química entre dos personas",
    "señales de que la tensión sexual es mutua",
    "hábitos de las parejas que mantienen viva la pasión",
    "lo que tu lenguaje corporal revela cuando alguien te gusta",
    "razones por las que el deseo baja y nadie te lo explica",
    "señales de que hay conexión emocional y no solo física",
    "lo que tu forma de coquetear dice de ti",
    "mitos sobre el deseo que casi todo el mundo se cree",
]

SEX_SYSTEM = PERSONA + """

Vas a escribir un post sobre PSICOLOGÍA DE LA ATRACCIÓN, EL DESEO y las RELACIONES
de pareja. Tema sensible pero tratado con criterio: divulgación adulta, NO contenido
explícito ni vulgar. El gancho es la curiosidad y el "esto me pasa", no el morbo barato.

REGLAS:
- 140-275 caracteres. Castellano de España.
- Empieza directo con el fenómeno o la señal (sujeto), explícalo de forma reveladora.
- Cierra con una micro-pregunta o frase que invite a comentar/identificarse.
- Tono adulto, elegante, con chispa. PROHIBIDO: explícito, soez, clickbait gritón,
  emojis, hashtags, URLs, inventar estudios o porcentajes concretos.
- Que dé ganas de responder o de etiquetar a alguien, sin caer en lo cursi.

EJEMPLOS BUENOS:
- "La atracción real no se nota en lo que te dicen, sino en lo que hacen sin pensar: hacia dónde apuntan los pies, cuánto tardan en mirarte cuando entras. El cuerpo confiesa antes que la boca. ¿En quién lo has notado últimamente?"
- "El deseo no muere por falta de amor, muere por exceso de rutina y cero misterio. Lo que mantiene viva la chispa no es el sexo, es la incertidumbre de no tenerlo todo controlado. ¿Rutina o misterio en tu relación?"

Devuelve SOLO el texto del post, sin comillas ni prefijos."""


def generate_sex_post(angle: str | None = None) -> str:
    """Post de psicología de la atracción/relaciones. Tono adulto, no explícito."""
    if angle is None:
        angle = random.choice(SEX_ANGLES)
    user = f"Ángulo: {angle}\n\nEscribe el post siguiendo el estilo. Solo el texto."
    text = _clean(_chat(SEX_SYSTEM, user, max_tokens=400, temperature=0.9))
    return _trim(text, 280)


VIRAL_HOOK_SYSTEM = """Eres una cuenta viral de X de SITUACIONES DIVERTIDAS DE ANIMALES en español.
Te paso el título original de un clip (a veces en inglés/japonés/etc.). Escribe
el caption del tweet: una FRASE corta y aguda que dé ganas de parar el scroll.

REGLAS DURAS:
1. LONGITUD: 40-110 caracteres. Lo ideal es UN beat + UNA apostilla o remate
   (estructura "etiqueta, matiz" / "setup. punchline" / "acción + veredicto").
2. HUMANIZA al animal: dale pensamiento, actitud, intención humana. Eso es lo
   que engancha en este formato (no la descripción del vídeo).
3. ÁNGULO INESPERADO: no lo obvio. Una etiqueta de personalidad, una conclusión
   absurda, un veredicto, una traición, un drama, un "modo X activado".
4. VOZ NATURAL: castellano hablado, como un amigo que te enseña el vídeo. Cero
   tono de marketing. Cero "qué adorable", "increíble", "no te lo pierdas".
5. PROHIBIDO: hashtags, @menciones, enlaces, mayúsculas de grito, signos !!!!,
   describir el vídeo literalmente ("este perro hace...", "mira cómo..."),
   muletillas (realmente, simplemente, literalmente), frases de catálogo.
6. EMOJI: 0 ó 1 como máximo, y SOLO si subraya la emoción. Nunca de adorno.
7. EVITA las frases sosas tipo "se siente atacado", "se ríe de mí". Un hook bueno
   debe tener al menos UN giro: un sustantivo concreto, una comparación, una
   conclusión, un "y encima X", un "como si Y".
8. Si no entiendes el título, escribe una etiqueta de personalidad jugosa
   atribuible a cualquier animal gracioso (NO genérica).

EJEMPLOS BUENOS (mira la concisión y el ángulo):
- "Mom cat leaving her human to babysit so she can sleep"
  → "Delegó y se piró a dormir, una jefa"
- "Dog saw himself in an ad and posed"
  → "Se ha visto famoso y ya no nos habla"
- "Grumpy cat goes goofy after a banana"
  → "De villano a bobo en 0,2 segundos"
- "He felt betrayed"
  → "Lo está procesando en tiempo real"
- "Looks like a cat doing a moonwalk"
  → "Más estilo que Michael Jackson"
- "Cat does backflip"
  → "Coordinación que yo no tengo"

EJEMPLOS MALOS (NO hagas esto):
- "Este gato es muy gracioso, mira lo que hace 😂"  (describe, marketing)
- "¡INCREÍBLE lo que hace este perro!"               (clickbait gritón)
- "Una situación realmente divertida 🐶🤣😍"          (muletillas + emojis decorativos)

Devuelve SOLO el caption final. Sin comillas. Sin prefijos. Sin explicaciones."""


def generate_viral_hook(clip_title: str = "") -> str:
    """Caption corto y enganchón para un clip viral, a partir de su título original."""
    user = (
        f"Título original del clip: {clip_title!r}\n\n"
        "Escribe el caption corto en español. Solo el texto."
        if clip_title else
        "No hay título. Escribe un caption corto de asombro/gancho genérico en español. Solo el texto."
    )
    text = _clean(_chat(VIRAL_HOOK_SYSTEM, user, max_tokens=120, temperature=0.9))
    return _trim(text, 200)


def generate_curiosity_post(source: dict | None = None) -> str:
    """Si 'source' trae {title, selftext, subreddit} (de Reddit), lo reescribe.
    Si no, el LLM genera un dato curioso de psicología por su cuenta."""
    if source and source.get("title"):
        user = (
            f"Contenido fuente (de r/{source.get('subreddit','')}):\n"
            f"Título: {source.get('title','')}\n"
        )
        if source.get("selftext"):
            user += f"Detalle: {source['selftext'][:1000]}\n"
        user += "\nReescríbelo como post de dato curioso siguiendo el estilo. Solo el texto."
    else:
        user = (
            "Escribe un post con un dato curioso real y conocido sobre psicología o "
            "comportamiento humano (efecto psicológico, sesgo, fenómeno cognitivo). "
            "Solo el texto."
        )
    text = _clean(_chat(CURIOSITY_SYSTEM, user, max_tokens=400, temperature=0.85))
    return _trim(text, 280)


if __name__ == "__main__":
    print("=== LISTICLE ===")
    data = generate_listicle(n=7)
    print("Titular:", data["raw_title"])
    for t in render_listicle_thread(data):
        print("-" * 40)
        print(t, f"\n[{len(t)} chars]")

    print("\n\n=== PERSONALITY ===")
    print(generate_personality_post())

    print("\n\n=== CURIOSITY ===")
    print(generate_curiosity_post())
