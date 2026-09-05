"""Module for all Form Tests."""

import pytest
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _

from budgetis.users.forms import BourseNominationForm
from budgetis.users.forms import DeactivateUserForm
from budgetis.users.forms import UserAdminCreationForm
from budgetis.users.forms import UserEditForm
from budgetis.users.forms import UserEditSelectionForm
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


@pytest.mark.django_db
class TestDeactivateUserForm:
    def test_excludes_the_requesting_user_from_the_choices(self):
        admin = UserFactory()
        other = UserFactory()

        form = DeactivateUserForm(requesting_user=admin)

        choices = list(form.fields["user"].queryset)
        assert other in choices
        assert admin not in choices

    def test_excludes_already_inactive_users_from_the_choices(self):
        admin = UserFactory()
        inactive = UserFactory(is_active=False)

        form = DeactivateUserForm(requesting_user=admin)

        assert inactive not in list(form.fields["user"].queryset)

    def test_deactivates_the_selected_user(self):
        admin = UserFactory()
        target = UserFactory()

        form = DeactivateUserForm({"user": target.pk}, requesting_user=admin)

        assert form.is_valid(), form.errors
        form.save()

        target.refresh_from_db()
        assert not target.is_active

    def test_cannot_select_the_requesting_user_even_via_a_crafted_post(self):
        admin = UserFactory()

        form = DeactivateUserForm({"user": admin.pk}, requesting_user=admin)

        assert not form.is_valid()


@pytest.mark.django_db
class TestUserEditSelectionForm:
    def test_excludes_the_requesting_user_from_the_choices(self):
        admin = UserFactory()
        other = UserFactory()

        form = UserEditSelectionForm(requesting_user=admin)

        choices = list(form.fields["user"].queryset)
        assert other in choices
        assert admin not in choices

    def test_includes_inactive_users_in_the_choices(self):
        """Unlike deactivation/nomination, fixing a typo shouldn't require reactivating first."""
        admin = UserFactory()
        inactive = UserFactory(is_active=False)

        form = UserEditSelectionForm(requesting_user=admin)

        assert inactive in list(form.fields["user"].queryset)


@pytest.mark.django_db
class TestUserEditForm:
    def test_updates_name_trigram_and_municipal_status(self):
        target = UserFactory(name="Old Name", trigram="OLD", is_municipal=False)

        form = UserEditForm(
            {"name": "New Name", "trigram": "NEW", "is_municipal": True},
            instance=target,
        )

        assert form.is_valid(), form.errors
        form.save()

        target.refresh_from_db()
        assert target.name == "New Name"
        assert target.trigram == "NEW"
        assert target.is_municipal is True

    def test_does_not_expose_email_or_staff_fields(self):
        form = UserEditForm()

        assert set(form.fields) == {"name", "trigram", "is_municipal"}
