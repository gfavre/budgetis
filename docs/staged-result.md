# Compte de résultats: présentation échelonnée

Implemented in `budgetis/accounting/staged_result.py`, surfaced as the "Staged
result" page under both the Budget and Actuals nav menus
(`accounting:budget-staged-result` / `accounting:account-staged-result`).

## Source

The structure and nature-code boundaries are taken verbatim from the official
handbook, not invented or approximated:

> Conférence suisse des services et responsables financiers (SRS-CSPCP),
> **"Manuel MCH2"**, 2e édition, mars 2022, Recommandation 04
> "Compte de résultats", §12 and **Tableau 04-1**
> "Compte de résultats : Présentation échelonnée".
> https://www.srs-cspcp.ch/sites/default/files/pages/2022-01-01-manuel-mch2-2e-edition_3.pdf

That PDF (468 pages) is not encrypted despite some tooling reporting it as
unreadable/compressed - `pdftotext -layout` or a PDF-capable file reader
extracts it fine. It's organized as numbered "Recommandations"; Tableau 04-1
is on page 3 of Recommandation 04.

## Tableau 04-1 (reproduced)

| Charges d'exploitation | Revenus d'exploitation |
|---|---|
| 30 Charges de personnel | 40 Revenus fiscaux |
| 31 Charges de biens et services et autres charges d'exploitation | 41 Patentes et concessions |
| 33 Amortissements du patrimoine administratif | 42 Taxes |
| 35 Attributions aux fonds et financements spéciaux | 43 Revenus divers |
| 36 Charges de transferts | 45 Prélèvements sur les fonds et financements spéciaux |
| 37 Subventions redistribuées | 46 Revenus de transferts |
| | 47 Subventions à redistribuer |
| **→ Résultat d'exploitation [REX]** | |
| 34 Charges financières | 44 Revenus financiers |
| **→ Résultat financier [RFI]** | |
| **→ Résultat opérationnel [ROP = REX + RFI]** | |
| 38 Charges extraordinaires | 48 Revenus extraordinaires |
| **→ Résultat extraordinaire [REO]** | |
| **→ Résultat total du compte de résultats [= ROP + REO]** | |

This is exactly the structure `staged_result.py::build_staged_result()`
implements, line by line: a detail row per nature group (labelled straight
off the table, via `GROUP_LABELS`), a subtotal row for each side of the
operating section, then a result row after each of the three sections
(exploitation → +financier = opérationnel → +extraordinaire = total), each
result row's cumulative total carrying forward into the next. The group
split (`EXPLOITATION_CHARGE_GROUPS`, `EXPLOITATION_REVENUE_GROUPS`,
`FINANCIAL_CHARGE_GROUP`/`FINANCIAL_REVENUE_GROUP`,
`EXTRAORDINARY_CHARGE_GROUP`/`EXTRAORDINARY_REVENUE_GROUP`) matches the
table exactly, including 39/49 "imputations internes" being absent from
both - they net out between charges and revenues and the table has no line
for them.

Each `StagedLine` carries a stable, untranslated `key` (e.g. `"detail-30"`,
`"operating-result"`) separate from its user-facing, translated `label` -
code seeking a specific row (tests included) should match on `key`, never on
`label`, since the latter changes with the active language.

## Resolved question: "impôts aléatoires" (nature 402/404/405)

Genolier's irregular tax revenue (impôt foncier, droit de mutation,
successions - nature 40**2**/40**4**/40**5**) swings significantly
year-to-year (e.g. ~1.3M in 2022-2024 down to ~440k in 2025, driven mostly by
the real-estate transfer tax tracking the actual property market). This looks
suspicious in a year-over-year comparison and raised the question of whether
it should be isolated as its own line, separate from ordinary exploitation.

**Per Tableau 04-1, no** - nature 40 "Revenus fiscaux" (which nature 402/404/405
belong to) is exploitation revenue by the official definition, full stop.
There is no separate line for it anywhere in the MCH2 model. §11 of the same
recommandation explicitly anticipates this: *"Le solde du compte de résultats
est un chiffre-clé... C'est pourquoi le résultat total prévaut. Les soldes
intermédiaires offerts par la présentation échelonnée du résultat sont utiles
pour l'analyse de détail."* - the staged subtotals are secondary detail, not a
mechanism to smooth out real tax volatility. A year with unusually low
droit-de-mutation revenue is expected to show a worse "Résultat
d'exploitation" that year, by design.

**No code change needed** - `staged_result.py`'s 3-tier split was already
correct before this was investigated; this section exists so the next person
asking the same question doesn't have to re-derive it.

## Cross-scheme (MCH1/MCH2) comparison

Unlike the detailed by-function/by-nature explorers
(`accounting/scheme_transition.py::comparison_flags()`), which hide a
comparison year entirely across the MCH1→MCH2 switch because those explorers
join years by `(function, nature, sub_account)` - a key that never lines up
across schemes since the codes themselves are shaped differently - the staged
result only aggregates by **two-digit nature group** (30, 34, 38, 40, 44,
48...), which is identical in both MCH1 and MCH2 (see `mch2-migration.md`'s
"Account code shapes" table: only the digit *count* changed, e.g. MCH1 `351`
vs MCH2 `3010`, not the leading two digits' meaning).

Because of this, `staged_comparison_flags()` uses its own, more permissive
comparability rule than `comparison_flags()`: a comparison column is shown
whenever that year simply has data, regardless of scheme. `build_staged_result()`
queries `Account` directly per column instead of going through
`BudgetLoader`/`ActualsLoader` (which do the function/nature/sub_account
join) - this was a real bug in an earlier version: reusing those loaders
silently produced zero for every cross-scheme comparison column instead of
the real historical totals, since the join key never matched. Regression test:
`test_comparison_columns_carry_the_real_prior_year_totals` in
`accounting/tests/test_views.py`.
