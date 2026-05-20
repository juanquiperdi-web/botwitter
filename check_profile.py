"""Diagnóstico: lee los últimos tweets del perfil para verificar si se publican."""
from pathlib import Path
from playwright.sync_api import sync_playwright
from config import TWITTER_USERNAME

PROFILE_DIR = Path(__file__).parent / "chrome_profile"


def main():
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 800},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(f"https://x.com/{TWITTER_USERNAME}", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(8000)
        page.screenshot(path="debug/profile.png", full_page=True)
        print(f"URL actual: {page.url}")
        print(f"Title: {page.title()}")

        # Buscar mensajes de cuenta suspendida o restringida
        body_text = page.locator('body').inner_text()[:500]
        print(f"Inicio del body:\n{body_text}\n")

        articles = page.locator('article[data-testid="tweet"]').all()
        print(f"Tweets visibles en el perfil: {len(articles)}")
        for i, art in enumerate(articles[:5], 1):
            try:
                text = art.locator('[data-testid="tweetText"]').first.inner_text(timeout=2000)
                time_el = art.locator('time').first
                ts = time_el.get_attribute('datetime', timeout=2000)
                print(f"\n[{i}] {ts}")
                print(f"    {text[:200]}")
            except Exception as e:
                print(f"[{i}] error leyendo: {e}")

        context.close()


if __name__ == "__main__":
    main()
