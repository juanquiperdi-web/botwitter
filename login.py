"""
Ejecuta esto UNA SOLA VEZ para iniciar sesión manualmente en X.
Usa un perfil persistente de Chrome real (no Chromium) — X no lo detecta como bot.
Inicia sesión a mano. Cuando estés dentro, el script lo detecta y guarda el perfil.
"""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

PROFILE_DIR = Path(__file__).parent / "chrome_profile"
TIMEOUT_SECONDS = 600


def main():
    PROFILE_DIR.mkdir(exist_ok=True)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 800},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://x.com/login")

        print("\n" + "=" * 60)
        print("Inicia sesión MANUALMENTE en la ventana del navegador.")
        print("Detectaré automáticamente cuando estés dentro.")
        print(f"Perfil persistente: {PROFILE_DIR}")
        print("=" * 60 + "\n")

        deadline = time.time() + TIMEOUT_SECONDS
        while time.time() < deadline:
            try:
                if page.locator('[data-testid="SideNav_NewTweet_Button"]').is_visible(timeout=1000):
                    print("Login detectado. Perfil guardado automáticamente.")
                    print("Ya puedes cerrar esta ventana y ejecutar: python main.py")
                    time.sleep(3)
                    context.close()
                    return
            except Exception:
                pass
            time.sleep(2)

        print("Timeout: no se detectó login en 10 minutos.")
        context.close()


if __name__ == "__main__":
    main()
