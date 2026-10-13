# ruff: noqa: PLR2004
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from budgetis.accounting.models import Account
from budgetis.accounting.models import AccountComment
from budgetis.accounting.tests.factories import AccountFactory
from budgetis.common.models import ChartScheme


pytestmark = pytest.mark.django_db


def make_account(**kwargs):
    defaults = {
        "scheme": ChartScheme.MCH2,
        "year": 2027,
        "function": "01100",
        "nature": "3000",
        "sub_account": "",
        "charges": 0,
        "revenues": 0,
        "is_budget": True,
    }
    return AccountFactory(**(defaults | kwargs))


def run(**kwargs):
    call_command("normalize_mch2_extensions", stdout=StringIO(), **kwargs)


def test_scope_year_and_idempotence():
    blank = make_account()
    untouched = [
        make_account(sub_account="01", charges=100),
        make_account(sub_account="99"),
        make_account(year=2026),
        make_account(scheme=ChartScheme.MCH1, function="110"),
    ]
    run(year=2027)
    run(year=2027)
    blank.refresh_from_db()
    assert blank.sub_account == "00"
    for account in untouched:
        original = account.sub_account
        account.refresh_from_db()
        assert account.sub_account == original


@pytest.mark.parametrize("amount_field", ["charges", "revenues"])
@pytest.mark.parametrize("valued_extension", ["", "00"])
def test_keeps_nonzero_amount_and_moves_comments(amount_field, valued_extension):
    valued = make_account(sub_account=valued_extension, **{amount_field: -50})
    empty = make_account(sub_account="00" if valued_extension == "" else "")
    comment = AccountComment.objects.create(account=empty, content="À conserver")
    with patch("builtins.input", side_effect=AssertionError("Unexpected prompt")):
        run()
    valued.refresh_from_db()
    comment.refresh_from_db()
    assert valued.sub_account == "00"
    assert getattr(valued, amount_field) == -50
    assert not Account.objects.filter(pk=empty.pk).exists()
    assert comment.account_id == valued.pk


@pytest.mark.parametrize("amount", [0, 100])
@pytest.mark.parametrize("choice", ["1", "2"])
def test_ambiguous_duplicate_prompts(amount, choice):
    blank = make_account(charges=amount)
    zero = make_account(sub_account="00", revenues=amount)
    with patch("builtins.input", side_effect=["invalid", choice]) as prompt:
        run()
    assert prompt.call_count == 2
    keeper = blank if choice == "1" else zero
    discarded = zero if choice == "1" else blank
    keeper.refresh_from_db()
    assert keeper.sub_account == "00"
    assert not Account.objects.filter(pk=discarded.pk).exists()


def test_budget_and_actuals_are_separate():
    blank = make_account()
    actual = make_account(sub_account="00", is_budget=False, charges=100)
    run()
    blank.refresh_from_db()
    actual.refresh_from_db()
    assert blank.sub_account == "00"
    assert actual.charges == 100


def test_dry_run_rolls_back_deletion_and_comments():
    blank = make_account(charges=100)
    zero = make_account(sub_account="00")
    comment = AccountComment.objects.create(account=zero, content="Commentaire")
    run(dry_run=True)
    blank.refresh_from_db()
    comment.refresh_from_db()
    assert blank.sub_account == ""
    assert Account.objects.filter(pk=zero.pk).exists()
    assert comment.account_id == zero.pk


@pytest.mark.parametrize("response", ["q", EOFError(), KeyboardInterrupt()])
def test_abort_rolls_back_previous_changes(response):
    previous = make_account(function="01000")
    make_account()
    make_account(sub_account="00")
    with patch("builtins.input", side_effect=[response]), pytest.raises(CommandError):
        run()
    previous.refresh_from_db()
    assert previous.sub_account == ""
    assert Account.objects.count() == 3


def test_non_mch2_collision_rolls_back():
    blank = make_account()
    other = make_account(sub_account="00", scheme=ChartScheme.MCH1)
    with pytest.raises(CommandError, match="non MCH2"):
        run()
    blank.refresh_from_db()
    assert blank.sub_account == ""
    assert Account.objects.filter(pk=other.pk).exists()
