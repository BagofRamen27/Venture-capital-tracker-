# Competitive and Disruption Analysis Toolkit

*Venture Scout · for comparing a startup against established companies in its field · October 2026*

This toolkit is a repeatable process for one question: **can this startup beat the incumbents in its field, and why?** It has four stages. Each stage uses a few frameworks and has a fill-in template. The scorecard in Stage 4 turns everything into one comparable number per startup, so profiles on the site can be ranked against each other.

> "Destructive" analysis here means **disruption analysis**: testing whether a startup can displace incumbents, not only compete with them.

---

## How to use it

| Stage | Question | Tools | Time |
|---|---|---|---|
| 1. Map the arena | Who really competes, and is the industry worth winning? | Competitor set, Five Forces | 30 min |
| 2. Compare the offer | How is the startup shaped differently from incumbents? | Positioning map, Strategy canvas + ERRC, Jobs-to-be-Done | 45 min |
| 3. Test for disruption | Is this disruption, a sustaining competitor, or a feature? | Christensen checklist, Distribution race, AI Incumbent Test | 30 min |
| 4. Test durability and score | Can the edge last? | 7 Powers, VRIO, Scorecard | 30 min |

Use the **field selector** at the end to decide which tools to go deeper on for fintech, healthcare, consumer, B2B software or hardware.

---

## Stage 1: Map the arena

### 1a. Build the competitor set

Founders usually list only direct rivals. Porter warns that defining competition too narrowly is the most common mistake, and Sequoia's pitch guidance says "doing nothing" is always a competitor.

A company counts as a competitor if it matches on at least two of these (Antler-style test): **same customer**, **same problem**, **comparable solution**.

| Type | Examples to look for | Name them |
|---|---|---|
| Direct incumbents | Market leaders selling the same thing | |
| Direct startups | Funded startups with the same pitch | |
| Indirect / substitutes | Different product, same job (spreadsheets, agencies, in-house teams) | |
| Inertia | What customers do today if they buy nothing | |
| Adjacent giants | Big platforms that could ship this as a feature | |

### 1b. Five Forces (Porter)

Run this on the **industry**, then ask which force the startup weakens or exploits. It tells you whether the arena is profitable; it says little about one early-stage company, so don't stop here.

| Force | Strength (Low / Med / High) | Evidence | Does the startup change it? |
|---|---|---|---|
| Rivalry among existing competitors | | | |
| Threat of new entrants | | | |
| Threat of substitutes | | | |
| Buyer power | | | |
| Supplier power | | | |

Notes from Porter: fast growth doesn't mean the industry is profitable, and regulation isn't a sixth force — it works by shifting the five. That matters for fintech and healthcare.

---

## Stage 2: Compare the offer

### 2a. Positioning map

Pick **two axes customers actually care about** (from customer interviews or reviews, not the founder's deck — founders choose axes that flatter them). Plot the startup and every competitor from Stage 1. A strong startup sits in an empty quadrant that real customers want.

```
            High ease of use
                  |
   [Startup?]     |     [ ]
                  |
 Low price -------+------- High price
                  |
       [ ]        |   [Incumbent A] [Incumbent B]
                  |
            Low ease of use
```

Common axis pairs: price vs. capability, ease of setup vs. customisation, self-serve vs. sales-led, speed vs. accuracy.

### 2b. Strategy canvas and ERRC grid (Blue Ocean)

List the 6–10 factors the industry competes on. Score the incumbent and the startup 1–5 on each. Then fill the ERRC grid for the startup. A credible disruptor usually **eliminates or reduces** things incumbents prize and **creates** something new. A startup that only raises and creates is often over-engineered and too costly (the authors' own warning).

| Factor | Incumbent (1–5) | Startup (1–5) |
|---|---|---|
| Price | | |
| Feature breadth | | |
| Setup time | | |
| Support / service | | |
| *(new factor the startup creates)* | 0 | |

| Eliminate | Reduce | Raise | Create |
|---|---|---|---|
| | | | |

### 2c. Jobs-to-be-Done

People "hire" a product to make progress in a situation. The job has functional, social and emotional sides. This often reveals competitors the feature list misses — the Christensen Institute's milkshake study found morning milkshakes competed with bananas and bagels, not other milkshakes.

> When **[situation]**, the customer wants to **[progress]**, so they can **[outcome]**. Today they hire **[current solution]**, which fails because **[pain]**.

Then ask: is the startup **10x better** on the one dimension that matters for this job (Thiel's test)? If it's only 20% better, incumbents rarely lose customers over it.

---

## Stage 3: Test for disruption

### 3a. Christensen disruption checklist

Christensen's theory is narrow. Per the 2015 HBR update, disruption is a **process**: an entrant starts with customers incumbents overserve (low end) or people who weren't buying at all (new market), then improves until it takes the mainstream. Success isn't part of the definition, and most successful startups aren't disruptive in this sense.

| # | Question | Yes / No | Evidence |
|---|---|---|---|
| 1 | Does it start with overserved low-end customers or non-consumers? | | |
| 2 | Is it worse on the incumbent's main metric but better on a new one (price, convenience, access)? | | |
| 3 | Do incumbents have a rational profit reason to ignore it? | | |
| 4 | Is there a clear path to improve and move upmarket? | | |

**Verdict:**
- **4 yes → Disruptive** (e.g., Netflix: DVD-by-mail served a niche Blockbuster could ignore, then streaming met mainstream needs).
- **Mostly no, but wins mainstream customers with a better product → Sustaining competitor** (HBR's example: Uber started in a well-served taxi market with mainstream riders).
- **Could be shipped as a button by an incumbent → Feature risk** (go to 3c).

**Use with caution.** A 2015 study (King & Baatartogtokh, MIT Sloan) found only 9% of 77 cases Christensen cited met all four parts of the theory, and Ben Thompson argues low-end disruption works poorly for consumer products. Treat the label as one input, not the verdict.

**Which incumbent weakness? (Gans).** *Demand-side*: incumbents are focused on their best customers and miss the niche. *Supply-side*: incumbents lack the capabilities to build the new thing (e.g., hardware firms needing software skills). Note which one applies — supply-side gaps usually last longer.

### 3b. Distribution vs. innovation race (a16z, Rampell)

The whole contest is a race: **does the startup get distribution before the incumbent gets the innovation?** Usually the incumbent copies and wins on distribution.

| Question | Answer |
|---|---|
| Who owns the customer relationship today? | |
| Can the startup reach customers without going through an incumbent? | |
| How long would an incumbent need to copy the core product? | |
| How fast is the startup acquiring customers / users? | |
| Does the startup depend on an incumbent's rails (cable boxes, card networks, app stores)? | |

If the startup depends on incumbent rails and copying is easy, the risk is high.

### 3c. AI-era Incumbent Test

2025–26 investor thinking has turned against the "incumbents are slow" assumption. 500 Global (May 2026) argues speed, UX and being first can be matched within a quarter. Lightspeed says that once AI is commoditised, distribution decides, and attacking an incumbent's own AI feature head-on is very hard.

| Test | Yes / No |
|---|---|
| Owns a complex, hard-to-enter **workflow**? | |
| Builds **proprietary data that compounds** with use? | |
| Has **sector depth** that is hard to copy? | |
| Sells **finished outcomes** (autopilot) rather than tools for professionals (copilot)? | |
| Uses a **business model incumbents can't adopt** without hurting their own revenue? | |

All "no" means the moat is fragile. Sequoia's March 2026 "Services: The New Software" thesis adds that outcome-selling AI puts per-seat software vendors in an innovator's dilemma, with the most openings in fragmented, already-outsourced work such as accounting, claims, tax, legal and healthcare billing.

---

## Stage 4: Test durability and score

### 4a. Helmer's 7 Powers

Score each power **0–2** for the startup today, the startup in 5 years if the plan works, and the strongest incumbent today.

| Power | What it means | Startup now | Startup in 5 yrs | Incumbent now |
|---|---|---|---|---|
| Counter-positioning | A model the incumbent can't copy without damaging its own business (Netflix vs broadcasters, Vanguard vs active managers) | | | |
| Cornered resource | Unique team, IP, licence or data | | | |
| Network economies | Gets more valuable as more people use it | | | |
| Switching costs | Painful to leave | | | |
| Scale economies | Cost per unit falls with size | | | |
| Process power | Hard-to-copy way of operating | | | |
| Branding | Customers pay more for the name | | | |

At seed stage, **counter-positioning** and **cornered resource** are the realistic powers. Network effects and switching costs are the path to power, not something a young startup already has. For network effects, NFX lists 16 types (marketplace, platform, data, social and more); name the exact type rather than writing "network effects."

### 4b. VRIO check on the startup's main claimed advantage

| Question | Yes / No |
|---|---|
| Valuable? | |
| Rare? | |
| Costly to imitate? | |
| Organised to exploit it? | |

Not valuable = disadvantage · valuable only = parity · valuable + rare but imitable = temporary edge · all four = sustained advantage.

### 4c. Venture Scout scorecard

Score each line 0–2 (0 = weak / no evidence, 1 = plausible, 2 = strong evidence). Maximum 20.

| # | Criterion | Source tool | Score (0–2) |
|---|---|---|---|
| 1 | **Why now:** a named, dated shift (technology, regulation, behaviour) | Sequoia | |
| 2 | **Market:** credible bottom-up market size, not "if we get 1%" | TAM/SAM/SOM | |
| 3 | **Arena:** industry forces favourable or weakened by the startup | Five Forces | |
| 4 | **Differentiation:** empty, wanted spot on the positioning map / ERRC | Positioning, Blue Ocean | |
| 5 | **10x:** 10x better on the job that matters | JTBD, Thiel | |
| 6 | **Disruption path:** passes the Christensen checklist, or has a clear sustaining edge | Christensen, Gans | |
| 7 | **Distribution race:** can reach customers before incumbents copy | Rampell | |
| 8 | **Incumbent-proof:** passes the AI Incumbent Test | 500 Global, Lightspeed, Sequoia | |
| 9 | **Counter-positioning:** copying would hurt the incumbent's profits | 7 Powers | |
| 10 | **Path to lasting power:** named network effect, switching cost, data or cornered resource | 7 Powers, VRIO, NFX | |
| | **Total** | | **/20** |

**Reading the score:** 15–20 strong challenger · 10–14 promising with a clear risk to watch · below 10 likely to be out-competed or absorbed as a feature.

Always publish the **biggest risk** next to the score. A score without the risk reads like promotion, not analysis.

---

## Field selector

No source formally maps frameworks to industries. This table is our own judgment based on each framework's assumptions and the examples above.

| Field | Go deep on | Watch out for |
|---|---|---|
| **B2B software / SaaS** | Feature matrix, Crossing the Chasm beachhead, switching costs, AI Incumbent Test, copilot vs autopilot | Being a feature an incumbent ships next quarter |
| **Developer tools / infrastructure** | Wardley mapping (turning a custom component into a commodity), scale economies | Cloud giants copying the layer |
| **Fintech** | Distribution race (banks own customers), Five Forces with regulation, network effects, Lightspeed's "value destruction" (Robinhood-style model undercut) | Dependence on card networks / bank partners; price cuts alone don't win |
| **Healthcare / biotech** | Five Forces (payers and regulators as powerful buyers), VRIO / cornered resource (IP, trial data), Christensen new-market (access for non-consumers) | Regulatory path and reimbursement matter more than features |
| **Consumer** | Jobs-to-be-Done, Aggregation Theory (does it own demand?), branding, social network effects | Low-end disruption claims (Thompson's critique) |
| **Hardware / deep tech** | Technology S-curve position, Hype Cycle timing check, scale and process power | Relying on incumbent distribution channels; hype-peak timing |

---

## One-page analysis template (copy for each startup)

```markdown
# [Startup] vs [Main incumbent] — [Field]

**One-line verdict:** [Disruptive / Sustaining challenger / Feature risk] · Score [__/20]

## The arena
- Competitor set: [direct incumbents] · [startups] · [substitutes] · [inertia]
- Five Forces headline: [which force is strongest, which the startup changes]

## How it's different
- Positioning: [axis 1] vs [axis 2] — startup sits in [quadrant]
- ERRC: Eliminates [ ] · Reduces [ ] · Raises [ ] · Creates [ ]
- Job: When [situation], customers want [progress]. 10x on: [dimension]

## Disruption test
- Christensen checklist: [_/4] → [verdict]; weakness type: [demand / supply-side]
- Distribution race: [who owns the customer; time for incumbent to copy]
- AI Incumbent Test: workflow [Y/N] · data [Y/N] · sector depth [Y/N] · outcomes [Y/N]

## Durability
- Strongest power now: [ ] · Path to power: [ ]
- VRIO on main advantage: [result]

## Biggest risk
[One or two sentences]

## Sources
[Links]
```

---

## Worked example: Netflix vs Blockbuster (from HBR 2015)

| Step | Finding |
|---|---|
| Christensen checklist | Started with a niche (DVD-by-mail customers) Blockbuster could rationally ignore; worse on instant availability, better on selection and no late fees; streaming later met mainstream needs → **4/4, disruptive** |
| Counter-positioning | Blockbuster's store network and late-fee revenue made copying the model self-harming |
| Contrast: Uber | Launched in a well-served taxi market and won mainstream riders first → **sustaining competitor**, not disruption, in Christensen's sense |

---

## Sources

- [Porter, "The Five Competitive Forces That Shape Strategy," HBR 2008](https://hbr.org/2008/01/the-five-competitive-forces-that-shape-strategy)
- [Blue Ocean Strategy: ERRC grid](https://www.blueoceanstrategy.com/tools/errc-grid/)
- [VRIO overview (ThinkInsights)](https://thinkinsights.net/strategy/vrio)
- [Helmer's 7 Powers explained (Edison Group)](https://www.edisongroup.com/thematic/edison-explains-seven-strategic-powers-understanding-sustainable-competitive-advantage/)
- [Thiel's monopoly traits (Shortform summary)](https://www.shortform.com/blog/what-is-a-monopoly/)
- [Christensen, Raynor & McDonald, "What Is Disruptive Innovation?" HBR 2015 (PDF)](https://lburlamaqui.com.br/wp-content/uploads/2023/04/04-Christensen.What-is-disruptive-innovation-HBR-2015.pdf)
- [Stratechery, "Critiquing Disruption Theory" (2014)](https://stratechery.com/2014/critiquing-disruption-theory/)
- [Tuck, "Deflating Disruption Theory"](https://tuck.dartmouth.edu/news/articles/deflating-disruption-theory)
- [Gans, *The Disruption Dilemma* (publisher description)](https://www.readings.com.au/product/9780262533621)
- [Christensen Institute: Jobs to Be Done](https://www.christenseninstitute.org/theory/jobs-to-be-done/)
- [Crossing the Chasm (Wikipedia)](https://en.wikipedia.org/wiki/Crossing_the_Chasm)
- [Gartner Hype Cycle (Wikipedia)](https://en.wikipedia.org/wiki/Gartner_hype_cycle)
- [Wardley mapping FAQ](https://www.wardleymaps.com/faqs/what-is-wardley-mapping)
- [Stratechery: Aggregation Theory](https://stratechery.com/aggregation-theory/)
- [NFX Network Effects Manual](https://www.nfx.com/post/network-effects-manual)
- [Sequoia business plan template (Alexander Jarvis summary)](https://www.alexanderjarvis.com/sequoia-capital-business-plan-template/)
- [Paul Graham's views on competitors (The Venture Crew)](https://theventurecrew.substack.com/p/paul-grahams-views-on-competitor)
- [a16z, "Distribution v. Innovation" (2015)](https://a16z.com/2015/11/05/distribution-v-innovation/)
- [Lightspeed, "Startups v. Incumbents"](https://lsvp.com/stories/startups-v-incumbents-the-battle-for-ais-application-layer/)
- [500 Global, "The incumbents are slow thesis has aged poorly" (May 2026)](https://500.co/content/the-incumbents-are-slow-thesis-has-aged-poorly)
- [Sequoia, "Services: The New Software" (Mar 2026)](https://sequoiacap.com/article/services-the-new-software)
