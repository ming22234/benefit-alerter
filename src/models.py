from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class BenefitItem:
    id: str
    title: str
    category: str
    organization: str
    summary: str
    apply_period_text: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_always_open: bool = False
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    region: str = "전국"
    url: str = ""
    expected_months: List[int] = field(default_factory=list)
    is_priority: bool = False
    d_day: Optional[int] = None


@dataclass
class ClassifiedBenefits:
    newly_opened: List[BenefitItem] = field(default_factory=list)
    closing_soon: List[BenefitItem] = field(default_factory=list)
    currently_open: List[BenefitItem] = field(default_factory=list)
    upcoming_monthly: List[BenefitItem] = field(default_factory=list)
