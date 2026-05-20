"""
Formato "media por país" con DATOS REALES de World Bank (API abierta, sin clave).
Produce posts tipo "Esperanza de vida por país" o "Hijos por mujer por país",
con un ranking real y un gancho de cierre escrito por el LLM (los NÚMEROS nunca
los inventa el modelo: salen tal cual de la API).

API: https://api.worldbank.org/v2/country/<ISO3;...>/indicator/<CODE>?format=json&mrv=1
"""
import logging
import requests

log = logging.getLogger(__name__)

WB_BASE = "https://api.worldbank.org/v2"

# Pool de países relevantes para audiencia hispanohablante + grandes referencias.
# ISO3 -> (nombre_es, bandera)
COUNTRIES = {
    "ESP": ("España", "🇪🇸"), "MEX": ("México", "🇲🇽"), "ARG": ("Argentina", "🇦🇷"),
    "COL": ("Colombia", "🇨🇴"), "CHL": ("Chile", "🇨🇱"), "PER": ("Perú", "🇵🇪"),
    "VEN": ("Venezuela", "🇻🇪"), "ECU": ("Ecuador", "🇪🇨"), "URY": ("Uruguay", "🇺🇾"),
    "BOL": ("Bolivia", "🇧🇴"), "PRY": ("Paraguay", "🇵🇾"), "GTM": ("Guatemala", "🇬🇹"),
    "CUB": ("Cuba", "🇨🇺"), "DOM": ("R. Dominicana", "🇩🇴"), "CRI": ("Costa Rica", "🇨🇷"),
    "PAN": ("Panamá", "🇵🇦"), "HND": ("Honduras", "🇭🇳"), "SLV": ("El Salvador", "🇸🇻"),
    "NIC": ("Nicaragua", "🇳🇮"), "BRA": ("Brasil", "🇧🇷"), "PRT": ("Portugal", "🇵🇹"),
    "USA": ("EE.UU.", "🇺🇸"), "CAN": ("Canadá", "🇨🇦"), "GBR": ("Reino Unido", "🇬🇧"),
    "FRA": ("Francia", "🇫🇷"), "DEU": ("Alemania", "🇩🇪"), "ITA": ("Italia", "🇮🇹"),
    "NLD": ("Países Bajos", "🇳🇱"), "CHE": ("Suiza", "🇨🇭"), "SWE": ("Suecia", "🇸🇪"),
    "NOR": ("Noruega", "🇳🇴"), "JPN": ("Japón", "🇯🇵"), "KOR": ("Corea del Sur", "🇰🇷"),
    "CHN": ("China", "🇨🇳"), "IND": ("India", "🇮🇳"), "RUS": ("Rusia", "🇷🇺"),
    "AUS": ("Australia", "🇦🇺"), "ZAF": ("Sudáfrica", "🇿🇦"), "NGA": ("Nigeria", "🇳🇬"),
    "EGY": ("Egipto", "🇪🇬"), "TUR": ("Turquía", "🇹🇷"), "SAU": ("Arabia Saudí", "🇸🇦"),
}

# Catálogo de indicadores con buen gancho viral.
# code -> dict(label, unit, decimals, order, fmt)
#   order: "desc" (mayor primero) | "asc" (menor primero)
#   fmt:   None | "miles" (separador de miles)
INDICATORS = {
    "SP.DYN.LE00.IN": dict(
        label="Esperanza de vida", unit="años", decimals=1, order="desc"),
    "SP.DYN.TFRT.IN": dict(
        label="Hijos por mujer", unit="", decimals=2, order="desc"),
    "IT.NET.USER.ZS": dict(
        label="Población con internet", unit="%", decimals=1, order="desc"),
    "SP.URB.TOTL.IN.ZS": dict(
        label="Población que vive en ciudades", unit="%", decimals=1, order="desc"),
    "SP.POP.65UP.TO.ZS": dict(
        label="Población mayor de 65 años", unit="%", decimals=1, order="desc"),
    "NY.GDP.PCAP.CD": dict(
        label="PIB por habitante", unit="$", decimals=0, order="desc", fmt="miles"),
    "SL.UEM.TOTL.ZS": dict(
        label="Tasa de desempleo", unit="%", decimals=1, order="desc"),
    "SH.DYN.MORT": dict(
        label="Mortalidad infantil (por 1.000 nacidos)", unit="", decimals=1, order="desc"),
}


def fetch_indicator(code: str) -> list[dict]:
    """Devuelve [{iso, name, flag, value, year}] para los países del pool, valor
    más reciente disponible (mrv). Lista sin ordenar."""
    iso_list = ";".join(COUNTRIES.keys())
    url = f"{WB_BASE}/country/{iso_list}/indicator/{code}"
    try:
        r = requests.get(url, params={"format": "json", "per_page": "1000", "mrv": "1"},
                         timeout=25)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.error(f"World Bank fetch falló para {code}: {e}")
        return []
    if not isinstance(data, list) or len(data) < 2 or not data[1]:
        return []

    out = []
    for row in data[1]:
        val = row.get("value")
        iso = row.get("countryiso3code") or ""
        if val is None or iso not in COUNTRIES:
            continue
        name, flag = COUNTRIES[iso]
        out.append({"iso": iso, "name": name, "flag": flag,
                    "value": float(val), "year": row.get("date")})
    return out


def _fmt_value(val: float, meta: dict) -> str:
    dec = meta["decimals"]
    if meta.get("fmt") == "miles":
        s = f"{val:,.{dec}f}".replace(",", ".")
    else:
        s = f"{val:.{dec}f}".replace(".", ",")
    unit = meta["unit"]
    if unit == "$":
        return f"{unit}{s}"
    return f"{s}{(' ' + unit) if unit and unit != '%' else unit}"


def build_country_ranking(code: str, top: int = 10, with_flags: bool = True) -> dict | None:
    """Construye el ranking de un indicador. Devuelve dict listo para renderizar:
    {title, unit, year, lines: [str], spain_line, source}."""
    meta = INDICATORS.get(code)
    if not meta:
        return None
    rows = fetch_indicator(code)
    if len(rows) < top:
        log.warning(f"country_data: pocos datos para {code} ({len(rows)} países)")
        if len(rows) < 5:
            return None
    rows.sort(key=lambda r: r["value"], reverse=(meta["order"] == "desc"))
    year = rows[0]["year"] if rows else ""

    top_rows = rows[:top]
    lines = []
    for i, r in enumerate(top_rows, 1):
        flag = (r["flag"] + " ") if with_flags else ""
        lines.append(f"{i}. {flag}{r['name']}: {_fmt_value(r['value'], meta)}")

    # Si España no está en el top, la añadimos como referencia con su posición global.
    spain_line = ""
    if not any(r["iso"] == "ESP" for r in top_rows):
        for pos, r in enumerate(rows, 1):
            if r["iso"] == "ESP":
                flag = (r["flag"] + " ") if with_flags else ""
                spain_line = f"#{pos} {flag}{r['name']}: {_fmt_value(r['value'], meta)}"
                break

    return {
        "title": meta["label"],
        "unit": meta["unit"],
        "year": year,
        "lines": lines,
        "spain_line": spain_line,
        "source": "Banco Mundial",
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for code in INDICATORS:
        r = build_country_ranking(code, top=5)
        if not r:
            print(f"[FALLA] {code}")
            continue
        print(f"\n=== {r['title']} ({r['year']}) ===")
        for ln in r["lines"]:
            print(ln)
        if r["spain_line"]:
            print("...", r["spain_line"])
