import json
from pathlib import Path
from typing import List
from src.models import BenefitItem


def collect_seed_benefits(seed_file: Path) -> List[BenefitItem]:
    if not seed_file.exists():
        return []
    with open(seed_file, "r", encoding="utf-8") as f:
        raw_list = json.load(f)
    return [BenefitItem(**item) for item in raw_list]
