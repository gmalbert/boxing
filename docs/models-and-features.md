# Boxing Analytics: Models, Features & Edge Methodology

---

## Predictive Model Architecture

Boxing is fundamentally different from team sports — there are no lineup changes, no fatigue from a schedule, no home/away splits. What matters is the **matchup** between two individuals. This makes it both harder and more exploitable than NFL/NBA betting.

---

## Feature Engineering

### Fighter Physical & Background Features
| Feature | Type | Notes |
|---|---|---|
| Height differential | Continuous | Taller fighters have longer reach on average |
| Reach differential | Continuous | **Very important** — longer reach = distance control |
| Age | Continuous | Peak boxing age ~26-32; over 35 is decline flag |
| Age differential | Continuous | Younger fighter advantage varies by context |
| Weight cut severity | Categorical | Fighters moving up/down divisions |
| Stance matchup | Categorical | Orthodox vs. Southpaw creates unique defensive angles |
| Nationality/Gym | Categorical | Some gyms known for specific styles |

### Record & Resume Features
| Feature | Type | Notes |
|---|---|---|
| Win % | Continuous | Weight recent fights more heavily |
| KO % | Continuous | Power puncher signal |
| KO % of opponents | Continuous | Chin durability signal |
| Fights at this weight class | Integer | Experience at current weight |
| Days since last fight | Integer | Ring rust vs. rhythm |
| Opposition quality (avg ranking) | Continuous | Are their wins against real competition? |
| Record against top-25 opponents | Continuous | Separates contenders from padded records |
| Early stoppage % | Continuous | Do they tend to finish or go to decision? |
| Decision win % | Continuous | Can they win on the cards? |

### Recent Form Features (Last 5 fights)
| Feature | Notes |
|---|---|
| Rolling win rate (last 3/5 fights) | Exponentially weight recent performance |
| Recent KO% | Is their power trending? |
| Recent rounds fought average | Are they getting tired? Going deep into fights? |
| Last fight result | Win/loss binary |
| Last fight method | How did they look? |
| Performance trajectory | Improving/declining based on punch stats |

### In-Fight Stats (CompuBox / punch data — where available)
| Feature | Notes |
|---|---|
| Punches landed per round | Output and accuracy |
| Jab accuracy | Establishes range, sets up power shots |
| Power punch accuracy | Primary damage metric |
| Punch output (thrown per round) | Volume vs. accuracy tradeoff |
| Defense (punches absorbed per round) | Getting hit = bad |
| Knockdown rate | Both scored and suffered |

### Odds-Based Features (for model validation, not inputs)
| Feature | Notes |
|---|---|
| Opening line (DraftKings) | Market's initial assessment |
| Pinnacle opening line | Sharp assessment |
| Line movement direction | Which way did money flow? |
| Consensus probability | Weighted average across all books |
| Public betting % vs. sharp betting % | Where is the square money vs. sharp money? |

---

## Models

### Model 1: Baseline — Logistic Regression
**Purpose:** Interpretable baseline. Fast to train, easy to explain.

**Inputs:** Reach differential, age differential, win%, KO%, opposition quality, stance matchup

**Output:** Win probability for Fighter A

**Why it's useful:** If logistic regression already beats the DK closing line 55%+ of the time, you have an edge before deploying complex models. Complexity isn't always better in boxing.

**Target metric:** Accuracy vs. closing line (CLV), not just win/loss accuracy

---

### Model 2: XGBoost Ensemble
**Purpose:** Primary prediction model. Handles non-linear relationships and feature interactions.

**Inputs:** All features above, including rolling averages

**Output:** Win probability + confidence score

**Key hyperparameters to tune:**
- Max depth (prevent overfitting on small boxing datasets)
- n_estimators
- Learning rate
- Subsample ratio

**Warning:** Boxing datasets are small. A typical model might have 2,000-5,000 fights for major bouts. Overfitting is a real risk. Use cross-validation aggressively.

---

### Model 3: Elo Rating System
**Purpose:** Dynamic fighter strength rating that updates after every fight.

**How it works:**
- Start each fighter at 1500 Elo
- Win against a higher-rated opponent → bigger Elo gain
- K-factor should be higher for early fights (more uncertainty), lower for established fighters

**Why it's valuable:** Elo captures *trajectory* better than raw win%. A fighter going 5-0 against weak opposition has different Elo growth than one going 3-2 against top contenders.

**Boxing-specific modifications:**
- Weight KO wins more than decision wins (+bonus Elo for finishing)
- Weight recent fights more (recency decay on past fights)
- Separate Elo by weight class

---

### Model 4: Method of Victory Predictor
**Purpose:** Predicting KO/TKO vs. Decision (useful for DK props).

**DraftKings offers:**
- Over/Under total rounds
- Method of victory (KO/TKO, decision, disqualification)
- Round-specific outcomes

**Features that predict KOs:**
- Both fighters' KO% and opponents' KO% suffered
- Combined power punch accuracy
- Weight class (heavyweights KO more)
- Fight history between similar opponents

---

### Model 5: Line Value Detector
**Purpose:** Not predicting winners, but detecting when DK's odds are mispriced vs. your model.

**Formula:**
```
Model_Prob = your model's win probability for Fighter A
DK_Implied_Prob = 1 / (DK_American_odds_to_decimal)
Edge = Model_Prob - DK_Implied_Prob
```

If `Edge > threshold` (e.g., 4-5%), flag as a bet.

**Sharp vs. Soft comparison:**
```
Pinnacle_Implied = 1 / Pinnacle_decimal_odds (no-vig adjusted)
DK_Implied = 1 / DK_decimal_odds (with vig)
DK_Edge_vs_Pinnacle = Pinnacle_Implied - DK_Implied
```
If DK is offering better odds than Pinnacle implies, that's a +EV signal.

---

## Closing Line Value (CLV) — The Most Important Metric

**CLV is the single best predictor of long-term betting success.**

- If your bets consistently *beat the closing line*, you're making +EV decisions
- If your bets consistently *lose to the closing line*, you're a square

**How to track:**
1. Log the odds at which you would bet (or your model signals a bet)
2. Log the closing odds for that fight
3. If you got -140 and the fight closed at -160, you beat the closing line (+CLV)
4. Track this across all signals

A model with consistent +CLV will be profitable long-term even through variance.

---

## Data Volume Realities for Boxing

This is the critical limitation to understand:

| League | Games/year | Data depth |
|---|---|---|
| NFL | ~270 games | Deep, decades of data |
| NBA | ~1,230 games | Very deep |
| **Boxing** | ~500 major bouts/year | **Shallow — many fighters have <20 pro fights** |

**Implications:**
- Statistical significance is harder to achieve
- Fighters have small sample sizes
- Models must generalize from fight patterns, not just fighter-specific history
- Stance matchups (Orthodox vs. Southpaw) have historically been hard to model due to small N

**Mitigation strategies:**
- Incorporate style/archetype clustering (pressure fighter, counter-puncher, boxer-puncher, slugger)
- Use Elo to encode cross-fighter information
- Weight CompuBox stats heavily when available — they're more predictive than records
- Start with higher-profile fights where more data exists (Top Rank, PBC, Matchroom events)

---

## Realistic Expectations

| Metric | Typical Sports Model | What to Expect (Boxing) |
|---|---|---|
| Win prediction accuracy | 60-65% on balanced data | 55-62% is realistic |
| +EV bet hit rate | 53-55%+ needed vs. vig | Target 54%+ on -110 equivalent |
| Annual fights to bet | Many (NFL 270+) | **Very few — maybe 20-50 high-confidence signals/year** |
| Edge magnitude | Typically 2-5% | 3-7% possible on props and underdogs |

**This is a low-volume, high-selectivity game.** Your model should say "no bet" most of the time. The edge comes from waiting for the right spots, not betting every fight card.

---

## Site Feature Recommendations

See [`site-features.md`](./site-features.md) for full UI/UX breakdown.

**Priority features for edge-finding:**
1. **Odds movement tracker** — See when DK moves a line and why
2. **Model vs. line dashboard** — Your probability vs. DK's implied probability
3. **Bet tracker with CLV** — Know if your process is working, not just results
4. **Alert system** — Notify you within minutes when a high-edge bet appears
5. **Fighter comparison tool** — Deep dive any matchup with all metrics side-by-side
