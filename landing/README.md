# Frugl — landing + kviz (market-test verzija)

> **„Preveri, ali preplačuješ za položnice — v 60 sekundah."**
> Ena samostojna stran (`index.html`): hero → 4-vprašanjski kviz → rezultat „preplačuješ €X/leto" → email-capture + share-card.
> **Namen te verzije = market test** (merimo, koliko ljudi dokonča kviz in pusti email), zgrajena za hackaton. Dvojezična: **SLO privzeto + EN toggle.**

---

## 1. Zaženi lokalno (10 sekund)

Ni build-a, ni npm-a. Samo statična stran.

```bash
# možnost A — kar odpri datoteko
start index.html            # Windows

# možnost B — lokalni strežnik (priporočeno, da dela clipboard/share)
python -m http.server 8777 --directory .
# → http://localhost:8777/index.html
```

## 2. Deploy (da gre pred prave ljudi)

Katerakoli od teh (vse zastonj, < 2 min):

| Kako | Koraki |
|---|---|
| **Netlify Drop** | povleci `index.html` na https://app.netlify.com/drop → dobiš javni URL |
| **Vercel** | `vercel` v tej mapi, ali povleci v dashboard |
| **GitHub Pages** | push v `Zanoxlr/frugl` → Settings → Pages → deploy from branch |
| **Cloudflare Pages** | connect repo ali drag-and-drop |

Ko dobiš pravo domeno (npr. `frugl.si`), jo vpiši v `CONFIG.SITE_URL` (za share-card povezavo).

---

## 3. Konfiguracija — vse na vrhu `<script>` v `index.html`

```js
const CONFIG = {
  SITE_URL: "https://frugl.si",   // za share-card
  FORM_ENDPOINT: "",              // kam gredo emaili (glej spodaj); prazno = shrani lokalno
  PLAUSIBLE: false,               // true, če dodaš Plausible
  GA_ID: ""                       // "G-XXXX", če dodaš Google Analytics
};
```

### a) Email-capture (`FORM_ENDPOINT`) — da emaili dejansko pridejo do tebe
Brez tega se lead-i shranijo **samo lokalno** (v brskalniku obiskovalca — dobro za demo, neuporabno za pravi test).
Za pravi test v 2 minutah:
1. Naredi obrazec na **[Formspree](https://formspree.io)** ali **[Tally](https://tally.so)** (oba imata free plan).
2. Prilepi njihov endpoint, npr. `FORM_ENDPOINT: "https://formspree.io/f/xxxxxxx"`.
3. Stran pošlje `POST` z: `email, watchdog, vertical, provider, tenure, amount, overpay, lang`.

### b) Cene za izračun (`BENCH`) — srce hooka
```js
const BENCH = { mobile:13, net:29, car:28, home:12 };  // €/mes „najboljša primerljiva cena"
```
To so **indikativne** referenčne cene. **Zamenjaj jih s pravimi iz Testa 1** (spodaj) — AKOS/Tarifnik.
Izračun je namenoma konservativen in nikoli ne pokaže > 60 % prihranka (kredibilnost). Vedno piše „indikativno, potrdi pri ponudniku".

### c) Copy (`T = { sl, en }`)
Vsa besedila (oba jezika) so v objektu `T`. FAQ je polje `T.sl.faq` / `T.en.faq`. Uredi tam.

---

## 4. Kako beriš market-test rezultate

Stran trackira dogodke (v `localStorage`, `console`, in v Plausible/GA če ju dodaš). V **konzoli brskalnika**:

```js
Frugl.stats()    // tabela: quiz_open, quiz_step, quiz_complete, email_captured, share_click ...
Frugl.leads()    // seznam zajetih lead-ov (email + odgovori kviza)
```

**Ključne metrike (kaj šteje):**
- **Kviz-completion %** = `quiz_complete / quiz_open` → ali hook drži (cilj 31–40 %).
- **Email-capture %** = `email_captured / quiz_complete` → ali je bolečina resnična.
- **Share %** = `share_click / quiz_complete` → viralni koeficient (od tega je odvisen CAC ≈ 0).

> Merimo **kviz-completion, ne klikov** — to je bila izrecna zahteva iz analize.

---

## 5. ⚠️ Vzporedno poženi 2 kill-gate testa (brez tega je landing samo polovica testa)

Iz kritičnega audita ([`SESSION_HANDOFF`](../General%20topics%20and%20questions/jeremy%20miner/SESSION_HANDOFF_2026-07-18.md) §4) — landing sam **ne odgovori na 2 vprašanja, ki odločata go/kill**:

1. **TEST 1 — loyalty delta:** vzemi 5–10 pravih računov (mobilni/zavarovanje), primerjaj staro ceno vs najboljša (Tarifnik/AKOS). Če delta **> 15–20 %** → hook drži. Te številke gredo v `BENCH`.
2. **TEST 2 — affiliate rails:** piši 3–5 ponudnikom (Telemach/A1/Telekom/…): dajejo **provizijo za priporočilo/switch**? Če ne → money model rabi drug motor (success-fee / concierge). **Cel prihodek stoji na tem.**

**Odločitev po ~2 tednih:** landing konvertira **IN** Test 1 delta velika **IN** Test 2 rails obstajajo → gradi switch-flow. Sicer pivot/kill. **Nič več kode, dokler ta gate ne pade.**

---

## 6. Poštene opombe (ne skrivaj jih)

- **Kritični audit te ideje = NO-GO za slepo gradnjo** (SLO konkurenti obstajajo, affiliate rails nedokazan, pravni robovi). Ta stran je **cenen test hipoteze**, ne dokaz posla.
- **„€877"** je UK podatek (loyalty penalty), ne slovenski — footnote to pove. Zamenjaj z lastno številko po Testu 1.
- **Izračun je indikativen** — cel flow to pošteno pove; ne obljubljaj točnega zneska.
- **Zavarovanja:** switch/posredovanje zavarovanj lahko rabi AZN/IDD licenco — preveri, preden monetiziraš to vertikalo.
- **GDPR:** email + „watchdog" checkbox = jasno privoli; dodaj pravo Zasebnost stran, preden greš v scale.

---

## 7. Struktura datoteke `index.html`

```
<style>      design system (CSS variables v :root, dark-mode + responsive)
HTML         nav · hero · stat-strip · kako deluje · vertikale · trust · testimonial · FAQ · final CTA · footer
<script>
  CONFIG     ← uredi (endpoint, analytics, domena)
  BENCH      ← uredi (cene za izračun)
  T          ← uredi (copy SLO + EN)
  i18n       applyI18n / setLang
  track()    analytics + localStorage
  KVIZ       state machine (koraki 0–6), compute() izračun, renderResult(), share-card (canvas)
```

## 8. Naslednji koraki

- [ ] Prilepi pravo domeno + `FORM_ENDPOINT` → deploy.
- [ ] Poženi Test 1 + Test 2 (§5) vzporedno.
- [ ] Pridobi ~50–100 obiskov (delitev v skupine, mali FB/IG oglas €20–50, DM-i).
- [ ] Po 2 tednih preberi metrike (§4) + odloči go/pivot/kill.
