# Changelog

All notable changes to Budgetis are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-09-01

First production release, for the municipality of Genolier.

### Added

- **Budget & actuals explorer**: browse budgets and annual accounts (comptes) by
  functional group, with multi-year comparison (actuals vs budget vs prior year),
  percentage variance, and a filter to show only the accounts a user is
  responsible for.
- **Account history**: a per-account chart (budget vs actuals over time),
  accessible from any account row.
- **Comments**: per-account annotations explaining variances, attached to
  charges or revenues independently.
- **Group responsibility**: assign a municipal officer (by trigram) to an
  account group for a given year; ancestor group levels (SuperGroup, MetaGroup)
  display a responsible automatically when every function underneath agrees,
  purely for the report - never stored at that level.
- **Reports by nature**: budgets and actuals grouped by nature code (charges
  30-39, revenues 40-49) instead of functional group, with a printable layout.
- **Sankey diagram**: visualizes the communal household - revenue flows into
  the commune, and expenditure flows out to the Canton, intercommunalities, and
  the commune's own operations.
- **BDI Excel import**: upload a finance-software export, map its columns, and
  import budget or actuals data asynchronously (Celery), with a dry-run mode
  and an import log.
- **MCH2 migration support**: the accounting model now supports both MCH1 and
  MCH2 numbering side by side.
  - The official MCH2 functional classification (N1-N4) is imported from the
    canton's reference file.
  - Genolier's own MCH1-to-MCH2 crosswalk is imported from their conversion
    file, correctly handling one-to-one, merged, and split account mappings.
  - A zero-value MCH2 account skeleton can be bootstrapped for a new year ahead
    of any real import, without ever overwriting real figures once they land.
  - The account history chart bridges the scheme switch automatically: merged
    accounts sum their MCH1 predecessors, split accounts show no fabricated
    history (with the ambiguous origins listed instead), and a marker on the
    chart shows exactly when the switch happened.
  - Explorer comparison columns (prior year, two years prior) are hidden
    entirely - not shown blank or zero - whenever the compared year uses a
    different accounting scheme, since the two aren't meaningfully comparable.
- **Admin tooling**: bulk actions to hide/show accounts in the report, bulk
  reassignment of group responsibility, site branding configuration (logo,
  commune name, colors), and the account/group/comment management screens.
- **Authentication**: email/password login with invite-only signup restricted
  to pre-authorized email addresses (django-allauth).

### Fixed

- The "only my accounts" filter no longer silently shows every account when a
  user has no group responsibility for the year - it now correctly shows none.
- The actuals-explorer fallback to budget data (shown when a year's actuals
  aren't imported yet) no longer issues one extra database query per account
  for its comments.
- Account group auto-assignment no longer fails when a group code happens to
  collide with one at a different level of the hierarchy.
