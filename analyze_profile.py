"""
Analiza el perfil de un usuario de X: lee últimos tweets con métricas
y resume patrones (longitud, hashtags, hilos, imágenes, engagement).
Uso: python analyze_profile.py <username_sin_arroba>
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = Path(__file__).parent / "chrome_profile"


def _parse_count(s: str) -> int:
    """Parsea '194', '5,2 mil', '12K', '1,3M', '1.5 millones'."""
    if not s:
        return 0
    s_orig = s.strip().lower()
    # Captura el primer número (con coma o punto decimal)
    m = re.search(r"([\d]+(?:[.,]\d+)?)", s_orig)
    if not m:
        return 0
    num = float(m.group(1).replace(",", "."))
    rest = s_orig[m.end():]
    # Multiplicador por sufijo
    if "millon" in rest or re.search(r"\bm\b", rest):
        num *= 1_000_000
    elif "mil" in rest or re.search(r"\bk\b", rest):
        num *= 1_000
    return int(num)


def main(username: str):
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 1200},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(f"https://x.com/{username}", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)

        # Scroll para cargar más tweets
        for _ in range(6):
            page.mouse.wheel(0, 3000)
            page.wait_for_timeout(1500)

        articles = page.locator('article[data-testid="tweet"]').all()
        print(f"\nTweets capturados: {len(articles)}\n")

        results = []
        for art in articles:
            try:
                text = ""
                try:
                    text = art.locator('[data-testid="tweetText"]').first.inner_text(timeout=1500)
                except Exception:
                    pass
                ts = ""
                try:
                    ts = art.locator('time').first.get_attribute('datetime', timeout=1500) or ""
                except Exception:
                    pass

                # Métricas: views, replies, retweets, likes
                metrics = {}
                for key in ("reply", "retweet", "like"):
                    try:
                        el = art.locator(f'[data-testid="{key}"]').first
                        label = el.get_attribute("aria-label", timeout=1000) or ""
                        metrics[key] = _parse_count(label)
                    except Exception:
                        metrics[key] = 0
                # Views: el aria-label suele estar en el enlace que contiene "vistas"/"views"
                try:
                    view_link = art.locator('a[href*="/analytics"]').first
                    label = view_link.get_attribute("aria-label", timeout=1000) or ""
                    metrics["view"] = _parse_count(label)
                except Exception:
                    metrics["view"] = 0

                has_image = art.locator('[data-testid="tweetPhoto"]').count() > 0
                has_video = art.locator('[data-testid="videoPlayer"]').count() > 0
                hashtags = re.findall(r"#\w+", text)
                mentions = re.findall(r"@\w+", text)
                urls = re.findall(r"https?://\S+", text)

                results.append({
                    "ts": ts,
                    "text": text,
                    "len": len(text),
                    "hashtags": hashtags,
                    "mentions": mentions,
                    "has_image": has_image,
                    "has_video": has_video,
                    "has_url": bool(urls),
                    "metrics": metrics,
                })
            except Exception:
                continue

        context.close()

    if not results:
        print("No se pudieron capturar tweets.")
        return

    # Análisis
    print("=" * 70)
    print(f"ANÁLISIS DE @{username}")
    print("=" * 70)

    by_likes = sorted(results, key=lambda r: r["metrics"].get("like", 0), reverse=True)

    import sys as _sys
    if hasattr(_sys.stdout, "reconfigure"):
        _sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print(f"\nTop 5 por likes:")
    for r in by_likes[:5]:
        m = r["metrics"]
        flags = []
        if r["has_image"]: flags.append("img")
        if r["has_video"]: flags.append("vid")
        if r["hashtags"]: flags.append(f"{len(r['hashtags'])}#")
        if r["mentions"]: flags.append(f"{len(r['mentions'])}@")
        flag_str = " ".join(flags) or "-"
        print(f"  likes={m.get('like',0)} rt={m.get('retweet',0)} reply={m.get('reply',0)} views={m.get('view',0)}  [{flag_str}]")
        print(f"     ({r['len']}c) {r['text'][:160].replace(chr(10), ' / ')}")

    # Estadísticas
    avg_len = sum(r["len"] for r in results) / len(results)
    pct_image = sum(1 for r in results if r["has_image"]) / len(results) * 100
    pct_video = sum(1 for r in results if r["has_video"]) / len(results) * 100
    pct_url = sum(1 for r in results if r["has_url"]) / len(results) * 100
    pct_no_hashtag = sum(1 for r in results if not r["hashtags"]) / len(results) * 100

    avg_hashtags = sum(len(r["hashtags"]) for r in results) / len(results)
    avg_mentions = sum(len(r["mentions"]) for r in results) / len(results)

    avg_likes = sum(r["metrics"].get("like", 0) for r in results) / len(results)
    avg_views = sum(r["metrics"].get("view", 0) for r in results) / len(results)

    print(f"\nESTADÍSTICAS sobre {len(results)} tweets:")
    print(f"  Longitud media:        {avg_len:.0f} chars")
    print(f"  Con imagen:            {pct_image:.0f}%")
    print(f"  Con vídeo:             {pct_video:.0f}%")
    print(f"  Con URL:               {pct_url:.0f}%")
    print(f"  SIN hashtags:          {pct_no_hashtag:.0f}%")
    print(f"  Hashtags por tweet:    {avg_hashtags:.1f}")
    print(f"  Menciones por tweet:   {avg_mentions:.1f}")
    print(f"  Likes medios:          {avg_likes:.0f}")
    print(f"  Views medios:          {avg_views:.0f}")

    # Top hashtags
    all_tags = Counter()
    for r in results:
        for h in r["hashtags"]:
            all_tags[h.lower()] += 1
    if all_tags:
        print(f"\n  Hashtags más usados:")
        for h, c in all_tags.most_common(10):
            print(f"    {h} × {c}")

    # Guardar JSON
    out = Path(__file__).parent / "debug" / f"analysis_{username}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Detalle completo guardado en: {out}")


if __name__ == "__main__":
    user = sys.argv[1] if len(sys.argv) > 1 else "IAGenMoney"
    main(user)
