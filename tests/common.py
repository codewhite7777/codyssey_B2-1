import csv
import tempfile
import unittest
from pathlib import Path

from budget_app.csv_io import CSV_COLUMNS
from budget_app.service import BudgetService
from budget_app.storage import DATA_NAMES


class ServiceCase(unittest.TestCase):
    def setUp(self):
        """각 테스트마다 임시 폴더와 서비스를 만들고 사용할 네 카테고리를 등록한다."""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        self.service = BudgetService(self.data)
        for category in ("food", "salary", "transport", "rent"):
            self.service.add_category(category)

    def add(self, **changes):
        """기본 거래 필드에 테스트별 변경값을 덮어 서비스로 저장하고 거래를 반환한다."""
        fields = dict(date="2026-10-06", type="expense", category="food", amount=15000,
                      memo="점심", tags=("meal",))
        fields.update(changes)
        return self.service.add(**fields)

    def snapshot(self):
        """세 저장 파일을 바이트로 복사하여 실패 전후의 원본 보존 비교에 사용한다."""
        return {name: (self.data / name).read_bytes() for name in DATA_NAMES}

    def csv_file(self, rows, columns=CSV_COLUMNS, name="input.csv", encoding="utf-8"):
        """주어진 열·행·인코딩으로 임시 CSV를 작성하고 테스트에 사용할 경로를 반환한다."""
        path = self.root / name
        with path.open("w", encoding=encoding, newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def row(self, **changes):
        """정상 CSV 행 사전을 만들고 지정한 필드만 바꾸어 정상·오류 사례를 구성한다."""
        result = dict(date="2026-10-06", type="expense", category="food", amount="15000",
                      memo="점심, 커피", tags="meal,lunch")
        result.update(changes)
        return result
