"""Demo: ricostruisce il caso fondativo Thomas e calcola i 2 regimi.

Eseguire dalla radice del repo con:
    python examples/thomas_chiller_demo.py

Questo script è il "filo rosso" del progetto: ogni nuovo modulo deve
continuare a riprodurre questi numeri (validazione di non-regressione).
"""

from pathlib import Path

from iazz.compute.cycle import compute_cycle
from iazz.core import refrigerants
from iazz.core.project import FluidTarget, Project, Regime


def build_thomas_project() -> Project:
    """Costruisce il progetto Thomas (chiller stalla 500 vacche)."""
    return Project(
        name="Chiller Thomas 500 vacche",
        description=(
            "Caso fondativo I.A.zz: chiller con recupero termico per "
            "stalla da 500 vacche. Latte 35→4 °C, acqua pozzo 12→19 °C. "
            "Compressore di riferimento: Bitzer 4NES-14Y-40P VSD."
        ),
        refrigerant=refrigerants.get("R1234ze(E)"),
        cold_load=FluidTarget(
            name="Latte mungitura", fluid_type="milk",
            flow_rate_kg_s=0.4292, cp_kJ_kgK=3.9, T_in_C=35, T_out_C=4,
        ),
        hot_load=FluidTarget(
            name="Acqua vacche", fluid_type="water",
            flow_rate_kg_s=0.724, cp_kJ_kgK=4.186, T_in_C=12, T_out_C=19,
        ),
        regimes=[
            Regime(label="A — worst case latte 4°C", T_evap_C=-2,
                   T_cond_C=40, Q_evap_required_kW=21.76),
            Regime(label="B — alleggerito latte 8°C", T_evap_C=2,
                   T_cond_C=40, Q_evap_required_kW=15.06),
        ],
        architecture="precooler_glycol_dual_condenser",
    )


def main() -> None:
    project = build_thomas_project()

    print(f"\n=== {project.name} ===")
    print(f"Refrigerante: {project.refrigerant.name} "
          f"(GWP={project.refrigerant.GWP100}, "
          f"{project.refrigerant.safety_class})")
    print(f"Carico latte: {project.cold_load.Q_kW:.1f} kW\n")

    for regime in project.regimes:
        res = compute_cycle(project.refrigerant, regime)
        # salviamo i risultati nel Project state (come farà la UI)
        project.cycle_results[regime.label] = res.model_dump()

        print(f"--- Regime {res.regime_label} ---")
        print(f"{'Punto':6} {'T [°C]':>8} {'p [bar]':>8} "
              f"{'h [kJ/kg]':>10} {'s [kJ/kgK]':>11}")
        for pt in res.points:
            print(f"{pt.label:6} {pt.T_C:8.2f} {pt.p_bar:8.3f} "
                  f"{pt.h_kJ_kg:10.2f} {pt.s_kJ_kgK:11.4f}")
        print(f"m_dot        = {res.m_dot_kg_s*1000:.1f} g/s")
        print(f"Q_evap       = {res.Q_evap_kW:.2f} kW")
        print(f"Q_cond       = {res.Q_cond_kW:.2f} kW  (recuperabile)")
        print(f"W_comp       = {res.W_comp_kW:.2f} kW")
        print(f"COP cooling  = {res.COP_cooling:.2f}")
        print(f"COP heating  = {res.COP_heating:.2f}")
        print(f"T_discharge  = {res.T_discharge_C:.1f} °C")
        print(f"Rapporto p   = {res.pressure_ratio:.2f}")
        print(f"Check bilancio: {res.energy_balance_error_kW():+.4f} kW\n")

    out = Path(__file__).parent / "thomas_chiller.json"
    project.save_json(out)
    print(f"Progetto salvato in {out}")


if __name__ == "__main__":
    main()
