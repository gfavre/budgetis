from http import HTTPStatus
from unittest.mock import call
from unittest.mock import patch

import pytest
from django.urls import reverse

from budgetis.bdi_import.models import AccountImportLog
from budgetis.bdi_import.tests.factories import AccountImportLogFactory
from budgetis.bdi_import.tests.factories import ColumnMappingFactory
from budgetis.users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db
TASK_PATH = "budgetis.bdi_import.admin.import_accounts_task.delay"


class TestAccountImportLogAdmin:
    @pytest.fixture(autouse=True)
    def setup_admin(self, client):
        client.force_login(UserFactory(is_staff=True, is_superuser=True))
        self.url = reverse("admin:bdi_import_accountimportlog_changelist")

    def test_pages_load(self, client):
        log = AccountImportLogFactory()
        assert client.get(self.url).status_code == HTTPStatus.OK
        assert (
            client.get(reverse("admin:bdi_import_accountimportlog_change", args=[log.pk])).status_code == HTTPStatus.OK
        )

    def test_retry_finished_imports(self, client, django_capture_on_commit_callbacks):
        logs = [AccountImportLogFactory(status=status) for status in AccountImportLog.Status]
        failed = next(log for log in logs if log.status == AccountImportLog.Status.FAILED)
        successful = next(log for log in logs if log.status == AccountImportLog.Status.SUCCESS)
        mapping = ColumnMappingFactory(log=failed)
        with patch(TASK_PATH) as delay, django_capture_on_commit_callbacks(execute=True):
            response = client.post(
                self.url, {"action": "relaunch_import", "_selected_action": [log.pk for log in logs]}
            )
            delay.assert_not_called()
        assert response.status_code == HTTPStatus.FOUND
        delay.assert_has_calls([call(failed.pk), call(successful.pk)], any_order=True)
        assert delay.call_count == len((failed, successful))
        failed.refresh_from_db()
        assert failed.status == AccountImportLog.Status.PENDING
        assert failed.column_mappings.get().pk == mapping.pk
        for log in logs:
            if log.pk in (failed.pk, successful.pk):
                assert AccountImportLog.objects.get(pk=log.pk).status == AccountImportLog.Status.PENDING
            else:
                assert AccountImportLog.objects.get(pk=log.pk).status == log.status
        with patch(TASK_PATH) as delay, django_capture_on_commit_callbacks(execute=True):
            client.post(self.url, {"action": "relaunch_import", "_selected_action": [failed.pk, successful.pk]})
        delay.assert_not_called()

    def test_queue_failure_allows_retry(self, client, django_capture_on_commit_callbacks):
        log = AccountImportLogFactory(status=AccountImportLog.Status.FAILED, message="Original error")
        with (
            patch(TASK_PATH, side_effect=ConnectionError),
            pytest.raises(ConnectionError),
            django_capture_on_commit_callbacks(execute=True),
        ):
            client.post(self.url, {"action": "relaunch_import", "_selected_action": [log.pk]})
        log.refresh_from_db()
        assert log.status == AccountImportLog.Status.FAILED
        assert log.message == "Original error"
