# Profile Extraction Prompt (/profile step)

Used to turn a finished (or in-progress) advisor conversation into ONE structured `NeedsProfile` JSON object. Invoked via `claude -p`. The full conversation transcript is appended after this prompt.

---

Iz spodnjega pogovora izlusci strukturiran profil potreb uporabnika.

STROGA PRAVILA:
- Vrni TOCNO EN JSON objekt. Nic drugega. Brez uvoda, brez razlage, brez markdown, brez ```code fence``` ograj.
- Objekt mora ustrezati semi needs_profile.schema.json.
- Doloci `vertical` na eno od: "telco", "energy", "insurance" (glavna tema pogovora).
- Napolni SAMO blok, ki ustreza `vertical` (npr. ce vertical="telco", napolni "telco"; drugih dveh ne dodajaj).
- Ce nekega podatka uporabnik ni povedal, daj `null`. NE ugibaj in NE izmisljaj vrednosti.
- `summary`: ena kratka slovenska poved BREZ sumnikov (pisi "cas" ne "čas", "se" ne "še", "ze" ne "že").
- `dontNeed`: konkretni elementi, ki jih uporabnik placuje ali so mu ponujeni, pa jih ne rabi (npr. "sportni paket", "GAP kritje", "dopolnilno zdravstveno"). Ce nic takega, vrni prazen array [].
- Boolean polja so `true`/`false`/`null`. Stevila so stevila, ne nizi (razen dataNeedGB, ki je niz).

Struktura, ki jo vrnes (primer za telco; napolni glede na vertical):
{
  "vertical": "telco",
  "summary": "...",
  "dontNeed": ["..."],
  "telco": {
    "watchesSport": false,
    "wantsSpecialChannels": null,
    "phoneCount": 2,
    "dataNeedGB": "mid",
    "worksFromHome": true,
    "wantsFixedBroadband": true,
    "budgetPriority": false
  }
}

Zdaj preberi pogovor in vrni EN JSON objekt:

{{CONVERSATION}}
