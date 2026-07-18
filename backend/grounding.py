"""Render a compact, grounded DATA brief per vertical from the normalized catalog.

The advisor's whole contract is "answer ONLY from DATA, quote prices verbatim", so
this must be faithful: skip null tariffs, disclose when a single-tariff rate was
assumed from VT, keep insurance ranges labeled as typical (not exact), and always
carry the OZP figure (the signature insurance reveal is ungrounded without it).

Small on purpose — this is the "distilled advisor-brief" grounding, not the raw files.
"""


def _eur(value):
    if value is None:
        return "?"
    return ("%.5f" % value).rstrip("0").rstrip(".") if isinstance(value, float) else str(value)


# --------------------------------------------------------------------------- #
def _telco_brief(cat):
    lines = ["MOBILNI PAKETI (cena/mes, GB polne hitrosti):"]
    for p in sorted(cat["telco"]["mobilePlans"], key=lambda x: x["priceEur"]):
        fs = "neomejeno" if p["fullSpeedGB"] == float("inf") else "%s GB" % _eur(p["fullSpeedGB"])
        tag = " (samo za starejse)" if p.get("restricted") == "senior" else ""
        lines.append("- %s %s: %s eur/mes, %s%s" % (p["operator"], p["name"], _eur(p["priceEur"]), fs, tag))
    lines.append("TV DODATKI (placljivi paketi):")
    for a in sorted(cat["telco"]["tvAddons"], key=lambda x: x["priceEur"]):
        lines.append("- %s: %s eur/mes" % (a["name"], _eur(a["priceEur"])))
    lines.append("FIKSNI PAKETI (net + tv):")
    for f in sorted(cat["telco"]["fixPackages"], key=lambda x: x["priceEur"]):
        lines.append("- %s %s: %s eur/mes" % (f["operator"], f["name"], _eur(f["priceEur"])))
    return "\n".join(lines)


def _energy_brief(cat):
    lines = ["ELEKTRIKA (cena energije na kWh, brez DDV; fiksna mesecna taksa z DDV):"]
    for p in cat["energy"]["electricity"]:
        parts = []
        if p["etRate"] is not None:
            parts.append("ET %s" % _eur(p["etRate"]))
        if p["vtRate"] is not None:
            parts.append("VT %s" % _eur(p["vtRate"]))
        if p["mtRate"] is not None:
            parts.append("MT %s" % _eur(p["mtRate"]))
        rate = ", ".join(parts) if parts else "?"
        assumed = " (enotarifna cena ni navedena, prikazan VT)" if p["assumedVt"] else ""
        fixed = "fiksno %s eur/mes" % _eur(p["fixedMonthlyEur"]) if p["fixedMonthlyEur"] is not None else "fiksna taksa ni navedena"
        kind = "fiksna cena" if p["isFixed"] else "variabilno"
        lines.append("- %s %s: %s eur/kWh, %s, %s%s" % (p["provider"], p["name"], rate, fixed, kind, assumed))
    lines.append("PLIN (cena na kWh, brez DDV):")
    for g in cat["energy"]["gas"]:
        if g["etRate"] is None:
            continue
        fixed = "fiksno %s eur/mes" % _eur(g["fixedMonthlyEur"]) if g["fixedMonthlyEur"] is not None else "brez navedene fiksne takse"
        lines.append("- %s %s: %s eur/kWh, %s" % (g["provider"], g["name"], _eur(g["etRate"]), fixed))
    lines.append("OPOMBA: na ceno energije se pri VSEH dobaviteljih enako pristejejo omreznina,"
                 " dajatve in 22% DDV. Mesecni znesek = poraba_kWh x cena_na_kWh + fiksna taksa.")
    return "\n".join(lines)


def _insurance_brief(cat):
    ozp = cat["insurance"]["ozp"]
    lines = [
        "OBVEZNI ZDRAVSTVENI PRISPEVEK (OZP): %s eur/mes, obvezen od 2024, prek place/ZZZS."
        % _eur(ozp["currentMonthlyEur"]),
        "OZP je nadomestil staro 'dopolnilno zdravstveno zavarovanje' - to od 2024 NE obstaja"
        " vec kot prostovoljni izdelek; ce ga se kdo placuje loceno zavarovalnici, je odvec.",
        "ZAVAROVALNI IZDELKI (zneski so TIPICNI razponi, ne tocne premije):",
    ]
    for p in cat["insurance"]["products"]:
        if p.get("monthlyRange"):
            rng = "%s-%s eur/mes" % (_eur(p["monthlyRange"][0]), _eur(p["monthlyRange"][1]))
        elif p.get("annualRange"):
            rng = "%s-%s eur/leto" % (_eur(p["annualRange"][0]), _eur(p["annualRange"][1]))
        else:
            rng = "cena odvisna od profila"
        lines.append("- %s %s (%s): tipicno %s" % (p["provider"], p["name"], p.get("type"), rng))
    return "\n".join(lines)


_BUILDERS = {"telco": _telco_brief, "energy": _energy_brief, "insurance": _insurance_brief}


def vertical_brief(vertical, cat):
    """Compact grounded DATA block for the vertical. Raises on unknown vertical."""
    if vertical not in _BUILDERS:
        raise ValueError("no grounding brief for vertical: %r" % (vertical,))
    return _BUILDERS[vertical](cat)


def render_subs(subscriptions, vertical):
    """The user's current lines FOR THIS VERTICAL only (never leak other verticals)."""
    rows = [s for s in (subscriptions or []) if s.get("vertical") == vertical]
    if not rows:
        return "(uporabnik nima trenutne narocnine v tej kategoriji)"
    out = []
    for s in rows:
        price = s.get("monthlyEur")
        out.append("- %s %s: %s eur/mes" % (
            s.get("provider") or "?", s.get("planName") or "?",
            _eur(price) if price is not None else "?"))
    return "\n".join(out)
