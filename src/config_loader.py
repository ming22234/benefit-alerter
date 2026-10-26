from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional
import yaml


def calculate_age(birth_year: int, reference_date: Optional[date] = None) -> int:
    ref = reference_date or date.today()
    return ref.year - birth_year


def load_config(config_path: Path) -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
