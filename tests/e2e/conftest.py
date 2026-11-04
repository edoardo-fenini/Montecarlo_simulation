import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

RADICE = pathlib.Path(__file__).resolve().parents[2]


def _porta_libera() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def url_app(tmp_path_factory):
    """Avvia l'app con la finta rete in una cartella di lavoro temporanea (cache e report non toccano il repository)."""
    pytest.importorskip("playwright")
    lavoro = tmp_path_factory.mktemp("e2e")
    os.symlink(RADICE / "configurazioni", lavoro / "configurazioni")
    os.symlink(RADICE / ".streamlit", lavoro / ".streamlit")
    porta = _porta_libera()
    log = open(lavoro / "streamlit.log", "w")
    p = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(RADICE / "tests/e2e/app_finta.py"), "--server.headless", "true",
         "--server.port", str(porta), "--server.address", "127.0.0.1", "--browser.gatherUsageStats", "false"],
        cwd=lavoro, stdout=log, stderr=subprocess.STDOUT,
    )  # fmt: skip
    url = f"http://127.0.0.1:{porta}"
    for _ in range(120):
        try:
            if urllib.request.urlopen(url + "/_stcore/health", timeout=2).status == 200:
                break
        except OSError:
            time.sleep(0.5)
    else:
        p.kill()
        pytest.fail("L'app non si avvia:\n" + (lavoro / "streamlit.log").read_text())
    yield url
    testo_log = (lavoro / "streamlit.log").read_text(errors="replace")
    if "Traceback" in testo_log:  # errori dell'app durante le prove: visibili nel riepilogo di pytest (anche in CI)
        import warnings

        warnings.warn("Errori nel log di Streamlit durante la prova nel browser:\n" + testo_log[-4000:], stacklevel=1)
    p.terminate()
    try:
        p.wait(10)
    except subprocess.TimeoutExpired:
        p.kill()


@pytest.fixture(scope="session")
def browser():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        pronto = pathlib.Path(os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium"))
        try:
            b = p.chromium.launch()
        except Exception:
            cand = sorted(pathlib.Path("/opt/pw-browsers").glob("chromium-*/chrome-linux*/chrome"))
            b = p.chromium.launch(executable_path=str(cand[-1] if cand else pronto), args=["--no-sandbox"])
        yield b
        b.close()


@pytest.fixture
def pagina(browser, url_app):
    ctx = browser.new_context(viewport={"width": 1500, "height": 1000}, accept_downloads=True)
    p = ctx.new_page()
    p.set_default_timeout(60000)
    p.goto(url_app)
    p.get_by_text("Confronto del rischio di portafogli").wait_for()
    yield p
    ctx.close()
