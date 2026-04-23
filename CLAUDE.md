# Budgetis – Instructions for Claude

You are an expert in Python, Django, and Swiss municipal public accounting (MCH2).

**Read `CONTRIBUTING.md` for all coding conventions** (Python style, Django patterns, project structure, testing rules, CSS/frontend). Those rules apply here too.

---

## Business context

Budgetis is a municipal finance management tool used by the **municipality of Genolier** (canton of Vaud, Switzerland) and by the **commune's finance service** (bourse communale). Users are either elected **municipal officers** (municipaux) or finance staff.

### Primary goals

1. **Annotate** budgets and annual accounts (comptes) with remarks explaining variances between budget and actuals — per account, per group, per responsible officer.
2. **Produce reports** summarising finances for municipal meetings and management reports.
3. **Generate a Sankey diagram** representing the communal household: revenue flows (taxes, levies, rentals…) → communal household → Canton + Intercommunalities + Commune.

---

## Domain: MCH2 Swiss municipal accounting

### Chart of accounts (MCH2)

Budgetis follows the **Modèle Comptable Harmonisé 2 (MCH2)**, the Swiss standard for municipal public accounting.

Account code structure: `function.nature[.subaccount]` — e.g. `720.351`, `460.352.1`

| Level | Example | Description |
|---|---|---|
| `MetaGroup` | `1`, `2`, `3` | Top-level groups (grand totals) |
| `SuperGroup` | `41`, `42`, `43` | Intermediate sub-groupings |
| `AccountGroup` | `720`, `460` | Rubric (maps to the function digit) |
| `Account` | `720.351` | Elementary account |

### Natures (second part of the code)

- **30–39**: charges (expenditure)
- **40–49**: revenues (receipts)
- **500–599**: funding requests (préavis municipaux / demandes de crédit)
- **600–699**: depreciation (amortissements)

Key natures:
- `301–309`: personnel (salaries, social charges)
- `310–319`: goods, services, merchandise
- `320–329`: financial charges (interest)
- `360–369`: aids and subsidies
- `400–409`: taxes (where `402`, `404`, `405` = random/irregular taxes)
- `422–425`, `427`: property revenues (rentals, interest)
- `430–439`: levies and fees
- `350–359`: intercommunality contributions / cantonal equalization

### Domain vocabulary

| French term | English meaning |
|---|---|
| **Comptes** | Annual accounts (actuals) — `is_budget=False` |
| **Budget** | Forecast budget — `is_budget=True` |
| **Bourse** | Commune's finance department |
| **Municipal** | Elected member of the municipality (`User.is_municipal=True`) |
| **Trigram** | 3-letter initials of a municipal officer (`User.trigram`) |
| **Préavis** | Funding request submitted to the communal council |
| **Amortissement** | Depreciation installment on an investment |
| **Péréquation** | Cantonal/intercommunal financial equalization transfer |
| **AISGE** | Intercommunal security association (police) |
| **APEC** | Intercommunal employment/unemployment association |
| **SDIS** | Fire and rescue service |
| **ORPC** | Regional civil protection organization |
| **ARAS** | Regional social action association |

### Intercommunalities (Sankey)

The Sankey models the communal household with three major expenditure blocks:
- **Canton**: equalization (`220.352`), social security (`720.351`), police (`600.351`)
- **Intercommunalities**: AISGE, APEC, regional transport, associations, others
- **Commune**: wages, goods & services, interest, aids

---

## App architecture

| App | Role |
|---|---|
| `budgetis.accounting` | Core models: `Account`, `AccountGroup`, `SuperGroup`, `MetaGroup`, `AccountComment`, `GroupResponsibility`. Explorer and history views. |
| `budgetis.bdi_import` | Excel import (pandas) for accounts and budgets, with column mapping and import log (`AccountImportLog`, `ColumnMapping`). |
| `budgetis.finance` | `AvailableYear` (available Budget/Actuals years). Sankey views. |
| `budgetis.exports` | Exportable report generation (Excel). |
| `budgetis.core` | `SiteConfiguration` (logo, commune name, gradient colors), global template tags. |
| `budgetis.common` | `TimeStampedModel` (abstract base providing `created_at`/`updated_at`). |
| `budgetis.users` | `User` (auth, `is_municipal`, `trigram`), `AuthorizedEmail`. |
| `budgetis.contrib` | Third-party site extensions. |

---

## Hard rules — never break these

- **No magic strings or magic values.** Any string or number used as a sentinel, status, key, or category must be a named constant — inner class, `TextChoices`, or module-level constant. The only exceptions are `0`, `1`, and `""` when their meaning is unambiguous from context.
- **Never encode UI concerns in models.** Colors, CSS classes, icons, display labels are presentation layer — they belong in template tags or templates, never in `TextChoices`, model fields, or model methods. A model property may return a semantic status string (e.g. `"expired"`) but never a CSS class or color name.

---

## Project-specific patterns

### Multi-year comparisons in views

Explorer views systematically compare:
- **Actuals**: N (actuals) vs N (budget) vs N-1 (actuals)
- **Budgets**: N (budget) vs N-1 (budget) vs N-2 (actuals)

These values are attached dynamically as ad-hoc attributes on `Account` instances inside the explorer mixins — no extra DB fields.

### Group responsibility

`GroupResponsibility` binds an `AccountGroup` to a `User` for a given year. Views can filter with `only_responsible=True` to show only accounts for which the logged-in user is responsible.

### BDI import

Import runs in two phases: (1) Excel upload + column mapping via `AccountImportLog` + `ColumnMapping`; (2) async processing via Celery calling `import_accounts_from_dataframe()`. The `dry_run` flag allows simulation without writing to the database.

### Sankey

The Sankey is produced by `budgetis.finance.builders.build_income_budget_canton_intercos_commune()`. It returns `nodes`, `links`, `link_colors`, `node_colors` for Plotly. Colors are module-level constants in `builders.py`.
