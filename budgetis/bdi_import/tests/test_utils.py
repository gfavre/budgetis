import pytest

from budgetis.bdi_import.utils import load_account_dataframe


class TestLoadAccountDataframe:
    def test_unsupported_extension_raises_a_readable_error(self, tmp_path):
        path = tmp_path / "export.txt"
        path.write_text("whatever")

        with pytest.raises(ValueError, match=r"\.txt"):
            load_account_dataframe(str(path))
