"""Database dei refrigeranti supportati da I.A.zz (scope v0.5).

PROBLEMA
    Per ogni refrigerante servono: il nome esatto che CoolProp capisce,
    il GWP (per la parte ambientale/economica F-Gas) e la classe di
    sicurezza ASHRAE 34 (per i vincoli normativi EN 378).

CONCETTO
    Un semplice dizionario Python nome → Refrigerant. Niente database
    vero per ora: 7 fluidi stanno benissimo in un dict. Quando il DB
    crescerà (v1.5) migreremo su JSON/SQLite senza cambiare l'interfaccia.

SCELTE
    - GWP100 da IPCC AR5 / Regolamento F-Gas (valori usati nel caso Thomas).
    - `get()` solleva un errore parlante invece di un KeyError muto:
      l'utente del tool deve capire subito cosa è andato storto.
"""

from __future__ import annotations

from iazz.core.project import Refrigerant

# Scope v0.5: HFO, HFC e naturali per chiller 5-100 kW.
REFRIGERANTS: dict[str, Refrigerant] = {
    "R1234ze(E)": Refrigerant(
        name="R1234ze(E)", GWP100=7, safety_class="A2L", coolprop_name="R1234ze(E)"
    ),
    "R1234yf": Refrigerant(
        name="R1234yf", GWP100=4, safety_class="A2L", coolprop_name="R1234yf"
    ),
    "R134a": Refrigerant(
        name="R134a", GWP100=1430, safety_class="A1", coolprop_name="R134a"
    ),
    # NOTA — R513A (miscela R134a/R1234yf) è nello scope v1.0 ma NON in
    # questo DB: CoolProp non supporta il flash (P,s) per le miscele,
    # che serve per lo stato 2s del ciclo. Lo aggiungeremo quando
    # implementeremo un flash iterativo o tabelle dedicate (decisione
    # registrata nella roadmap, sezione "Decisioni tecniche").
    "R290": Refrigerant(
        name="R290 (propano)", GWP100=3, safety_class="A3", coolprop_name="Propane"
    ),
    "R744": Refrigerant(
        name="R744 (CO2)", GWP100=1, safety_class="A1", coolprop_name="CO2"
    ),
    "R717": Refrigerant(
        name="R717 (ammoniaca)", GWP100=0, safety_class="B2L", coolprop_name="Ammonia"
    ),
}


def get(name: str) -> Refrigerant:
    """Restituisce un refrigerante per nome, con errore parlante se assente.

    Args:
        name: nome commerciale, es. "R1234ze(E)".

    Returns:
        L'oggetto Refrigerant corrispondente.

    Raises:
        KeyError: se il refrigerante non è nel database v0.5.
    """
    try:
        return REFRIGERANTS[name]
    except KeyError:
        disponibili = ", ".join(sorted(REFRIGERANTS))
        raise KeyError(
            f"Refrigerante '{name}' non nel database v0.5. "
            f"Disponibili: {disponibili}"
        ) from None
