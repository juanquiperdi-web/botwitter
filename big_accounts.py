"""
Pool de cuentas grandes de X especializadas en FÚTBOL.
Tier-1 + analistas. TweepCred sube interactuando con estas cuentas.
"""
import random


BIG_ACCOUNTS_BY_TOPIC = {
    "futbol": [
        # Fichajes tier-1:
        "FabrizioRomano",       # 23M+ rey de fichajes
        "David_Ornstein",        # 4M Ornstein (The Athletic)
        "Plettigoal",            # Florian Plettenberg
        # Datos y estadísticas:
        "MisterChip",            # 3M+ datos curiosos
        "OptaJose",              # Opta español
        "OptaSpain",
        # Periodistas españoles:
        "JijantesFC",
        "Jorge_Calabres",
        "ToniJuanmarti",
        "moillorens",
        "9_ine",
        "GBilbaoVic",
        # Medios deportivos:
        "marca",
        "diarioas",
        "relevo",
        "MundoDeportivo",
        "sport",
        "elchiringuitotv",
        # Equipos y ligas:
        "realmadrid",
        "FCBarcelona",
        "LaLiga",
        "ChampionsLeague",
        "premierleague",
        # Cuentas internacionales:
        "Brfootball",
        "goal",
        "ESPNFC",
        "SkySportsNews",
        "TheAthletic",
    ],
}


def pick_random_account(topic: str) -> str:
    pool = BIG_ACCOUNTS_BY_TOPIC.get(topic)
    if not pool:
        return ""
    return random.choice(pool)


def pick_random_account_excluding(topic: str, exclude: set) -> str:
    pool = BIG_ACCOUNTS_BY_TOPIC.get(topic) or []
    exclude_low = {e.lower() for e in exclude}
    candidates = [a for a in pool if a.lower() not in exclude_low]
    if not candidates:
        candidates = pool
    if not candidates:
        return ""
    return random.choice(candidates)


def sample_accounts(topic: str, n: int, exclude: set = None) -> list[str]:
    exclude = exclude or set()
    pool = BIG_ACCOUNTS_BY_TOPIC.get(topic) or []
    exclude_low = {e.lower() for e in exclude}
    candidates = [a for a in pool if a.lower() not in exclude_low]
    if len(candidates) <= n:
        return candidates
    return random.sample(candidates, n)


def sample_accounts_all_topics(n: int, exclude: set = None) -> list[tuple[str, str]]:
    exclude = exclude or set()
    exclude_low = {e.lower() for e in exclude}
    all_pairs = []
    for topic, pool in BIG_ACCOUNTS_BY_TOPIC.items():
        for account in pool:
            if account.lower() not in exclude_low:
                all_pairs.append((topic, account))
    if len(all_pairs) <= n:
        random.shuffle(all_pairs)
        return all_pairs
    return random.sample(all_pairs, n)


if __name__ == "__main__":
    for topic, pool in BIG_ACCOUNTS_BY_TOPIC.items():
        print(f"{topic}: {len(pool)} cuentas")
