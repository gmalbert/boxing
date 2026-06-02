# Boxing Oracle — Next 5 Features to Implement

> **Based on:** Codebase gap analysis as of July 2025

---

## Feature 1: Weight Class-Specific Models

**Why:** Fighting styles, physical attributes, and historical dominance patterns differ dramatically across weight classes. A heavyweight fight model trained with flyweight data produces noisy predictions. Training separate XGBoost classifiers per weight class would be the single most impactful model improvement.

**How:**
1. Add `weight_class` column to the training dataset (if not already present — extract from fight records)
2. Group weight classes into 5 buckets: Heavyweight/Light Heavyweight, Middleweight/Super Middleweight, Welterweight/Super Welterweight, Lightweight/Super Lightweight, Featherweight and below
3. Train a separate XGBoost classifier per bucket in the model training script
4. At prediction time, route each fight to the correct weight class model
5. Compare AUC per class vs the unified model

**Complexity:** Medium

---

## Feature 2: Outcome Time-Decay Weighting

**Why:** A fighter's performance from 5+ years ago is much less predictive than their last 3 fights. Career arcs change — champions age, styles evolve, weight cuts get harder. Exponential time-decay on Elo updates would address the most common failure mode (correctly rating recently declining champions as "elite").

**How:**
1. In the Elo/rating update logic in `config.py` or the model training script, add a `decay_weight = exp(-λ × years_since_fight)` where `λ = 0.15` (halves weight after ~4.6 years)
2. Apply weight to each historical fight when computing feature rolling averages
3. Add a UI toggle in the sidebar to compare decayed vs non-decayed win probabilities
4. Validate improvement: check Brier score on hold-out fights for active fighters vs recently retired ones

**Complexity:** Low

---

## Feature 3: CLV Trend Analysis in Bet Tracker

**Why:** The Bet Tracker page already records Closed Line Value (CLV) per bet, but there is no visualization showing CLV trends over time or per fighter/market. CLV is the best leading indicator of long-term betting profitability — fighters or markets where you consistently beat the close deserve higher confidence weighting.

**How:**
1. Load `data_files/bet_tracker.csv` (or SQLite table) with the CLV column
2. Add a "CLV Trends" tab to `pages/bet_tracker.py` with:
   - Rolling 20-bet average CLV chart (Plotly line)
   - CLV breakdown by bet type (moneyline, method of victory, round betting)
   - Fighter-level CLV league table: which fighters have generated the most positive CLV
3. Add a CLV distribution histogram to quantify edge sustainability

**Complexity:** Low

---

## Feature 4: Judge/Referee Tendency Features

**Why:** Boxing decisions are highly judge-dependent. Some judges favor the aggressor; others reward counter-punching. If a fight goes to decision (which boxing prediction models often under-model), the judge panel composition can determine the winner independent of who "won" the fight.

**How:**
1. Create `data_files/judge_history.csv`: judge_name, fight_id, scorer_for_home_fighter (score split)
2. Compute per-judge metrics: aggressor-favoring %, home fighter bias % (for fights held in a fighter's home country)
3. For each upcoming fight, look up the assigned judges (available from boxing commission announcements)
4. Add `avg_judge_aggressor_pct` as a model feature specifically for the "Decision" probability model

**Complexity:** High

---

## Feature 5: Injury / Withdrawal Risk Feed

**Why:** Late fight cancellations and injury substitutions are more common in boxing than any other combat sport. A fighter pulling out 2 weeks before the event often creates a mismatch replacement (worse opponent) that the market doesn't immediately price. Flagging risk would help users avoid bets with high cancellation probability.

**How:**
1. Add `scripts/fetch_boxing_news.py` using BeautifulSoup to scrape BoxingScene.com's recent articles or ESPN Boxing injury news feed
2. Build a simple keyword matcher: "injured", "withdrew", "replacement", "pulled out", "surgery"
3. Display a `⚠ Injury Risk Reported` badge on affected fight cards in the upcoming events page
4. Store flagged fights in `data_files/injury_flags.json` for audit purposes — do not block predictions, only annotate

**Complexity:** Medium
