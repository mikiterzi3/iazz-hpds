"""Pagina NUOVO PROGETTO: intake conversazionale (F0) su scheda fissa.

PROBLEMA: una lista di "cose capite" non mostra la forma del buco.
CONCETTO: come il foglio 2_INPUT_GLOBALE dell'Excel Thomas — TUTTE le
caselle che servono sono sempre visibili, con lo stato di ciascuna:
🟢 compilata · 🔴 manca (obbligatoria) · ⚪ facoltativa vuota.
Tu racconti, l'agente riempie le caselle, la scheda mostra il resto.
"""

import streamlit as st

from iazz.agents.intake import (
    IntakeDraft, build_project, missing_fields, run_intake,
)

st.set_page_config(page_title="Nuovo progetto", page_icon="🎤",
                   layout="wide")
st.title("🎤 Nuovo progetto — racconta, io compilo la scheda")

st.caption("Descrivi il problema come a un collega. L'agente NON "
           "inventa: riempie solo le caselle che le tue parole "
           "coprono, il resto te lo chiede. Il progetto nasce quando "
           "confermi tu.")

if "intake_draft" not in st.session_state:
    st.session_state.intake_draft = None
    st.session_state.intake_questions = []

draft: IntakeDraft | None = st.session_state.intake_draft

# ============================================== struttura della scheda
# (sezione, [ (etichetta, campo, obbligatorio, unità) ])
SECTIONS = [
    ("📌 Anagrafica", [
        ("Nome progetto", "name", True, ""),
        ("Descrizione", "description", False, ""),
    ]),
    ("❄️ Carico freddo — il cuore del problema", [
        ("Cosa raffreddiamo", "cold_name", True, ""),
        ("Tipo di fluido", "cold_fluid_type", True,
         "water/milk/glycol30/air/brine"),
        ("T ingresso", "cold_T_in_C", True, "°C"),
        ("T finale richiesta", "cold_T_out_C", True, "°C"),
        ("Portata", "cold_flow_rate_kg_s", False, "kg/s"),
        ("— oppure volume/giorno", "cold_volume_L_day", False, "L/g"),
        ("— con ore di processo/giorno", "cold_hours_per_day", False, "h"),
    ]),
    ("🔥 Recupero / carico caldo (se esiste)", [
        ("Cosa scaldiamo", "hot_name", False, ""),
        ("Fluido", "hot_fluid_type", False, ""),
        ("T ingresso", "hot_T_in_C", False, "°C"),
        ("T richiesta", "hot_T_out_C", False, "°C"),
        ("Portata", "hot_flow_rate_kg_s", False, "kg/s"),
    ]),
    ("🌍 Sito e sorgenti", [
        ("T aria estiva di progetto", "T_air_summer_C", False, "°C"),
        ("T acqua di pozzo", "T_well_water_C", False, "°C"),
    ]),
    ("⚖️ Vincoli (decidono l'architettura!)", [
        ("Contatto alimentare/sanitario", "food_contact", False, "sì/no"),
        ("Altri vincoli di sicurezza", "safety_constraints", False, ""),
    ]),
    ("🎛️ Preferenze", [
        ("Refrigerante preferito", "refrigerant_preference", False, ""),
        ("Q frigorifera se già nota", "Q_design_kW", False, "kW"),
    ]),
]


def _flow_ok(d: IntakeDraft) -> bool:
    return d.cold_flow_rate_kg_s is not None or (
        d.cold_volume_L_day is not None and d.cold_hours_per_day is not None)


def render_sheet(d: IntakeDraft) -> None:
    """La scheda stile Excel: ogni casella col suo stato."""
    for title, rows in SECTIONS:
        st.markdown(f"**{title}**")
        for label, field, required, unit in rows:
            value = getattr(d, field)
            if value is not None:
                shown = {True: "sì", False: "no"}.get(value, value)
                suffix = unit if unit and unit[0] in "°kLh%" else ""
                st.markdown(f"🟢 {label}: **{shown}** {suffix}")
            elif required:
                st.markdown(f"🔴 {label} — *manca (obbligatorio)* "
                            f"{f'[{unit}]' if unit else ''}")
            else:
                st.markdown(f"⚪ {label} {f'[{unit}]' if unit else ''}")
    # la portata è obbligatoria "in alternativa": stato dedicato
    if not _flow_ok(d):
        st.markdown("🔴 **Portata**: serve `portata` **oppure** "
                    "`volume/giorno + ore/giorno`")
    if d.closed_topics:
        st.caption("Argomenti chiusi su tua richiesta: "
                   + ", ".join(d.closed_topics))


# ================================================================ input
placeholder = ("Es.: chiller per il latte di una stalla da 500 vacche, "
               "12.000 litri al giorno, mungitura in due finestre da "
               "4 ore. Il latte esce a 35 °C e va portato a 4 °C...")
description = st.text_area(
    "La tua descrizione" if draft is None
    else "Risposte / nuove informazioni",
    height=140, placeholder=placeholder)

if st.button("📨 Invia all'agente", type="primary"):
    if not description.strip():
        st.warning("Scrivi qualcosa prima di inviare.")
    else:
        try:
            with st.spinner("L'agente sta compilando la scheda..."):
                result = run_intake(description, previous=draft)
            st.session_state.intake_draft = result.draft
            st.session_state.intake_questions = result.questions
            st.rerun()
        except Exception as exc:
            st.error(f"Intake non riuscito: {exc}")
            st.caption("Questa pagina richiede il provider vero per "
                       "'coordinator' in config/providers.yaml.")

# ================================================================ scheda
draft = st.session_state.intake_draft
sheet = draft if draft is not None else IntakeDraft()
lacking = missing_fields(sheet)

# barra di avanzamento sugli obbligatori
required_total = sum(1 for _, rows in SECTIONS
                     for _, _, req, _ in rows if req) + 1   # +1 portata
required_done = sum(
    1 for _, rows in SECTIONS
    for _, f, req, _ in rows if req and getattr(sheet, f) is not None)
required_done += 1 if _flow_ok(sheet) else 0
st.progress(required_done / required_total,
            text=f"Scheda: {required_done}/{required_total} "
                 "caselle obbligatorie compilate")

c1, c2 = st.columns([3, 2])
with c1:
    st.subheader("📋 Scheda di progetto")
    render_sheet(sheet)
with c2:
    st.subheader("❓ L'agente chiede")
    qs = st.session_state.intake_questions
    if draft is None:
        st.write("(La scheda si riempie quando racconti: comincia "
                 "dalla descrizione qui sopra.)")
    else:
        for q in qs:
            st.write(f"- {q}")
        if not qs:
            st.write("Nessuna domanda.")
        elif not lacking:
            st.caption("Gli obbligatori ci sono: queste sono "
                       "rifiniture. Puoi rispondere o confermare.")

# =============================================================== firma
if draft is not None and not lacking:
    st.divider()
    st.success("La scheda regge: rileggi le caselle verdi — firmi tu.")
    if st.button("✅ Conferma e crea il progetto", type="primary"):
        project = build_project(draft)
        st.session_state["project"] = project
        st.session_state.intake_draft = None
        st.session_state.intake_questions = []
        st.balloons()
        st.success(f"Progetto «{project.name}» creato. Ora apri "
                   "**📐 Dimensiona**: si parte dalla catena delle "
                   "temperature (F4).")
