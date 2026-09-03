# MCH1 → MCH2 migration: architecture notes

> **Status:** the scheme infrastructure and the `AccountGroup` merge described
> below are implemented (see `accounting/models.py`, `common/models.py`,
> `finance/models.py`, migrations `accounting/0013-0015` and `finance/0002`,
> `accounting/groupers.py`, and the recursive `group_node.html` /
> `budget_group_node.html` partials). Verified against the real dev DB: totals
> per top-level group are byte-identical before/after the merge (8 metagroups,
> 37 supergroups, 53 leaf groups migrated, 6126 accounts and 265
> responsibilities untouched). Everything under "Deferred" below is still
> outstanding.

Genolier switches its municipal accounting from **MCH1** to **MCH2** starting with the
**2027 budget** (2026 stays MCH1 for both budget and actuals). MCH1 must stay
**permanently** browsable in Budgetis alongside MCH2, not just during a transition
window — these are two chart-of-accounts regimes coexisting forever, not a one-time
cutover.

This document is the working summary of the architecture discussion, kept so the
design survives even if an implementation session gets interrupted.

## Source data

- `Comptes 25 - base V21 pour upload.xlsx`, sheet **BASE**: the commune's own
  MCH1→MCH2 account mapping, columns `Fctio MCH2`/`Nat MCH2`/`Ext MCH2` giving the
  MCH2 code for each MCH1 account (`Compte MCH1`).
- `Plan_comptable_MCH2__Excel___04.26 (1).xlsx`, sheet **Classification
  fonctionnelle**: the official cantonal MCH2 functional classification reference
  (N1..N4 levels), used to validate the group hierarchy shape.

## Account code shapes

| | MCH1 | MCH2 |
|---|---|---|
| Account code | `function.nature[.sub_account]`, e.g. `720.351` | `function.nature.extension`, e.g. `01100.3000.00` |
| `function` | 3 digits | 5 digits = 4-digit canonical group (N4) + **1 commune-specific digit** |
| `nature` | 3 digits | 4 digits |
| sub-account / extension | commune-specific | commune-specific (2 digits) |

## MCH1 → MCH2 mapping is not 1:1

Analysis of the BASE sheet (633 distinct MCH1 accounts):

| Category | Count |
|---|---|
| Not yet mapped (`-` / `A trouver`) | 261 |
| Mapped total | 372 |
| ↳ Transposed 1:1 (e.g. `100.300 → 01100.3000.00`) | 158 |
| ↳ Split (1 MCH1 → several MCH2) | 106 |
| ↳ Merged (their MCH2 target also receives other MCH1 accounts) | 161 (into 65 distinct MCH2 targets) |
| ↳ of which both split and merged | 53 |

Of the 261 unmapped accounts, only 6 carry a non-zero 2025 amount (~15k CHF total,
mostly offsetting pairs) — low priority to chase down before the rest.

**Consequence:** existing `Account` rows can't just be relabeled; a crosswalk
between MCH1 and MCH2 code identities is needed (see "Deferred" below).

## Functional classification hierarchy

MCH1's grouping (confirmed in `accounting/groupers.py`) is **3 levels**:
`MetaGroup` (1 digit) → `SuperGroup` (2 digits) → `AccountGroup` (3 digits, the
deepest level, the one holding `GroupResponsibility`).

MCH2's official cantonal classification (verified against the canton reference
file: 10 N1 / 69 N2 / 159 N3 / 180 N4 nodes, each code cleanly prefixed by its
parent) is **4 levels**, responsibility sitting at N4. An MCH2 account's 5-digit
`function` = N4 (4 digits) + 1 commune digit; no grouping exists below N4 — the
commune digit and the 2-digit extension are purely local, matching how
`Account.function`/`nature`/`sub_account` already work today.

### Why one merged, self-referential model

`account_list.html`/`budget_list.html` originally rendered this hierarchy with a
template **hardcoded to exactly 3 nesting levels** (`groupers.build_grouped()`
built a fixed `metagroup → supergroups → groups` dict, one distinct HTML block per
level). For the *same view* to render both a 3-level (MCH1) and a 4-level (MCH2)
tree, the grouping structure has to support arbitrary depth — so `MetaGroup` /
`SuperGroup` / `AccountGroup` are merged into **one self-referential `AccountGroup`
model** (`parent` FK to self, `level`, `scheme`), and `groupers.py` +
`account_list.html`/`budget_list.html` become recursive. `Account.group` and
`GroupResponsibility.group` keep pointing at `AccountGroup` unchanged (no FK type
change, no data-loss risk on those relations) — they just now point at whichever
depth is the leaf for that scheme (level 3 for MCH1, level 4 for MCH2).

Full implementation plan (models, migrations, `groupers.py`, `admin.py`,
`forms.py`, templates, tests) lives in the plan history of the session that
implemented it; the model/field shapes described above are the source of truth
once implemented — check `accounting/models.py` directly for current state.

## Scheme infrastructure

- `ChartScheme` (`common/models.py`): `TextChoices` with `MCH1`/`MCH2`.
- `AvailableYear.scheme` (`finance/models.py`): which regime a given year uses.
- `Account.scheme` (`accounting/models.py`): stored explicitly on each `Account`
  row (not derived from `year` via an `AvailableYear` lookup), because
  `bdi_import/tasks.py` creates the `AvailableYear` row *after*
  `import_accounts_from_dataframe()` runs — a lookup-based derivation would fail
  mid-import.

## Deferred / explicitly out of scope for the current implementation pass

- **`AccountMapping` crosswalk model** — links MCH1 code identity
  (`function`/`nature`/`sub_account`) ↔ MCH2 code identity, at the *code* level
  (not tied to a specific year's `Account` row, since the same mapping holds for
  every year). Agreed to be **qualitative only** (no weighted/percentage
  redistribution of amounts) and **not needed for N-1 comparisons** — the user
  explicitly chose to accept a degraded/absent N-1 comparison for the one
  transition year (budget 2027 vs comptes 2026) rather than auto-translate
  amounts across schemes.
- **Importing the canton's reference classification data** (the 10/69/159/180
  N1-N4 rows) into `AccountGroup` for `scheme=MCH2` — needed before any real MCH2
  account can resolve its group via `Account.save()`, not done yet.
- **MCH1-hardcoded nature-range logic**, confirmed by exploration to assume
  3-digit MCH1 codes and silently misclassify or zero-out MCH2 rows once they
  exist:
  - `Account.is_funding_request` / `is_depreciation` (`accounting/models.py`) —
    compare `nature` (a `CharField`) against `FUNDING_REQUEST_GTE=500` /
    `DEPRECIATION_GTE=600` / `DEPRECIATION_LT=700`. Pre-existing latent fragility
    even for MCH1 (string vs int comparison — only works when `nature` is
    in-memory as an int before a DB round-trip, per `test_models.py`'s own
    comment) — not fixed here, just inherited.
  - `accounting/nature.py` (`NATURE_GROUPS`) and `groupers.py::_nature_group()` —
    2-digit nature-prefix grouping (30-49), used by the *nature*-axis explorer
    views (`account_by_nature_list.html` / `budget_by_nature_list.html`),
    untouched by the `AccountGroup` merge (separate axis). **Resolved for MCH2**:
    `NatureGroup` (`accounting/models.py`) is a second self-referential tree,
    kept separate from `AccountGroup` because nature and function codes share
    the same digits (e.g. both have a "30") and would collide in one table.
    Imported via `import_mch2_nature_classification` from the same reference
    file's **Compte de résultats - Charges/Revenus** sheets (421 nodes, levels
    1-4). `groupers._nature_group_labels()` sources level-2 labels from
    `NatureGroup` for MCH2 rows, falling back to the hand-written
    `NATURE_GROUPS` dict for MCH1 (no equivalent reference file for it). This
    also corrected several MCH1-era labels that didn't match the official MCH2
    naming (e.g. "34 Charges financières" was entirely missing; "36"/"42"/"44"
    were labeled with a different group's meaning).
  - `finance/builders.py` (`build_income_budget_canton_intercos_commune()`, the
    Sankey) and `finance/utils.py` — extensive hardcoded MCH1 nature ranges
    (`REVENUE_NATURE_RANGE=(400,499)`, `WAGES_NATURE_RANGE=(300,309)`, etc.) and
    specific account codes (`720.351`, `220.352`, `600.351`, the AISGE/APEC
    lists...). Will need MCH2-equivalent ranges/codes once the real MCH2 nature
    mapping is known — a separate follow-up task.
  - `finance/utils.py::_fmt_fn()` hardcodes 3-digit zero-padding
    (`f"{function:03d}.{nature:03d}"`), would mis-pad MCH2's 4-digit natures.
- **`bdi_import`** — the importer's dot-split code parsing
  (`importers.py::parse_account_code()`) is already shape-agnostic (no
  digit-count validation), so no change needed there yet; it just isn't wired up
  to *set* `scheme=MCH2` on anything since no MCH2 import exists.
- **`CLAUDE.md`** documents the current model as "MCH2" (section "Chart of
  accounts (MCH2)", example `720.351`) — that's actually MCH1-shaped (3+3
  digits) versus real MCH2 codes (5+4+2 digits, e.g. `01100.3000.00`). Needs
  correcting once the migration lands, to avoid misleading future sessions.
