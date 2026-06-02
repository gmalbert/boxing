# KnockOutIQ — 6-Month Feature Roadmap

## Month 1: Fight Card Experience

- **Fight-night countdown** — Hero section shows days/hours to the next scheduled DraftKings-listed event.
- **Fighter comparison card** — Side-by-side card for any two fighters: record, Elo, KO%, reach, age.
- **Weight class selector** — Filter the upcoming fights list by weight class (Heavyweight, Welterweight, etc.).
- **Event page deep link** — Each fight card links to its event detail page showing full undercard.

## Month 2: Predictions & Picks

- **Method of victory probabilities** — Show KO/TKO%, Decision% for each predicted fight.
- **Prop bet surface** — Surface DraftKings fight props (rounds, method) with model comparison.
- **Pick confidence badge** — Traffic-light system: green (strong edge), yellow (marginal), red (pass).
- **Best bet export** — One-click copy of today's top pick formatted for social sharing.

## Month 3: Fighter Profiles

- **Full fighter profile page** — Fight history, punch stats, win streak, style matchup history.
- **Elo history chart** — Plotly line chart of Elo over career fights.
- **Fighter image** — Pull from `image_url` field populated by `scripts/enrich_fighters_wiki.py`.
- **Similar fighters widget** — "Fans of this fighter also track" based on shared weight class / style.

## Month 4: Analytics

- **Model accuracy dashboard** — Rolling 30-fight accuracy chart for win prediction and method of victory.
- **CLV tracker** — Show closing line value vs. model opening prediction for settled fights.
- **Bet log history** — Table of all tracked bets from `bet_log` with P&L, CLV, and result.
- **Value finder page** — Filter upcoming fights by minimum edge threshold.

## Month 5: Data Enrichment

- **Live odds tracker** — Poll DraftKings every 15 minutes for opening fight; show line movement.
- **BoxRec integration** — Nightly sync of career records and punch stats for active fighters.
- **Injury/travel notes** — Manual flag for fighters travelling to a hostile venue or coming off injury.

## Month 6: Community & Notifications

- **Fight-week email** — Automated email every Thursday with weekend fight card and model picks.
- **Discord bot** — Post fight card and top model pick to a Discord server.
- **Public leaderboard** — Simulated bankroll tracker showing cumulative ROI for model picks.
