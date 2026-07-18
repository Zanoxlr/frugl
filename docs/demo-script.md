# Frugl — Hackathon Demo Script & Pitch

B2C multi-utility subscription advisor. Slovenian market. POC.

> All figures below are reconciled to the live seed (`data/demo_user.json`) and what
> `GET /api/state` + `compare()` actually return. If you change the seed, update this file
> in the same pass so the stage narration never contradicts the screen.

---

## 1. Positioning

### One-liner
Not a bill-lowering service. A pre-sales needs-clarifier that turns a passive, upsellable consumer into an informed buyer, then hands providers a lead that already knows what it wants.

### The problem in one breath
Every incumbent works the same way: "send us your bill, we'll lower it." The consumer stays passive and uninformed. So when a human sales agent finally calls, the consumer can't push back, and gets upsold on the exact stuff they came to cut. The bill "comparison" is bait; the call is the sell.

Frugl flips the order. Inform first, qualify second, hand off last. An informed consumer can't be upsold, and a lead that already understands its own needs is worth more, not less, to the provider.

### Name
**Frugl** is the product name (from "frugal": short, ownable, easy for English-speaking judges). **Jasno** (Slovenian for "clear / obvious") stays as the market-name option for a Slovenian consumer launch. Everything below uses Frugl.

### 30-second elevator pitch
"Slovenians overpay on utilities not because they picked wrong, but because nobody ever showed them what they actually have. The 'send us your bill' services keep them in the dark on purpose, because a confused customer is an easy upsell. Frugl puts all your subscriptions, telco, energy, insurance, water, in one dashboard, then a grounded AI advisor walks you through what you're really paying for and what you can drop. It catches the stuff a salesperson would never mention: a health charge for a product that was abolished two years ago, a mobile plan five times bigger than you use. Once you know your real needs, we match you to a right-fit offer, and we sell that high-intent lead to the provider. They pay for fit, not volume. Informed buyer, cleaner lead, everyone but the upseller wins."

---

## 2. The demo persona — Marko

**Marko Novak, 34, Ljubljana.** Works in IT, lives with his partner in a 2-bedroom apartment in Bežigrad. One car, owned outright. Busy, mildly annoyed by admin, hasn't reviewed a single subscription in years. Pays everything by direct debit and never reads the itemised bills. Typical "set and forget."

His subscriptions, as Frugl sees them after onboarding (real seed lines):

| Vertical | Line (demo, real provider/plan) | Marko pays | Status |
|---|---|---|---|
| Telco (fixed) | A1 Xplore TV maxi+ (fiber internet + TV, ~180 channels) | 55.99 /mo | Keep. Reasonable for a 2-person household. |
| Telco (TV add-on) | A1 Arena Sport Premium | **4.99 /mo** | **GOTCHA 1.** Paid sport add-on, hasn't watched sport in 90 days. Dead spend, cancel outright (~60 EUR/yr). |
| Telco (mobile) | A1 MaksiMIO (unlimited calls/SMS + 500 GB) | **27.99 /mo** | **GOTCHA 2.** Uses ~12-15 GB, pays for 500 GB. Right-size to MidiMIO (200 GB, 20.98) or an MVNO (~10). |
| Energy | Petrol Redni cenik (standard variable electricity, VT 0.12795 /kWh) | 41.90 /mo | Soft nudge. Petrol's own Akcijski promo (VT 0.11795, 1-yr fixed) is ~1 cent/kWh cheaper. Small, real. |
| Insurance (health) | Vzajemna "Dopolnilno zdravstveno zavarovanje" | **35.00 /mo** | **GOTCHA 3 (the big one).** This product was abolished 31 Dec 2023 and replaced 1 Jan 2024 by the compulsory state OZP (~39.36/mo, paid via ZZZS/payroll). He's likely paying OZP AND this redundant legacy charge. Double-paying. |
| Insurance (car) | Triglav Avtomobilsko zavarovanje AO | 25.00 /mo | Leave alone. Legally mandatory motor liability. The honest contrast line. |
| Water | JP VOKA Snaga (municipal water + sewage) | 22.00 /mo | No-sell. Municipal monopoly, can't be switched. Advisor just explains the bill. The trust anchor. |

**Total on the dashboard: 212.87 EUR/mo** (rounds to ~213 on screen). Annual 2554.44.
Per-vertical: telco 88.97, energy 41.90, insurance 60.00 (health 35 + car 25), water 22.00.

**What an honest advisor strips or fixes without downgrading his life:** Arena (4.99), the redundant health charge (35), and right-sizing the mobile plan (saves ~7/mo inside A1, up to ~22 on an MVNO), plus the small energy re-shop. That's **~47 EUR/mo at the conservative end, north of 60 if he moves the mobile line to an MVNO. Roughly 560-740 EUR a year, and every euro of it comes from removing things, not adding them.**

The point of the rig: the health charge is something no comparison site would ever catch, because there's nothing to *switch to*, only a charge to cancel. The other two wins are pure anti-upsell: we drop an add-on he doesn't use and shrink a plan he's outgrown. And on water we deliberately don't sell at all. That combination is the whole story.

---

## 3. Stage flow — tap by tap (~2–3 min)

Keep narration tight. The dashboard and the anti-upsell reveal are the two shots that land; everything else is glue.

**[0:00] Onboarding (10s).**
Open app. "Marko just linked his accounts." One tap through a consent screen ("Frugl reads your bills, never changes anything"). Loading shimmer, then the dashboard populates. Do NOT dwell here.

> Say: "No forms. He connects, we read. Notice we never asked him to upload a bill and wait for a human to call back."

**[0:15] Dashboard — category tiles + total (20s).**
Four category tiles: Telco, Energija, Zavarovanje, Voda. Big total at top: **~213 EUR / mesec.** Each tile shows its monthly number and a status dot (green = looks fine, amber = worth a look). Three amber: Telco, Zavarovanje, Energija. The Zavarovanje tile reads 60 and opens into two policies: zdravstveno (35) and avto (25).

> Say: "Everything he pays for, one screen. He's never seen this before. Three things are already flagged. Let's open the telco one."

**[0:35] Tap Telco → the grounded chat moment (35s).**
Tile expands into a chat with the advisor. The advisor opens with what it actually knows, not a sales line:

> Advisor: "Na tem paketu imaš fiksni internet, TV in mobilni. Zraven plačuješ dodatek Arena Sport Premium za 4.99 EUR na mesec. Arena je ločen TV dodatek, ni vključen v osnovni paket. Zadnjih 90 dni je nisi gledal. Ti jo pustimo ali odstranimo?"

This is the grounded beat. Now ask it the rehearsed factual questions live (section 4) so the judges see it answer accurately about the real package, not vibe.

> Say: "This is the difference. It's not guessing, it's not selling. It knows exactly what's on his plan and it's telling him the add-on is dead weight. A sales agent's job is to keep that Arena on the bill."

**[1:10] Needs discovery (30s).**
Advisor runs a short, plain needs check. Tap-to-answer chips:

1. "Gledaš šport v živo?" → "skoraj nikoli"
2. "Rabiš TV pakete ali večinoma streamaš?" → "večinoma Netflix/YouTube"
3. "Kolko podatkov porabiš na mobilnem na mesec?" → "12–15 GB, večinoma na WiFi"
4. "Imaš še kakšno staro zavarovanje ki ga nisi nikoli preveril?" → "ja, neko zdravstveno"

Each answer feeds a real reveal: no live sport → drop Arena; low mobile data on a 500 GB plan → right-size; the old health line → the double-pay catch.

> Say: "Plain questions, no jargon. And notice it's building his real profile across everything, not just this one bill."

**[1:40] The needs card + the anti-upsell reveal (30s).**
Advisor produces a **Needs Card**. The dramatic bit: it visibly strips things Marko doesn't need. On screen, line items animate out with a strike-through:

> **Tvoj profil**
> ~~Arena Sport Premium (4.99)~~ — ne gledaš športa v živo → **odstrani**
> ~~MaksiMIO 500 GB (27.99)~~ — porabiš 12–15 GB → **preveliko, zmanjšaj na 200 GB ali MVNO**
> ~~Dopolnilno zdravstveno (35)~~ — produkt je 2024 ukinjen, OZP že plačuješ → **podvojeno plačilo, ukini**
> ✓ Fiksni internet + TV — **obdrži**
> ✓ Avto AO — obvezno po zakonu, korekten strošek → **pusti**
> ✓ Voda — občinski monopol, nič za menjat, tvoj račun je korekten

The three struck-through lines are the money shot. The advisor is *removing* things it could have sold him.

> Say (slow down here): "Watch what it just did. It took things OFF. No sports package he doesn't watch. A mobile plan five times bigger than he uses, right-sized. And this one, the big one: he's been paying an insurer 35 euros a month for supplemental health cover that was abolished at the end of 2023. He already pays the state OZP charge for the same thing through his salary. He's been double-paying for two years. No comparison site catches that, because there's nothing to switch to, only a charge to cancel. And on water we tell him to do nothing. We don't sell when there's nothing to sell. That's why he trusts the rest."

**[2:10] Book the right offer → lead saved (20s).**
One clean recommendation card: a right-sized telco profile, the redundant health line flagged for cancellation, and a small energy re-shop to Petrol's fixed promo. Button: **"Poveži me s ponudnikom."** Tap. Confirmation: "Tvoj profil je poslan. Ponudnik ve točno kaj rabiš."

> Say: "One button. The lead that goes to the provider isn't 'guy who wants a cheaper bill.' It's 'Marko, low mobile data, no live sport, streams instead of TV packages, needs his energy re-priced to real usage, don't bother pitching him a bigger plan.' That lead converts, and it doesn't churn, because he already knows it fits. That's what a provider pays us for."

**Total run time: ~2:10.** If time is tight, cut the needs-discovery section to two questions and keep the reveal full-length. Never cut the reveal.

---

## 4. Rehearsed factual questions to ask live

Ask 3 of these during the telco chat beat. They prove the advisor is grounded on the real package, not improvising. Pick based on time.

1. **"Je Arena na tem paketu zastonj?"**
   Expected: "Ne. Arena Sport Premium je ločen TV dodatek za 4.99 EUR na mesec, ni vključen v osnovni paket. Zadnjih 90 dni je nisi gledal." (Grounded: knows it's a paid add-on AND that it's unused.)

2. **"Kolko kanalov dobim na tem paketu?"**
   Expected: "Xplore TV maxi+ ima okoli 180 kanalov. Če večinoma streamaš, plačuješ za pakete ki jih ne gledaš." (Grounded on his tier, then honest.)

3. **"Kolko podatkov mi daje mobilni paket?"**
   Expected: "MaksiMIO ti da 500 GB, ti pa porabiš okoli 12–15 GB, večinoma na WiFi. MidiMIO (200 GB, 20.98) ali MVNO za ~10 te pokrije za manj." (Grounded on the real plan size vs real usage.)

4. **"Zakaj mi je zdravstveno označeno rdeče?"**
   Expected: "Ker plačuješ staro dopolnilno zdravstveno zavarovanje pri zavarovalnici. To je bilo konec 2023 ukinjeno in nadomeščeno z obveznim prispevkom OZP (~39.36 EUR), ki ga že plačuješ prek plače. Torej plačuješ dvakrat za isto stvar." (The wow fact, delivered on demand.)

5. **"A mi splača menjat ponudnika elektrike?"**
   Expected: "Od marca 2025 ni več cenovne kape, cene so tržne. Tvoj strošek = poraba × cena na kWh + fiksni del. Na Petrolovem rednem ceniku si (VT 0.12795); njihov akcijski (VT 0.11795, fiksen 1 leto) je ~1 cent na kWh cenejši. Prihranek je majhen ampak realen." (Grounded on the post-cap reality and the real tariff numbers, not a flat "switch and save.")

**Safety line if asked something out of data:** the advisor should say "Tega podatka nimam, ne bom ugibal" rather than invent. Have one such question ready if a judge tries to break it.

---

## 5. Judge Q&A prep

**(a) "You promise not to upsell, but you sell leads to sellers. Why does that work / isn't that the same thing?"**
Different transaction. Incumbents sell *volume*: any warm body, upsold as hard as possible, high churn. We sell *fit*. The provider pays for a pre-qualified, high-intent lead that already understands its own needs. Those leads convert at a much higher rate and churn far less, because the customer bought something that actually fits instead of being talked into extras. The provider's economics reward fit over volume: lower CAC-to-retention, fewer cancellations, less support load. We're not hiding the sale, we're removing the manipulation from it. The consumer gets an honest match; the provider gets a customer that sticks. The only loser is the upsell.

**(b) "Is the data real or mocked?"**
The persona is scripted; the facts behind every answer are not. Every plan name, tier, and unit price traces to the real grounding corpus in the repo: telco packages and add-on prices from operator data (`data/telco/`), electricity tariffs from `data/energy.json` (the Petrol Redni vs Akcijski per-kWh comparison is real post-cap math), insurance and the 2024 dopolnilno→OZP regulatory change from `data/insurance.json`, municipal water from `data/water.json`. Bundle figures without a public monthly price are illustrative and flagged as such in the seed. The numbers you see on screen are what the deterministic calculator computes, not hand-typed slides.

**(c) "What stops the AI from hallucinating?"**
It's grounded-only. Every answer is tied to a known data point about the user's actual plan or a verified regulatory fact. When the data isn't there, it refuses: "Tega podatka nimam, ne bom ugibal." It doesn't fill gaps with plausible-sounding numbers. You can try to break it live, ask it something it can't know and watch it decline instead of invent. That refusal behavior is the feature, because a single wrong number destroys the trust the whole model depends on.

**(d) "Isn't this just a comparison site with a chatbot on top?"**
No. A comparison site answers "who's cheapest" for a product you already decided you want. It keeps you passive. The whitespace here is *conversational needs-definition plus anti-upsell*: we work out what you actually need before anyone shows you an offer, and we visibly remove things you don't need, including things we could have sold you. A comparison site would never tell you to cancel a health charge or shrink your mobile plan, there's no affiliate payout in telling you to buy less. The output isn't a price ranking, it's a pre-sales needs profile. That profile is the product, for the consumer and for the provider. Nobody else builds that.

---

## Appendix — fact sheet (verified July 2026)

- **Dopolnilno zdravstveno abolished 31 Dec 2023**, replaced 1 Jan 2024 by the compulsory state charge **OZP (~39.36 EUR/mo since March 2026, collected via ZZZS/payroll)**. Many still pay a legacy/redundant health charge to an insurer on top. Advisor catches the double-pay. This is the demo's biggest single reveal.
- **Energy price caps ended March 2025** → prices market-set, real comparison possible. Cost = usage (kWh) × per-kWh price + fixed fee. Not a flat bill. Marko's line is electricity only (~250 kWh/mo apartment); the promo-vs-standard gap is small but real.
- **Mobile over-provisioning:** a top-tier 500 GB plan (MaksiMIO, 27.99) on a user burning 12–15 GB. Right-size to 200 GB (MidiMIO, 20.98) or an MVNO (~10). Anti-upsell, not a switch-for-switch's-sake.
- **Telco add-ons:** paid extras like Arena Sport Premium (4.99/mo) that people pay for and don't use.
- **Water = municipal monopoly, no switching.** Advisor only explains the bill honestly. This is a deliberate no-sell, and it's what earns trust for everything else.
