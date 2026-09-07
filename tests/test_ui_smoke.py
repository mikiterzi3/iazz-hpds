"""Smoke test della UI: le pagine devono eseguire senza eccezioni.

CONCETTO: `streamlit.testing.v1.AppTest` esegue lo script della pagina
in un runtime finto, senza browser. Non verifica l'estetica, ma prende
al volo errori di import, refusi e chiamate rotte — il 90% dei bug UI.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_home_page_runs():
    at = AppTest.from_file(str(REPO_ROOT / "src/iazz/ui/app.py"),
                           default_timeout=30)
    at.run()
    assert not at.exception


def test_cycle_page_runs_manual_mode():
    at = AppTest.from_file(str(REPO_ROOT / "src/iazz/ui/pages/02_cycle.py"),
                           default_timeout=60)
    at.run()
    assert not at.exception


def test_cycle_page_runs_with_thomas_project():
    """Con il progetto Thomas in sessione: tab regimi + confronto."""
    from iazz.core.project import Project

    at = AppTest.from_file(str(REPO_ROOT / "src/iazz/ui/pages/02_cycle.py"),
                           default_timeout=60)
    at.session_state["project"] = Project.load_json(
        REPO_ROOT / "examples" / "thomas_chiller.json")
    at.run()
    assert not at.exception


def test_nuovo_progetto_page_runs():
    """La pagina intake esegue (senza click: nessuna chiamata API)."""
    at = AppTest.from_file(
        str(REPO_ROOT / "src/iazz/ui/pages/01_nuovo_progetto.py"),
        default_timeout=60)
    at.run()
    assert not at.exception


def test_dimensiona_page_without_project_shows_info():
    """Senza progetto la pagina di sintesi si ferma con l'invito."""
    at = AppTest.from_file(
        str(REPO_ROOT / "src/iazz/ui/pages/03_dimensiona.py"),
        default_timeout=60)
    at.run()
    assert not at.exception


def test_dimensiona_page_runs_with_thomas_project():
    """Il wizard F4→F6 esegue sul caso Thomas: catena, ciclo, selezione."""
    from iazz.core.project import Project

    at = AppTest.from_file(
        str(REPO_ROOT / "src/iazz/ui/pages/03_dimensiona.py"),
        default_timeout=120)
    at.session_state["project"] = Project.load_json(
        REPO_ROOT / "examples" / "thomas_chiller.json")
    at.run()
    assert not at.exception
