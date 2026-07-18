# Profile Extraction Prompt (/profile step)

Turns a finished (or in-progress) advisor conversation into ONE structured `Preferences`
JSON object (preferences.schema.json) for the active vertical. Invoked via `claude -p`.
The full transcript is appended after this prompt.

Note: household facts (carFinancing, homeOwnership, lineCount) belong on the UserState,
not here — a separate extraction fills those. This step fills only the per-vertical
`signals` + a summary. Insurance's legacy-dopolnilno drop is DERIVED from a subscription
line, so it is NOT a signal to extract here.

---

Iz spodnjega pogovora izlusci strukturiran profil potreb uporabnika.

STROGA PRAVILA:
- Vrni TOCNO EN JSON objekt. Nic drugega. Brez uvoda, brez razlage, brez markdown, brez ```code fence``` ograj.
- Objekt mora ustrezati preferences.schema.json.
- Doloci `vertical` na eno od: "telco", "energy", "insurance" (glavna tema pogovora).
- Napolni SAMO `signals` polja, ki ustrezajo temu vertical (spodaj). Cesar uporabnik ni povedal, daj `null`. NE ugibaj.
- `summary`: ena kratka slovenska poved BREZ sumnikov (pisi "cas" ne "č-as", "se" ne "š-e", "ze" ne "ž-e").
- `dontNeed`: konkretni elementi, ki jih uporabnik placuje ali so mu ponujeni, pa jih ne rabi. Ce nic, prazen array [].
- `context`: karkoli koristnega za pogovor, kar ni v signals. Kalkulator tega ne bere.
- Booleani so `true`/`false`/`null`. Stevila so stevila (razen dataNeedGB, ki je niz).

`signals` polja po vertical:
- telco: `dataNeedGB` (niz: "low"/"mid"/"high"/"unlimited" ali stevilka kot "15"), `watchesSport` (bool), `paidTvPacksUsed` (seznam iz "sport"/"movies"/"kids"/"balkan"/"adult"), `wantsFixedBroadband` (bool), `openToSwitchOperator` (bool), `travelsOutsideEU` (bool), `budgetPriority` (bool).
- energy: `annualKwh` (stevilo), `meterType` ("single_ET"/"dual_VT_MT"), `hasGas` (bool), `annualGasKwh` (stevilo), `dayNightSplit` ("mostly_day"/"even"/"mostly_night"), `priceCertaintyPref` ("cheapest_now"/"price_locked"), `contractLockTolerance` ("no_lock"/"ok_12mo"), `eInvoiceOk` (bool).
- insurance: `healthPrefs` `{ valuesFasterPrivateAccess, expectsDentalWork }` (bool), `floodExposed` (bool), `travelFrequency` ("rare"/"occasional"/"frequent"), `coverElsewhere` `{ personalAccident, roadsideAssist }` (bool).

Primer (telco):
{
  "vertical": "telco",
  "summary": "gleda serije, sporta ne gleda, mobilno rabi zmerno",
  "dontNeed": ["sportni paket"],
  "context": ["veliko na wifi"],
  "signals": {
    "dataNeedGB": "mid",
    "watchesSport": false,
    "paidTvPacksUsed": [],
    "wantsFixedBroadband": true,
    "openToSwitchOperator": true,
    "travelsOutsideEU": false,
    "budgetPriority": true
  }
}

Zdaj preberi pogovor in vrni EN JSON objekt:

{{CONVERSATION}}
