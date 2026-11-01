from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch
import requests
from src.daily_blog_generator import cleanup_old_blog_files
from src.models import BenefitItem, ClassifiedBenefits
from src.notifier import (
    _post_telegram_with_retry,
    format_daily_briefing,
    send_telegram_blog_package,
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
        second_call_files = mock_post.call_args_list[1].kwargs["files"]
        assert second_call_files["document"][1] == b"<html><body>Hello</body></html>"


def test_cleanup_old_blog_files_deletes_10_days_or_older(tmp_path: Path):
    blog_dir = tmp_path / "blog_posts"
    img_dir = blog_dir / "images"
    img_dir.mkdir(parents=True)

    # 10일 전(삭제 대상), 15일 전(삭제 대상), 9일 전(유지 대상), 오늘(유지 대상)
    old_html = blog_dir / "2026-10-22_old.html"
    older_img = img_dir / "2026-10-17_old_thumbnail.png"
    recent_html = blog_dir / "2026-10-23_recent.html"
    today_img = img_dir / "2026-11-01_today_thumbnail.png"

    for f in (old_html, older_img, recent_html, today_img):
        f.write_text("dummy", encoding="utf-8")

    removed = cleanup_old_blog_files(
        retention_days=10,
        today=date(2026, 11, 1),
        blog_dir=blog_dir,
    )
    assert set(removed) == {old_html, older_img}
    assert not old_html.exists()
    assert not older_img.exists()
    assert recent_html.exists()
    assert today_img.exists()


def test_send_telegram_blog_package_does_not_send_md(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    thumb = tmp_path / "thumb.png"
    info = tmp_path / "info.png"
    html_f = tmp_path / "post.html"
    md_f = tmp_path / "post.md"
    for f in (thumb, info, html_f, md_f):
        f.write_text("content", encoding="utf-8")

    pkg = {
        "blog_category": "돈·지원금 NEW",
        "recommended_title": "테스트 제목",
        "thumb_path": thumb,
        "info_path": info,
        "html_path": html_f,
        "md_path": md_f,
    }

    with patch("src.notifier._post_telegram_with_retry") as mock_retry:
        ok = send_telegram_blog_package(pkg)
        assert ok is True
        # 썸네일 1 + 인포그래픽 1 + HTML 1 = 총 3회만 호출되고 .md는 전송되지 않아야 함
        assert mock_retry.call_count == 3
        sent_paths = [call.kwargs["file_path"] for call in mock_retry.call_args_list]
        assert md_f not in sent_paths
        assert sent_paths == [thumb, info, html_f]
