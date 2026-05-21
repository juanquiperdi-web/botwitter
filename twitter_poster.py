import logging
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from playwright.sync_api import sync_playwright, Page, BrowserContext, TimeoutError as PWTimeout

log = logging.getLogger(__name__)
PROFILE_DIR = Path(__file__).parent / "chrome_profile"
DEBUG_DIR = Path(__file__).parent / "debug"

ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _extract_tweet_id(page: Page) -> str:
    try:
        page.wait_for_url(re.compile(r"/status/\d+"), timeout=8000)
        match = re.search(r"/status/(\d+)", page.url)
        if match:
            return match.group(1)
    except PWTimeout:
        pass
    return "ok"


def _dismiss_popups(page: Page) -> None:
    for _ in range(3):
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)


def _click_post_and_confirm(page: Page, is_video: bool = False, label: str = "tweet") -> None:
    """Pulsa el botón Postear esperando a que esté habilitado (el vídeo tarda en
    procesar) y CONFIRMA que la publicación salió. Lanza RuntimeError si X muestra
    error o si seguimos en el cuadro de redactar (no publicó)."""
    btn = page.locator('[data-testid="tweetButton"]').first
    deadline = 90000 if is_video else 20000   # ms; el vídeo necesita procesarse
    waited = 0
    while waited < deadline:
        try:
            if btn.count() and btn.get_attribute("aria-disabled") != "true":
                break
        except Exception:
            pass
        page.wait_for_timeout(1000)
        waited += 1000
    btn.click(timeout=10000)
    page.wait_for_timeout(9000 if is_video else 5000)

    # ¿Error de X? ("Algo salió mal, ...")
    try:
        if page.get_by_text("Algo salió mal").count() > 0:
            _save_debug(page, f"{label}_x_error")
            raise RuntimeError("X rechazó la publicación ('Algo salió mal') — ¿modo headless?")
    except RuntimeError:
        raise
    except Exception:
        pass

    # Éxito esperado: el cuadro /compose/post se cierra (salimos de esa URL).
    if "/compose/" in page.url:
        # Damos un margen extra por si está cerrando.
        page.wait_for_timeout(3000)
        if "/compose/" in page.url and page.locator('[data-testid="tweetTextarea_0"]').count() > 0:
            _save_debug(page, f"{label}_no_confirm")
            raise RuntimeError("Publicación no confirmada: seguimos en el cuadro de redactar.")


def _save_debug(page: Page, name: str) -> None:
    try:
        DEBUG_DIR.mkdir(exist_ok=True)
        path = DEBUG_DIR / f"{name}.png"
        page.screenshot(path=str(path), full_page=True)
        log.info(f"Screenshot guardado en: {path}")
    except Exception as e:
        log.warning(f"No se pudo guardar screenshot: {e}")


def _open_context(p, headless: bool) -> BrowserContext:
    if not PROFILE_DIR.exists():
        raise RuntimeError("No existe el perfil de Chrome. Ejecuta primero: python login.py")
    return p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        channel="chrome",
        headless=headless,
        # NOTA: navegador VISIBLE a propósito (headless lo bloquea X). Probado mover
        # la ventana fuera de pantalla pero rompe el click del botón Postear.
        args=["--disable-blink-features=AutomationControlled"],
        viewport={"width": 1280, "height": 800},
    )


def _type_into_textarea(page: Page, index: int, text: str) -> None:
    selector = f'[data-testid="tweetTextarea_{index}"]'
    textarea = page.wait_for_selector(selector, timeout=20000)
    try:
        textarea.click(timeout=5000)
    except PWTimeout:
        textarea.click(force=True)
    page.keyboard.type(text, delay=15)
    page.wait_for_timeout(500)


def _download_image(image_url: str) -> Path | None:
    """Descarga una imagen a archivo temporal. Devuelve la ruta o None si falla."""
    if not image_url:
        return None
    try:
        parsed = urlparse(image_url)
        ext = Path(parsed.path).suffix.lower() or ".jpg"
        if ext not in ALLOWED_IMAGE_EXTS:
            ext = ".jpg"

        r = requests.get(image_url, timeout=10, stream=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        r.raise_for_status()
        if int(r.headers.get("content-length", "0")) > 5_000_000:
            log.warning(f"Imagen demasiado grande: {image_url}")
            return None

        tmp = Path(tempfile.gettempdir()) / f"geopol_bot_{abs(hash(image_url))}{ext}"
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        if tmp.stat().st_size < 1000:
            log.warning(f"Imagen demasiado pequeña: {image_url}")
            tmp.unlink(missing_ok=True)
            return None
        return tmp
    except Exception as e:
        log.warning(f"No se pudo descargar imagen {image_url}: {e}")
        return None


def _attach_image(page: Page, image_path: Path) -> bool:
    try:
        file_input = page.locator('[data-testid="fileInput"]').first
        file_input.set_input_files(str(image_path), timeout=8000)
        page.wait_for_selector('[data-testid="attachments"]', timeout=10000)
        page.wait_for_timeout(2000)
        return True
    except Exception as e:
        log.warning(f"No se pudo adjuntar imagen: {e}")
        return False


def _attach_media(page: Page, media_path: Path, is_video: bool = False, tweet_index: int = 0) -> bool:
    """Adjunta una imagen o vídeo al tweet en posición tweet_index del compose."""
    try:
        # X presenta un file input por cada tweet del compose. nth(tweet_index) selecciona el correcto.
        inputs = page.locator('[data-testid="fileInput"]')
        count = inputs.count()
        if count <= tweet_index:
            file_input = inputs.last
        else:
            file_input = inputs.nth(tweet_index)
        file_input.set_input_files(str(media_path), timeout=8000)
        # Vídeos tardan más en procesarse en X
        timeout = 45000 if is_video else 10000
        page.wait_for_selector('[data-testid="attachments"]', timeout=timeout)
        if is_video:
            page.wait_for_timeout(8000)
        else:
            page.wait_for_timeout(2000)
        return True
    except Exception as e:
        log.warning(f"No se pudo adjuntar {'vídeo' if is_video else 'imagen'} al tweet {tweet_index}: {e}")
        return False


def post_tweet(text: str, image_url: str = "", video_path: Path = None,
               image_path: Path = None, headless: bool = False) -> str:
    # NOTA: headless=False por defecto — X BLOQUEA la publicación en modo headless
    # ("Algo salió mal"). Con navegador visible sí publica.
    if not image_path and image_url and not video_path:
        image_path = _download_image(image_url)
    media = video_path or image_path
    is_video = bool(video_path)
    with sync_playwright() as p:
        context = _open_context(p, headless)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)
            # OJO: NO pulsar Escape aquí — cierra el cuadro de publicar y te manda a /home.

            _type_into_textarea(page, 0, text)
            if media:
                if _attach_media(page, media, is_video=is_video):
                    log.info(f"{'Vídeo' if is_video else 'Imagen'} adjuntado al tweet")

            _click_post_and_confirm(page, is_video=is_video, label="tweet")
            tweet_id = _extract_tweet_id(page)
            log.info(f"Tweet publicado (id={tweet_id}, url={page.url})")
            return tweet_id
        except Exception:
            _save_debug(page, "error_single")
            raise
        finally:
            context.close()
            if image_path:
                image_path.unlink(missing_ok=True)


def post_reply(text: str, target_url: str, video_path: Path = None,
               image_path: Path = None, headless: bool = True) -> str:
    """Publica una respuesta (reply) a un tweet existente.
    Opcionalmente adjunta vídeo o imagen al reply."""
    if not target_url:
        raise ValueError("target_url es obligatorio")
    media = video_path or image_path
    is_video = bool(video_path)
    with sync_playwright() as p:
        context = _open_context(p, headless)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            _dismiss_popups(page)

            reply_textarea = page.wait_for_selector(
                '[data-testid="tweetTextarea_0"]', timeout=15000
            )
            try:
                reply_textarea.click(timeout=5000)
            except PWTimeout:
                reply_textarea.click(force=True)
            page.keyboard.type(text, delay=15)
            page.wait_for_timeout(1000)

            if media:
                if _attach_media(page, media, is_video=is_video, tweet_index=0):
                    log.info(f"{'Vídeo' if is_video else 'Imagen'} adjuntado al reply")
                    # Espera adicional para que termine el procesado en X
                    page.wait_for_timeout(5000 if is_video else 1500)

            # Timeout amplio cuando el reply lleva vídeo (X tarda en procesar)
            reply_btn = page.wait_for_selector(
                '[data-testid="tweetButtonInline"]:not([disabled]), [data-testid="tweetButton"]:not([disabled])',
                timeout=60000 if is_video else 20000,
            )
            reply_btn.click()
            page.wait_for_timeout(10000 if is_video else 6000)

            tweet_id = _extract_tweet_id(page)
            log.info(f"Reply publicado (id={tweet_id}, a {target_url})")
            return tweet_id
        except Exception:
            _save_debug(page, "error_reply")
            raise
        finally:
            context.close()


def post_quote_tweet(text: str, quoted_url: str, image_url: str = "", headless: bool = True) -> str:
    """Publica un quote-tweet: nuestro texto + tarjeta del tweet citado debajo.
    Si image_url se proporciona, añade una foto al tweet propio."""
    if not quoted_url:
        raise ValueError("quoted_url es obligatorio")
    image_path = _download_image(image_url) if image_url else None

    with sync_playwright() as p:
        context = _open_context(p, headless)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            _dismiss_popups(page)

            # Escribimos texto + URL: X detecta la URL y la convierte en quote automáticamente
            full_text = text.rstrip() + "\n\n" + quoted_url
            _type_into_textarea(page, 0, full_text)
            # Espera a que X procese la URL y muestre la quote card
            page.wait_for_timeout(4000)

            if image_path:
                if _attach_media(page, image_path, is_video=False, tweet_index=0):
                    log.info("Foto adjuntada al quote-tweet")

            page.keyboard.press("Control+Enter")
            page.wait_for_timeout(7000)

            tweet_id = _extract_tweet_id(page)
            log.info(f"Quote-tweet publicado (id={tweet_id}, citando {quoted_url})")
            return tweet_id
        except Exception:
            _save_debug(page, "error_quote")
            raise
        finally:
            context.close()
            if image_path:
                image_path.unlink(missing_ok=True)


def post_poll(question: str, options: list[str], headless: bool = True) -> str:
    """Publica una encuesta. Acepta entre 2 y 4 opciones."""
    if not question:
        raise ValueError("La pregunta no puede estar vacía")
    if len(options) < 2 or len(options) > 4:
        raise ValueError(f"Se requieren 2-4 opciones, recibidas: {len(options)}")

    with sync_playwright() as p:
        context = _open_context(p, headless)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            _dismiss_popups(page)

            # 1. Activar modo encuesta
            poll_btn = page.wait_for_selector('[data-testid="createPollButton"]', timeout=15000)
            poll_btn.click()
            page.wait_for_timeout(1500)

            # 2. Escribir la pregunta en el textarea principal
            _type_into_textarea(page, 0, question)

            # 3. Rellenar opciones 1 y 2 (siempre presentes)
            for i, opt in enumerate(options[:2], start=1):
                inp = page.wait_for_selector(f'input[name="Choice{i}"]', timeout=5000)
                inp.click()
                page.keyboard.type(opt, delay=20)
                page.wait_for_timeout(300)

            # 4. Si hay opciones 3 o 4, expandir
            for i, opt in enumerate(options[2:], start=3):
                # Botón para añadir opción
                try:
                    add_choice = page.locator('[data-testid="addChoiceButton"]').first
                    if not add_choice.is_visible():
                        # Buscar por aria-label en español
                        add_choice = page.locator('button[aria-label*="opción" i]').first
                    add_choice.click()
                    page.wait_for_timeout(800)
                except Exception as e:
                    log.warning(f"No se pudo añadir opción {i}: {e}")
                    break
                inp = page.wait_for_selector(f'input[name="Choice{i}"]', timeout=5000)
                inp.click()
                page.keyboard.type(opt, delay=20)
                page.wait_for_timeout(300)

            # 5. Publicar: clic en el botón (Ctrl+Enter no funciona en polls)
            page.wait_for_timeout(1000)
            send_btn = page.wait_for_selector(
                '[data-testid="tweetButton"]:not([disabled]), [data-testid="tweetButtonInline"]:not([disabled])',
                timeout=10000,
            )
            send_btn.click()
            page.wait_for_timeout(6000)

            tweet_id = _extract_tweet_id(page)
            log.info(f"Encuesta publicada (id={tweet_id})")
            return tweet_id
        except Exception:
            _save_debug(page, "error_poll")
            raise
        finally:
            context.close()


def post_thread(tweets: list[str], image_url: str = "", video_path: Path = None,
                image_path: Path = None, article_url_card: str = "",
                headless: bool = True) -> str:
    """Publica un hilo.
    - Si hay vídeo Y imagen: vídeo en tweet 1, imagen en tweet 2.
    - Si solo hay imagen: imagen en tweet 1.
    - Si no hay imagen NI vídeo PERO hay article_url_card: anexamos la URL al final
      del tweet 1 para que X renderice tarjeta-preview con thumbnail del medio.
    Tweets 3+ siempre sin media."""
    if not tweets:
        raise ValueError("Lista de tweets vacía")
    if len(tweets) == 1:
        return post_tweet(tweets[0], image_url=image_url, video_path=video_path,
                          image_path=image_path, headless=headless)

    image_path = image_path if image_path else (_download_image(image_url) if image_url else None)

    # Si no hay media y tenemos URL del artículo, la añadimos al final del tweet 1
    use_url_card = bool(article_url_card) and not (image_path or video_path)
    if use_url_card:
        if len(tweets[0]) + 2 + len(article_url_card) <= 280:
            tweets = list(tweets)
            tweets[0] = tweets[0].rstrip() + "\n\n" + article_url_card

    # Decisión de media por tweet
    if video_path and image_path:
        media_t0, is_video_t0 = video_path, True
        media_t1 = image_path
    elif video_path:
        media_t0, is_video_t0 = video_path, True
        media_t1 = None
    elif image_path:
        media_t0, is_video_t0 = image_path, False
        media_t1 = None
    else:
        media_t0 = media_t1 = None
        is_video_t0 = False

    with sync_playwright() as p:
        context = _open_context(p, headless)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            _dismiss_popups(page)

            _type_into_textarea(page, 0, tweets[0])
            if media_t0:
                if _attach_media(page, media_t0, is_video=is_video_t0, tweet_index=0):
                    log.info(f"{'Vídeo' if is_video_t0 else 'Imagen'} adjuntado al tweet 1")

            for i, text in enumerate(tweets[1:], start=1):
                add_btn = page.wait_for_selector('[data-testid="addButton"]', timeout=10000)
                add_btn.click()
                page.wait_for_timeout(800)
                _type_into_textarea(page, i, text)
                if i == 1 and media_t1:
                    if _attach_media(page, media_t1, is_video=False, tweet_index=1):
                        log.info("Imagen adjuntada al tweet 2")

            page.wait_for_timeout(800)
            page.keyboard.press("Control+Enter")
            page.wait_for_timeout(12000 if video_path else 8000)

            tweet_id = _extract_tweet_id(page)
            log.info(f"Hilo publicado ({len(tweets)} tweets, id={tweet_id})")
            return tweet_id
        except Exception:
            _save_debug(page, "error_thread")
            raise
        finally:
            context.close()
            if image_path:
                image_path.unlink(missing_ok=True)
