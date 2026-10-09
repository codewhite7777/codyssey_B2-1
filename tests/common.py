import csv
import tempfile
import unittest
from pathlib import Path

from budget_app.csv_io import CSV_COLUMNS
from budget_app.service import BudgetService
from budget_app.storage import DATA_NAMES


class ServiceCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        self.service = BudgetService(self.data)
        for category in ("food", "salary", "transport", "rent"):
            self.service.add_category(category)

    def add(self, **changes):
        fields = dict(date="2026-10-06", type="expense", category="food", amount=15000,
                      memo="점심", tags=("meal",))
        fields.update(changes)
        return self.service.add(**fields)

    def snapshot(self):
        return {name: (self.data / name).read_bytes() for name in DATA_NAMES}

    def csv_file(self, rows, columns=CSV_COLUMNS, name="input.csv", encoding="utf-8"):
        path = self.root / name
        with path.open("w", encoding=encoding, newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def row(self, **changes):
        result = dict(date="2026-10-06", type="expense", category="food", amount="15000",
                      memo="점심, 커피", tags="meal,lunch")
        result.update(changes)
        return result
