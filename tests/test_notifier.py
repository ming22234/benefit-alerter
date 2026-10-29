from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch
import requests
from src.models import BenefitItem, ClassifiedBenefits
from src.notifier import (
    _post_telegram_with_retry,
    format_daily_briefing,
    split_message_chunks,
)


def test_format_daily_briefing_and_chunking():
    classified = ClassifiedBenefits(
        newly_opened=[
            BenefitItem(
                id="b1",
                title="2026 평생교육이용권 2차 신청",
                category="교육/바우처",
                organization="교육부",
                summary="연 35만원 평생교육 강좌 수강료 지원",
                apply_period_text="2026-10-26 ~ 2026-11-08",
                start_date="2026-10-26",
                end_date="2026-11-08",
                url="https://www.lllcard.kr",
                is_priority=True,
                d_day=13,
            )
        ]
    )
    config = {
        "profile": {
            "birth_year": 1995,
            "region_sido": "서울",
            "region_sigungu": "강남구",
        },
        "notification": {
            "max_other_items_in_message": 10,
        },
    }

    msg = format_daily_briefing(classified, config, today=date(2026, 10, 26))
    assert "평생교육이용권" in msg
    assert "https://www.lllcard.kr" in msg
    assert "서울 강남구" in msg

    chunks = split_message_chunks(msg, max_length=100)
    assert all(len(c) <= 100 for c in chunks)


def test_post_telegram_with_retry_recovers_from_connection_reset(tmp_path: Path):
    dummy_html = tmp_path / "test_blog.html"
    dummy_html.write_text("<html><body>Hello</body></html>", encoding="utf-8")

    ok_resp = MagicMock()
    ok_resp.raise_for_status.return_value = None

    with patch("src.notifier.requests.post") as mock_post, patch("src.notifier.time.sleep"):
        mock_post.side_effect = [
            requests.exceptions.ConnectionError("Connection reset by peer"),
            ok_resp,
        ]
        resp = _post_telegram_with_retry(
            "https://api.telegram.org/botTOKEN/sendDocument",
            data={"chat_id": "123", "caption": "test"},
            file_field="document",
            file_path=dummy_html,
            content_type="text/html",
            pacing_sec=0.0,
        )
        assert resp is ok_resp
        assert mock_post.call_count == 2
        # 두 번째 재시도에서도 파일 바이트가 비어있지 않고 정상 전달되었는지 검증
        second_call_files = mock_post.call_args_list[1].kwargs["files"]
        assert second_call_files["document"][1] == b"<html><body>Hello</body></html>"
