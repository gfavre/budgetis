# Contributing to Budgetis

## Stack

- Python 3.12, Django 5.2, uv
- PostgreSQL ≥ 15 (dev + test)
- Redis ≥ 7 (Celery broker + cache)
- HTMX + vanilla JS, crispy-forms (Bootstrap 5), Tom Select
- Celery + django-celery-beat for async tasks
- Plotly (Sankey diagram)

## Setup

```bash
uv sync --dev
python manage.py migrate --settings=config.settings.local
python manage.py runserver --settings=config.settings.local
```

With Docker (recommended for production):

```bash
cp .env.example .env
./scripts/setup.sh
make up
```

Run tests:

```bash
pytest
```

Run with coverage:

```bash
coverage run -m pytest
coverage html
```

Type checking:

```bash
mypy budgetis
```

## Code style

- PEP 8, **119-character line limit** (enforced by ruff and djLint)
- Double quotes for strings
- f-strings for formatting
- Import ordering via **ruff** (rule `I`, `force-single-line = true`, 2 blank lines after imports)
- Formatting via **ruff-format** (replaces Black)
- Never shadow Python builtins as parameter names (`filter`, `id`, `type`, `list`, `input`, `format`) — use descriptive alternatives

## Pre-commit hooks

All hooks run automatically on `git commit`. Install once with `pre-commit install`.

Active hooks:
- `trailing-whitespace`, `end-of-file-fixer`, `check-json/toml/xml/yaml`
- `debug-statements`, `check-builtin-literals`, `detect-private-key`
- `django-upgrade` (target Django 5.0)
- `ruff` (lint + autofix) then `ruff-format` (formatter)
- `djlint-reformat-django` + `djlint-django` (templates)

Migrations and `staticfiles/` are excluded from all hooks.

## Hard rules

- **No magic strings or magic values.** Sentinels, statuses, keys, and categories must be named constants — inner class, `TextChoices`, or module-level constant. Exceptions: `0`, `1`, `""` when unambiguous.
- **Never encode UI concerns in models.** Colors, CSS classes, icons, display labels belong in template tags or templates. A model property may return a semantic status string (e.g. `"expired"`) but never a CSS class or color name.

## Django conventions

- Prefer built-in features over third-party packages
- Use the ORM; avoid raw SQL unless truly necessary
- Use signals sparingly and document them
- Use `get_object_or_404` instead of manual exception handling
- Paginate all list views
- End all URL patterns with a trailing slash
- Use descriptive URL names for `reverse()`
- `ATOMIC_REQUESTS = True` — every view runs in a DB transaction; no manual `transaction.atomic()` needed at the view level

### Models

- Extend `TimeStampedModel` from `budgetis.common.models` — no exceptions
- `__str__` on every model
- `Meta` with `verbose_name`, `verbose_name_plural`, and `ordering`
- `blank=True` for optional form fields; `null=True` for optional DB fields
- Always set `related_name` on `ForeignKey`, `OneToOneField`, `ManyToManyField`
- All user-facing strings use `gettext_lazy` as `_(...)`
- Use `OneToOneField` to enforce unique relationships
- Use a through model when a FK carries extra data
- Financial/credit tracking: ledger pattern — signed `amount` + `balance_after` snapshot, never a mutable running total
- Append-only models (audit logs, ledger entries): disable add/change/delete in admin via `has_*_permission → False`
- Identity keys immutable once assigned: `readonly_fields` in admin, enforced at service layer

### Forms

- Use `ModelForm` for model instances
- Use crispy-forms: `FormHelper(form_tag=False)` + `Fieldset` layout objects

### Templates

- Templates live in `budgetis/<appname>/templates/` — never top-level
- `budgetis/core/templates/` for global templates only (base, login, admin overrides)
- Move logic to views or template tags, not templates
- CSRF protection on all forms
- djLint enforces formatting (profile `django`, indent 2, max line 119); run `djlint --reformat` before committing

### Admin

- `fieldsets` on models with more than ~6 fields
- `autocomplete_fields` for FK selectors (requires `search_fields` on the referenced admin)
- `show_change_link = True` on tabular inlines
- Collapse heavy inlines/fieldsets with `"classes": ("collapse",)`
- Append-only inlines: disable add/change/delete permissions

### API & webhooks

- Simple inbound webhooks: vanilla Django (`@csrf_exempt` + `@require_POST` + `JsonResponse`)
- Always persist raw payload before processing
- Return HTTP 200 even on processing errors; set error status on the delivery record
- Webhook security: token in URL + optional IP allowlist + optional API key header
- IP/CIDR validation: Python stdlib `ipaddress`

## Project structure

```
budgetis/
  <appname>/
    models.py          # or models/ package with __init__.py
    views.py           # or views/ package with __init__.py
    urls.py
    forms.py
    templates/<appname>/
    static/<appname>/
    templatetags/
    tests.py           # or tests/ package
config/
  settings/
    base.py
    local.py
    production.py
    test.py
```

- All apps under `budgetis/` with `AppConfig.name = "budgetis.<appname>"`
- Cross-app ForeignKeys use string references: `"accounting.Account"`
- Global static assets (CSS, JS) in `budgetis/static/`

## Testing

Every feature must include tests covering:

- **Model methods**: every `save()` override, every business logic method, every property with conditional logic. Use `factory.build()` for pure-logic tests, `factory.create()` when persistence matters.
- **Login required**: one test per protected view asserting anonymous GET redirects to `/login/`.
- **Tests grouped by view**: one `TestCase` class per view (e.g. `AccountCommentCreateViewTest`), containing login_required + 200 + behavior tests together.
- **Admin smoke tests**: changelist and change form return 200 for staff. Append-only admins: add/change/delete return 403.

Rules:
- `factory_boy` for all fixtures — no raw `Model.objects.create()` in tests
- Factories in `tests/factories.py` alongside test files; use `factory.Trait` for variants
- `UserFactory` lives in `budgetis/users/tests/factories.py` — never duplicated
- Test settings: `config/settings/test.py` (auto-loaded via pytest ini `--ds=config.settings.test`)
- `--reuse-db` is active by default; pass `--create-db` when schema changes

## i18n

All user-facing strings (model verbose names, help text, choice labels) must use `gettext_lazy`.

Language: `fr-ch` (French Switzerland). Time zone: `Europe/Zurich`.

## CSS & Frontend

- Global styles in `budgetis/static/css/` (`project.css`, `theme.css`, `print.css`)
- No component-level `<style>` blocks in templates
- HTMX: `hx-target="#detail-panel"` for detail swaps, `hx-target="#list-content"` for list refreshes
- Money formatting: use the `|format_money` template filter from `budgetis.accounting.templatetags.money`

## Dependencies

- Runtime: `[project] dependencies` in `pyproject.toml`
- Dev/test only: `[dependency-groups] dev` in `pyproject.toml`
- Install: `uv sync --dev`
- Add a package: `uv add <package>` (runtime) or `uv add --dev <package>` (dev-only)
