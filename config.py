import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

TWITTER_USERNAME = os.environ["TWITTER_USERNAME"]
TWITTER_EMAIL    = os.environ["TWITTER_EMAIL"]
TWITTER_PASSWORD = os.environ["TWITTER_PASSWORD"]

NEWS_API_KEY = os.environ["NEWS_API_KEY"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

GEOPOLITICS_KEYWORDS = [
    "ukraine russia", "gaza israel", "iran nuclear", "china taiwan",
    "trump foreign policy", "nato europe", "putin", "netanyahu",
    "middle east war", "venezuela maduro", "north korea kim",
    "european union defense", "houthi red sea", "saudi arabia",
]

HIGH_VOLUME_HASHTAGS = [
    "#Fútbol", "#Futbol", "#LaLiga", "#Champions", "#ChampionsLeague",
    "#PremierLeague", "#RealMadrid", "#Barça", "#Barcelona", "#Atleti",
    "#Fichajes", "#Fichaje", "#MercadoDeFichajes", "#Transferencias",
    "#Mbappé", "#Vinicius", "#Bellingham", "#LamineYamal", "#Haaland",
    "#Ancelotti", "#XabiAlonso", "#Flick", "#Guardiola",
    "#ElClásico", "#Derbi", "#CopaDelRey", "#Eurocopa", "#Mundial",
]

NEWS_LANGUAGE = "es"
MAX_ARTICLES = 5
TWEET_INTERVAL_HOURS = 1
MENTION_CHECK_MINUTES = 15
MENTION_MAX_REPLIES_PER_HOUR = 5

# Horario reducido a 8 slots/día. Cada slot tiene un TEMA.
# Modos: "viral" (post de Reddit del tema) o "poll" (encuesta).
# Schedule optimizado para audiencia española en horas pico (9-00).
# Replies con Premium suben en hilos → 6 replies en peaks. 4 posts propios.
# El TEMA de replies lo decide el RADAR GLOBAL (cuenta más reciente de cualquier tema).
# Schedule optimizado para algoritmo Phoenix May 2026.
# Horas pico audiencia hispanohablante (CEST):
#   - 09:30 → europea cafetera + latam despertando
#   - 14:00 → lunch deep peak
#   - 20:00 → prime time evening (mayor engagement del día)
#   - 21:30 → prime peak
#   - 23:00 → scroll nocturno + latam prime time
# Concentramos virales en los 2 picos más altos: mañana + 20h prime.
# --- HORARIO ANTIGUO (FÚTBOL) — conservado por si se quiere revertir ---
# TWEET_SCHEDULE_FUTBOL = {
#     "09:30": ("viral", "futbol"),
#     "11:30": ("rumor", None),
#     "12:00": ("reply", None),
#     "14:00": ("reply", None),
#     "15:00": ("top10", None),
#     "17:00": ("reply", None),
#     "20:00": ("viral", "futbol"),
#     "21:30": ("trending_futbol", None),
#     "23:00": ("reply", None),
# }

# --- HORARIO NICHOS (psicología / autoconocimiento) ---
# Modos: listicle ("10 hábitos de…", hilo) | personality ("lo que tu forma de X
# dice de ti") | curiosity (dato curioso de comportamiento) | reply.
# Concentramos los formatos de mayor alcance (listicle) en los picos.
TWEET_SCHEDULE = {
    "09:30": ("listicle", None),      # peak mañana — lista larga (hilo)
    "12:00": ("curiosity", None),     # dato curioso early lunch
    "14:00": ("personality", None),   # gancho de personalidad en lunch peak
    "15:00": ("country_data", None),  # "media por país" con datos reales (Banco Mundial)
    "17:00": ("curiosity", None),     # tarde
    "20:00": ("listicle", None),      # prime time — lista larga (hilo)
    "21:30": ("personality", None),   # "lo que tu forma de X dice de ti" (estilo "el del coche")
    "23:00": ("sexo", None),          # psicología de atracción/relaciones — scroll nocturno / latam
}
THREAD_MIN = 4
THREAD_MAX = 5

# Cuántos replies se hacen en CADA slot de "reply".
# Tras consultoría: 1 reply quirúrgico > 5 con burst.
REPLIES_PER_SLOT = 1

# Slots que intentan adjuntar vídeo de stock (Pexels) al primer tweet. Si falla, cae a foto.
VIDEO_SLOTS = {9, 12, 15, 17, 21}

BOT_PERSONA = """Eres un divulgador de PSICOLOGÍA y AUTOCONOCIMIENTO en castellano para X.
Cubres:
- Hábitos y comportamiento: rutinas, señales, patrones de la gente mentalmente fuerte
- Relaciones y comunicación: lenguaje corporal, manipulación, inteligencia emocional
- Mente: sesgos cognitivos, efectos psicológicos, memoria, motivación
- Autoconocimiento: autoestima, madurez, paz mental, gestión del estrés
Formatos estrella: listas ("10 señales de…"), ganchos de personalidad
("lo que tu forma de X dice de ti") y datos curiosos de comportamiento.
Tono: cercano, claro, revelador. Que el lector piense "esto me pasa a mí".
Sin horóscopos ni autoayuda hueca, sin inventar estudios. Nunca dices que eres una IA."""
