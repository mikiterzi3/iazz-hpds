"""I.A.zz — entry point della web app Streamlit.

Avviare dalla radice del repo con:
    streamlit run src/iazz/ui/app.py

CONCETTO: ogni file in `pages/` diventa una voce del menu a sinistra.
Lo stato condiviso tra le pagine vive in `st.session_state["project"]`:
è l'oggetto `Project`, la fonte unica di verità. Questa pagina lo
carica/salva; le altre lo leggono e ci scrivono i risultati.
"""

from pathlib import Path

import streamlit as st

from iazz import __version__
from iazz.core.project import Project

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_JSON = REPO_ROOT / "examples" / "thomas_chiller.json"

st.set_page_config(page_title="I.A.zz — HP Design & Sizing", page_icon="❄️",
                   layout="wide")

st.title("❄️ I.A.zz — Heat Pumps Design & Sizing")
st.caption(f"v{__version__} — progettazione chiller e pompe di calore "
           "con agenti AI specialisti")

# ---------------------------------------------------------- carica/salva
col_load, col_up, col_save = st.columns(3)

with col_load:
    if st.button("📂 Carica demo Thomas", use_container_width=True):
        st.session_state["project"] = Project.load_json(DEMO_JSON)
        st.success("Caso Thomas caricato.")

with col_up:
    uploaded = st.file_uploader("Apri progetto (.json)", type="json",
                                label_visibility="collapsed")
    if uploaded is not None:
        st.session_state["project"] = Project.model_validate_json(
            uploaded.read().decode("utf-8"))
        st.success(f"Progetto «{st.session_state['project'].name}» caricato.")

with col_save:
    if "project" in st.session_state:
        st.download_button(
            "💾 Scarica progetto (.json)",
            data=st.session_state["project"].model_dump_json(indent=2),
            file_name="progetto_iazz.json", mime="application/json",
            use_container_width=True,
        )

st.divider()

# ------------------------------------------------------------- riepilogo
project: Project | None = st.session_state.get("project")
if project is None:
    st.info("Nessun progetto caricato. Carica la demo Thomas oppure un "
            "tuo file JSON — o vai diretto alla pagina **Ciclo** in "
            "modalità manuale.")
else:
    st.subheader(f"Progetto: {project.name}")
    if project.description:
        st.caption(project.description)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Refrigerante", project.refrigerant.name,
              f"GWP {project.refrigerant.GWP100} · "
              f"{project.refrigerant.safety_class}")
    c2.metric("Carico freddo", f"{project.Q_cold_design_kW:.1f} kW",
              project.cold_load.name)
    c3.metric("Richiesta calda", f"{project.Q_hot_design_kW:.1f} kW",
              project.hot_load.name if project.hot_load else "—")
    c4.metric("Regimi", str(len(project.regimes)), project.architecture)

    # Check di simultaneità (F1): il recupero copre il carico caldo?
    chk = project.simultaneity_check()
    if chk["recovery_covers_hot_load"]:
        st.success(f"♻️ Recupero stimato {chk['Q_cond_estimated_kW']} kW ≥ "
                   f"richiesta calda {chk['Q_hot_kW']} kW. {chk['note']}")
    else:
        st.warning(f"♻️ Recupero stimato {chk['Q_cond_estimated_kW']} kW < "
                   f"richiesta calda {chk['Q_hot_kW']} kW. {chk['note']}")

st.markdown(
    """
---
**Moduli** (menu a sinistra): 🔄 *Ciclo termodinamico* — calcolo stati,
COP, diagrammi p-h e T-s, red flag, confronto refrigeranti.
*Compressore, scambiatori, economia…* in arrivo (vedi roadmap).
"""
)
