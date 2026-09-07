"""Pagina DIMENSIONA: il flusso di sintesi F4 → F5 → F6.

PROBLEMA: nella pagina ciclo le temperature sono slider liberi (modalità
analisi). Qui NASCONO dai bisogni: l'utente decide gli APPROCCI vedendo
il prezzo di ogni K, e le temperature sono conseguenze.
CONCETTO: tre sezioni in cascata = tre fasi del design_flow:
  F4 catena delle temperature → F5 ciclo → F6 selezione compressore.
La UI non calcola nulla: chain.py, cycle.py, selection.py (testati).
"""

import streamlit as st

from iazz.agents.base import thermodynamic_agent
from iazz.compute.chain import ColdLink, HotSink, TemperatureChain
from iazz.compute.cycle import compute_cycle
from iazz.compute.plausibility import check_cycle
from iazz.compute.selection import select_compressors
from iazz.core.project import Project

st.set_page_config(page_title="Dimensiona", page_icon="📐", layout="wide")
st.title("📐 Dimensiona — dai bisogni al compressore")

project: Project | None = st.session_state.get("project")
if project is None:
    st.info("Carica un progetto dalla home (o la demo Thomas): il "
            "dimensionamento parte dai carichi, non dagli slider.")
    st.stop()

cold = project.cold_load
st.markdown(f"**Carico freddo**: {cold.name} — da {cold.T_in_C:.0f} °C "
            f"a {cold.T_out_C:.0f} °C · **Q di progetto**: "
            f"{project.Q_cold_design_kW:.1f} kW")

# ============================================= F4 — catena temperature
st.header("F4 · Catena delle temperature")
st.caption("Ogni approccio è una decisione: piccolo = COP alto ma "
           "scambiatore grande. Le temperature del ciclo sono derivate, "
           "non scrivibili.")

c1, c2 = st.columns(2)
with c1:
    st.subheader("Lato freddo")
    n_links = st.number_input("Scambiatori in cascata (incluso "
                              "l'evaporatore)", 1, 4, 2)
    links = []
    default_names = ["carico → fluido intermedio",
                     "fluido intermedio → evaporazione",
                     "anello 3", "anello 4"]
    if n_links == 1:
        default_names = ["carico → evaporazione (espansione diretta)"]
    for i in range(int(n_links)):
        cc1, cc2 = st.columns([2, 1])
        name = cc1.text_input(f"Anello {i + 1}", default_names[i],
                              key=f"ln{i}")
        dt = cc2.slider("ΔT [K]", 2.0, 10.0, 3.0, 0.5, key=f"lk{i}")
        links.append(ColdLink(name=name, approach_K=dt))

with c2:
    st.subheader("Lato caldo (pozzi)")
    sinks = []
    if project.hot_load is not None:
        h = project.hot_load
        dt_rec = st.slider(f"ΔT recupero su «{h.name}» "
                           f"(target {h.T_out_C:.0f} °C)",
                           2.0, 10.0, 2.0, 0.5, key="sk_rec")
        sinks.append(HotSink(name=f"{h.name} (recupero)",
                             T_sink_C=h.T_out_C, approach_K=dt_rec))
    t_air = st.number_input("T aria estiva di progetto [°C]",
                            20.0, 50.0,
                            float(project.ambient.T_air_summer_design_C),
                            1.0)
    dt_air = st.slider("ΔT condensatore ad aria", 2.0, 15.0, 2.0, 0.5,
                       key="sk_air")
    sinks.append(HotSink(name="aria estiva", T_sink_C=t_air,
                         approach_K=dt_air))

chain = TemperatureChain(cold_target_C=cold.T_out_C,
                         cold_links=links, hot_sinks=sinks)

m1, m2, m3 = st.columns(3)
m1.metric("T evaporazione (derivata)", f"{chain.T_evap_C:.1f} °C")
m2.metric("T condensazione (derivata)", f"{chain.T_cond_C:.1f} °C")
m3.metric("Pozzo governante", chain.governing_sink.name)

with st.expander("💡 Sensibilità: cosa vale 1 K su ogni anello?"):
    sens = chain.sensitivity_COP_per_K(project.refrigerant)
    for name, val in sens.items():
        if val is None:
            st.write(f"- **{name}**: già al minimo fisico (2 K) — "
                     "nessun margine.")
        elif val == 0:
            st.write(f"- **{name}**: non governa T_cond — stringere "
                     "qui non cambia nulla.")
        else:
            st.write(f"- **{name}**: −1 K ⇒ **+{val:.3f} COP** "
                     f"(≈ {val / 3.5 * 100:.1f} %) — al prezzo di più "
                     "superficie di scambio.")

# ======================================================= F5 — ciclo
st.header("F5 · Ciclo termodinamico")
regime_dim = max(project.regimes, key=lambda r: r.Q_evap_required_kW)
Q_req = st.number_input("Q frigorifera richiesta [kW]", 1.0, 500.0,
                        float(regime_dim.Q_evap_required_kW))
regime = chain.to_regime("dimensionamento", Q_req)
res = compute_cycle(project.refrigerant, regime)

flags = check_cycle(res, regime, project=project)
for f in flags:
    {"info": st.info, "warning": st.warning,
     "critical": st.error}[f.level](f"{f.message}  `{f.code}`")

k1, k2, k3, k4 = st.columns(4)
k1.metric("COP", f"{res.COP_cooling:.2f}")
k2.metric("P compressore", f"{res.W_comp_kW:.1f} kW")
k3.metric("T mandata", f"{res.T_discharge_C:.0f} °C")
k4.metric("Volume aspirato", f"{res.V_dot_suction_m3_h:.1f} m³/h")

# ============================================ F6 — selezione macchina
st.header("F6 · Selezione compressore dal DB")
if any(f.level == "critical" for f in flags):
    st.error("GATE F5 chiuso: risolvi i problemi critici del ciclo "
             "prima di scegliere la macchina (design_flow §2-F5).")
    st.stop()

sel = select_compressors(chain.T_evap_C, chain.T_cond_C, Q_req,
                         project.refrigerant.name)

if not sel.candidates:
    st.warning("Nessuna macchina del DB copre questo punto. Vedi le "
               "scartate qui sotto per capire cosa manca.")
else:
    st.success(f"{len(sel.candidates)} candidate (ordinate per COP reale)")
    rows = [{
        "Modello": f"{c.vendor} {c.model}",
        "VSD": "sì" if c.vsd else "no",
        "f richiesta [Hz]": c.frequency_hz,
        "Q [kW]": round(c.performance.Q_evap_kW, 2),
        "P [kW]": round(c.performance.P_input_kW, 2),
        "COP reale": round(c.performance.COP_cooling, 2),
        "Margine a f_max": f"{c.margin_at_max:.2f}×",
        "Note": c.note or "—",
    } for c in sel.candidates]
    st.dataframe(rows, use_container_width=True)

with st.expander(f"Macchine scartate ({len(sel.rejected)}) — e perché"):
    for r in sel.rejected:
        st.write(f"- **{r.vendor} {r.model}**: {r.reason}")

# ============================================== agente sul contesto
st.divider()
st.subheader("🤖 Agente Termodinamico")
ctx = (f"Flusso di dimensionamento. Catena: T_evap={chain.T_evap_C:.1f} "
       f"°C, T_cond={chain.T_cond_C:.1f} °C (governa: "
       f"{chain.governing_sink.name}). Approcci freddi: "
       + ", ".join(f"{l.name}={l.approach_K:.1f}K" for l in links)
       + f". COP ciclo={res.COP_cooling:.2f}. Candidate: "
       + (", ".join(c.model for c in sel.candidates) or "nessuna")
       + f". Flags: {[f.code for f in flags]}.")
b1, b2, b3 = st.columns(3)
buttons = {
    "🔍 Spiegami": ("explain", b1),
    "⚠ Trova problemi": ("find_problems", b2),
    "💡 Suggerisci alternative": ("suggest", b3),
}
for label, (mode, col) in buttons.items():
    if col.button(label, use_container_width=True):
        try:
            with st.spinner("L'agente sta ragionando..."):
                resp = thermodynamic_agent().ask(ctx, project, mode=mode)
            st.markdown(resp.text)
            with st.expander("System prompt inviato (trasparenza)"):
                st.text(resp.system_prompt[:8000])
        except Exception as exc:
            st.error(f"Agente non disponibile: {exc}")
