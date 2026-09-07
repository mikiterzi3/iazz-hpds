"""Pagina Streamlit: ciclo termodinamico multi-regime.

PROBLEMA: il progettista vuole (a) vedere l'effetto immediato di ogni
scelta, (b) confrontare i regimi del progetto, (c) confrontare i fluidi.
CONCETTO: la UI non calcola MAI nulla: chiama `compute_cycle`,
`check_cycle` e `compare_refrigerants` (tutti testati) e presenta.
"""

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from CoolProp.CoolProp import PropsSI

from iazz.agents.base import thermodynamic_agent
from iazz.compute.compare import compare_refrigerants
from iazz.compute.cycle import CycleResults, compute_cycle
from iazz.compute.plausibility import check_cycle
from iazz.core import refrigerants
from iazz.core.project import Project, Regime

st.set_page_config(page_title="Ciclo termodinamico", page_icon="🔄",
                   layout="wide")
st.title("🔄 Ciclo termodinamico")

project: Project | None = st.session_state.get("project")

# ----------------------------------------------------------- input sidebar
with st.sidebar:
    st.header("Input del ciclo")

    # Sorgente: un regime del progetto caricato, oppure modalità manuale.
    sources = ["Manuale"]
    if project is not None:
        sources = [r.label for r in project.regimes] + ["Manuale"]
    source = st.selectbox("Regime", sources)

    if project is not None and source != "Manuale":
        base = next(r for r in project.regimes if r.label == source)
        default_ref = project.refrigerant.name
    else:
        base = Regime(label="Manuale", T_evap_C=-2.0, T_cond_C=40.0,
                      Q_evap_required_kW=21.76)
        default_ref = "R1234ze(E)"

    all_refs = sorted(refrigerants.REFRIGERANTS)
    # il nome nel progetto può essere la chiave del DB o il nome esteso
    ref_index = next((i for i, n in enumerate(all_refs)
                      if n == default_ref or
                      refrigerants.get(n).name == default_ref), 0)
    ref_name = st.selectbox("Refrigerante", all_refs, index=ref_index)

    T_evap = st.slider("T evaporazione [°C]", -40.0, 20.0,
                       float(base.T_evap_C), 0.5)
    T_cond = st.slider("T condensazione [°C]", 20.0, 80.0,
                       float(base.T_cond_C), 0.5)
    Q_evap = st.number_input("Carico frigorifero [kW]", 1.0, 200.0,
                             float(base.Q_evap_required_kW))
    superheat = st.slider("Surriscaldamento [K]", 0.0, 20.0,
                          float(base.superheat_K), 0.5)
    subcooling = st.slider("Sottoraffreddamento [K]", 0.0, 15.0,
                           float(base.subcooling_K), 0.5)
    eta_is = st.slider("Rendimento isoentropico η_is", 0.5, 0.95,
                       float(base.eta_isentropic), 0.01)

refrigerant = refrigerants.get(ref_name)
regime = Regime(label=source, T_evap_C=T_evap, T_cond_C=T_cond,
                Q_evap_required_kW=Q_evap, superheat_K=superheat,
                subcooling_K=subcooling, eta_isentropic=eta_is)

try:
    res = compute_cycle(refrigerant, regime)
except ValueError as exc:
    st.error(f"⚠ {exc}")
    st.stop()

# salviamo il risultato nel Project state (fonte unica di verità)
if project is not None and source != "Manuale":
    project.cycle_results[source] = res.model_dump()

# --------------------------------------------------------------- red flags
# Il project (se caricato) abilita i controlli incrociati col carico:
# sono quelli che intercettano gli assurdi fisici (es. T_evap sopra il
# target del latte), anche quando gli slider sono in modalità manuale.
flags = check_cycle(res, regime, project=project)
for f in flags:
    {"info": st.info, "warning": st.warning,
     "critical": st.error}[f.level](f"{f.message}  `{f.code}`")

# ---------------------------------------------------------------- metriche
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("COP cooling", f"{res.COP_cooling:.2f}")
c2.metric("COP heating", f"{res.COP_heating:.2f}")
c3.metric("Q condensatore", f"{res.Q_cond_kW:.1f} kW")
c4.metric("W compressore", f"{res.W_comp_kW:.1f} kW")
c5.metric("T mandata", f"{res.T_discharge_C:.0f} °C")

# ------------------------------------------------------------ tabella stati
st.subheader("Stati del ciclo")
st.dataframe(
    [{"Punto": p.label, "Descrizione": p.description,
      "T [°C]": round(p.T_C, 2), "p [bar]": round(p.p_bar, 3),
      "h [kJ/kg]": round(p.h_kJ_kg, 2), "s [kJ/kgK]": round(p.s_kJ_kgK, 4)}
     for p in res.points],
    hide_index=True, use_container_width=True,
)


# ------------------------------------------------------------- diagrammi
@st.cache_data
def saturation_dome(fluid: str) -> dict | None:
    """Campana di saturazione (h, s, T, p) — cache per fluido."""
    try:
        T_crit = PropsSI("Tcrit", fluid)
        T_min = max(PropsSI("Ttriple", fluid), 200.0)
        Ts = np.linspace(T_min, T_crit - 0.5, 120)
        return {
            "T": [t - 273.15 for t in Ts],
            "p": [PropsSI("P", "T", t, "Q", 0, fluid) / 1e5 for t in Ts],
            "h_l": [PropsSI("H", "T", t, "Q", 0, fluid) / 1e3 for t in Ts],
            "h_v": [PropsSI("H", "T", t, "Q", 1, fluid) / 1e3 for t in Ts],
            "s_l": [PropsSI("S", "T", t, "Q", 0, fluid) / 1e3 for t in Ts],
            "s_v": [PropsSI("S", "T", t, "Q", 1, fluid) / 1e3 for t in Ts],
        }
    except ValueError:
        return None  # miscele: campana non disponibile


def cycle_traces(res: CycleResults, x_attr: str, y_attr: str) -> go.Scatter:
    """Poligono del ciclo 1→2→3→4→1 su assi a scelta (h/s vs p/T)."""
    pts = {p.label: p for p in res.points}
    order = ["1", "2", "3", "4", "1"]
    return go.Scatter(
        x=[getattr(pts[k], x_attr) for k in order],
        y=[getattr(pts[k], y_attr) for k in order],
        mode="lines+markers+text", name="Ciclo reale",
        text=[k if i < 4 else "" for i, k in enumerate(order)],
        textposition="top center", line=dict(color="crimson", width=2),
    )


dome = saturation_dome(refrigerant.coolprop_name)
col_ph, col_ts = st.columns(2)

with col_ph:
    st.subheader("Diagramma p-h")
    fig = go.Figure()
    if dome:
        fig.add_trace(go.Scatter(
            x=dome["h_l"] + dome["h_v"][::-1], y=dome["p"] + dome["p"][::-1],
            mode="lines", name="Saturazione", line=dict(color="gray", width=1)))
    fig.add_trace(cycle_traces(res, "h_kJ_kg", "p_bar"))
    fig.update_yaxes(type="log", title="p [bar]")
    fig.update_xaxes(title="h [kJ/kg]")
    fig.update_layout(height=460, legend=dict(orientation="h"))
    st.plotly_chart(fig, use_container_width=True)

with col_ts:
    st.subheader("Diagramma T-s")
    fig = go.Figure()
    if dome:
        fig.add_trace(go.Scatter(
            x=dome["s_l"] + dome["s_v"][::-1], y=dome["T"] + dome["T"][::-1],
            mode="lines", name="Saturazione", line=dict(color="gray", width=1)))
    fig.add_trace(cycle_traces(res, "s_kJ_kgK", "T_C"))
    fig.update_yaxes(title="T [°C]")
    fig.update_xaxes(title="s [kJ/kgK]")
    fig.update_layout(height=460, legend=dict(orientation="h"))
    st.plotly_chart(fig, use_container_width=True)

st.caption("Verifica bilancio energetico: "
           f"Q_cond − (Q_evap + W) = {res.energy_balance_error_kW():+.4f} kW")

# ----------------------------------------------- confronto regimi progetto
if project is not None and len(project.regimes) > 1:
    st.subheader("Confronto regimi del progetto")
    rows = []
    for r in project.regimes:
        try:
            rr = compute_cycle(project.refrigerant, r)
            rows.append({"Regime": r.label, "T_ev [°C]": r.T_evap_C,
                         "T_cond [°C]": r.T_cond_C,
                         "Q_evap [kW]": rr.Q_evap_kW,
                         "Q_cond [kW]": round(rr.Q_cond_kW, 2),
                         "W [kW]": round(rr.W_comp_kW, 2),
                         "COP": round(rr.COP_cooling, 2),
                         "T_mand [°C]": round(rr.T_discharge_C, 1)})
        except ValueError as exc:
            rows.append({"Regime": r.label, "COP": None, "Errore": str(exc)})
    st.dataframe(rows, hide_index=True, use_container_width=True)

# ------------------------------------------------- confronto refrigeranti
with st.expander("🔬 Confronto refrigeranti su questo regime"):
    chosen = st.multiselect("Fluidi da confrontare",
                            sorted(refrigerants.REFRIGERANTS),
                            default=["R1234ze(E)", "R290", "R134a"])
    if chosen:
        comp = compare_refrigerants(regime, names=chosen)
        st.dataframe(
            [{"Refrigerante": r.refrigerant, "GWP": r.GWP100,
              "Sicurezza": r.safety_class, "COP": r.COP_cooling,
              "Q_cond [kW]": r.Q_cond_kW, "W [kW]": r.W_comp_kW,
              "T_mand [°C]": r.T_discharge_C, "p_cond [bar]": r.p_cond_bar,
              "Note": r.error or ""}
             for r in comp],
            hide_index=True, use_container_width=True,
        )
        st.caption("Ordinati per COP. I fluidi non calcolabili mostrano "
                   "il motivo in Note — mai nascondere un fallimento.")

# ------------------------------------------------------ assistente AI (F5)
st.divider()
st.subheader("🤖 Agente Termodinamico")
st.caption("Anteprima F5: con provider 'mock' (default) le risposte sono "
           "finte ma il telaio è reale. Per accenderlo: chiave in .env + "
           "config/providers.yaml.")

_q = {
    "🔍 Spiegami":               ("explain",
        "Spiega i numeri del ciclo attualmente calcolato."),
    "⚠ Trova problemi":          ("find_problems",
        "Verifica input e risultati del ciclo corrente."),
    "💡 Suggerisci alternative":  ("suggest",
        "Proponi alternative migliorative per il ciclo corrente."),
}
cols = st.columns(3)
for col, (label, (mode, question)) in zip(cols, _q.items()):
    if col.button(label, use_container_width=True):
        # il contesto = progetto se caricato, arricchito dal ciclo a schermo
        ctx = project
        try:
            agent = thermodynamic_agent()
            extra = (f"{question}\n\nCiclo a schermo: {res.regime_label}, "
                     f"{refrigerant.name}, COP={res.COP_cooling:.2f}, "
                     f"T_mandata={res.T_discharge_C:.1f} °C, "
                     f"flags={[f.code for f in flags]}")
            resp = agent.ask(extra, ctx, mode=mode)
            st.write(resp.text)
            with st.expander("System prompt inviato (trasparenza)"):
                st.code(resp.system_prompt[:8000], language="markdown")
        except Exception as exc:  # provider mal configurato, chiave assente...
            st.error(f"Agente non disponibile: {exc}")
