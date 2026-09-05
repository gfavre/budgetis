# Changelog

All notable changes to Budgetis are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.0] - 2026-09-05

### Changed

- **User management page redesign**: the separate "Edit a user" and
  "Deactivate a user" dropdown pickers are replaced by a single table
  listing every other user, with an Edit and (where applicable) a
  Deactivate button directly on each row - no more picking a name
  from a dropdown to act on it.

## [1.5.0] - 2026-09-05

### Added

- **Edit a user**: on the user management page, an admin can now fix
  an existing user's name, trigram, or municipal officer status
  (`users.change_user`) - not just at invite time. Same admin-only
  permission as deactivation, so Bourse members still can't touch it.

### Fixed

- The "Is Municipal" checkbox on the invite form was untranslated -
  `User.is_municipal` now has a proper, translatable label.

## [1.4.0] - 2026-09-04

### Added

- **Deactivate a user**: on the user management page, an admin can now
  deactivate any existing account (`users.change_user`) - deactivated
  users can no longer sign in, and this is reversible from the Django
  admin. Deliberately not available to Bourse members, whose
  co-optation permission (`auth.change_group`) only lets them add
  people to the Bourse, not deactivate anyone.

## [1.3.0] - 2026-09-04

### Added

- **User management page**: a new "Users" page (linked from the nav bar)
  lets an admin invite a future municipal officer or finance staff member
  by email - no Django-admin access required, and the created account can
  never be an admin itself. Any current member of the "Bourse" permission
  group can also nominate an existing user into that group themselves,
  without needing an admin - a self-service co-optation flow.

## [1.2.0] - 2026-09-04

### Added

- **In-place budget editing**: charges and revenues for the current budget
  year can now be edited directly from the budget-by-function explorer -
  click an amount, type the new value, press Enter or click away to save.
  Restricted to a new "Bourse" permission group (bundling this together
  with the existing Sankey-configuration permissions), so other municipal
  officers still see a read-only figure. Prior years' budgets and actuals
  stay locked.

### Changed

- Every dependency, including Django, refreshed to its latest version -
  Django stays on the 5.2 LTS line (long-term support) rather than
  jumping to the newer, short-support 6.x line, since this app isn't
  upgraded on a tight cadence.

### Fixed

- Uploading a file with an unsupported extension in the BDI import
  crashed with an unrelated error instead of showing the intended
  message.
- A duplicate email address showed Django's generic uniqueness error
  instead of the intended, friendlier message.

## [1.1.0] - 2026-09-04

### Added

- **Sankey configuration page**: an overview, per accounting scheme, of
  exactly how each Sankey category is built - its nature-range, function +
  nature, exact-code and label rules - reachable from a "Réglages" button on
  the Sankey page, pre-filtered to whichever scheme the selected year uses.
  Every rule and category is editable in place (no more redirect to Django
  admin), restricted to finance staff via a dedicated permission.
- **Sankey hover breakdowns**: hovering a node or link now shows which
  accounts or categories feed it, largest first, instead of just a total.
- A new rule type distinguishes accounts that share the same MCH2 nature but
  are actually paid to different bodies depending on which municipal
  function pays - needed for intercommunal association dues (AISGE, APEC,
  RAT...) that all share nature 3612.

### Changed

- Sankey branches reached directly from the household with no further
  breakdown (dotations, result) now stop at the same column as
  Canton/Intercommunalities/Commune, instead of being pushed all the way to
  the diagram's rightmost column.
- Sankey node labels for a category with nothing upstream or downstream of
  it (a pure revenue source, or a leaf with nothing feeding out of it) are
  now drawn beside the node instead of overlapping the flow's color.
- The main content area now uses more of the available width on larger
  screens.
- Sankey page controls (year, budget toggle, exports, settings) moved into a
  narrow left column, giving the chart itself more vertical room.

### Fixed

- Several buttons across the app used the secondary (yellow) accent color
  instead of the intended primary (green) one.
- A handful of MCH2 accounts were mapped to the wrong Sankey category
  (UAPE and a tax-collection fee account were both misclassified as
  unrelated categories) due to a crosswalk artifact from the MCH1 import.
- Missing or duplicated French translations across the new Sankey
  configuration screens.

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
