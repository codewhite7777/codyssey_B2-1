"""데이터 모양(모델). 모든 계층이 같은 Transaction을 주고받는다."""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Transaction:
    id: str              # "TX-000001" 형식, 유일
    type: str            # "income" 또는 "expense"
    date: str            # "YYYY-MM-DD"
    amount: int          # 양수
    category: str        # 등록된 카테고리
    memo: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """파일에 저장할 딕셔너리로 바꾼다."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transaction":
        """파일에서 읽은 딕셔너리로 Transaction을 만든다."""
        return cls(**data)
