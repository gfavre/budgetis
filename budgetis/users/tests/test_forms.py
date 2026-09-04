"""Module for all Form Tests."""

import pytest
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _

from budgetis.users.forms import BourseNominationForm
from budgetis.users.forms import UserAdminCreationForm
from budgetis.users.forms import UserInviteForm
from budgetis.users.models import BOURSE_GROUP_NAME
from budgetis.users.models import User
from budgetis.users.tests.factories import UserFactory


class TestUserAdminCreationForm:
    """
    Test class for all tests related to the UserAdminCreationForm
    """

    def test_username_validation_error_msg(self, user: User):
        """
        Tests UserAdminCreation Form's unique validator functions correctly by testing:
            1) A new user with an existing username cannot be added.
            2) Only 1 error is raised by the UserCreation Form
            3) The desired error message is raised
        """

        # The user already exists,
        # hence cannot be created.
        form = UserAdminCreationForm(
            {
                "email": user.email,
                "password1": user.password,
                "password2": user.password,
            },
        )

        assert not form.is_valid()
        assert len(form.errors) == 1
        assert "email" in form.errors
        assert form.errors["email"][0] == _("This email has already been taken.")


@pytest.mark.django_db
class TestUserInviteForm:
    def test_creates_an_account_with_an_unusable_password(self):
        form = UserInviteForm({"email": "future@example.com", "name": "Future Municipal", "trigram": "FUT"})

        assert form.is_valid(), form.errors
        user = form.save()

        assert not user.has_usable_password()
        assert not user.groups.filter(name=BOURSE_GROUP_NAME).exists()

    def test_can_add_the_new_account_to_the_bourse_group(self):
        form = UserInviteForm(
            {
                "email": "future@example.com",
                "name": "Future Municipal",
                "trigram": "FUT",
                "add_to_bourse": True,
            }
        )

        assert form.is_valid(), form.errors
        user = form.save()

        assert user.groups.filter(name=BOURSE_GROUP_NAME).exists()


@pytest.mark.django_db
class TestBourseNominationForm:
    def test_excludes_existing_bourse_members_from_the_choices(self):
        bourse = Group.objects.create(name=BOURSE_GROUP_NAME)
        member = UserFactory()
        member.groups.add(bourse)
        candidate = UserFactory()

        form = BourseNominationForm()

        choices = list(form.fields["user"].queryset)
        assert candidate in choices
        assert member not in choices

    def test_adds_the_selected_user_to_the_bourse_group(self):
        candidate = UserFactory()

        form = BourseNominationForm({"user": candidate.pk})

        assert form.is_valid(), form.errors
        form.save()

        assert candidate.groups.filter(name=BOURSE_GROUP_NAME).exists()
