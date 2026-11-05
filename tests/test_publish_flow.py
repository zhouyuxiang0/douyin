import asyncio
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

from dy_cli.engines import publish_flow as f
from dy_cli.main import cli


@pytest.fixture
def spec(tmp_path, monkeypatch):
    monkeypatch.setattr(f.shutil, "which", lambda _: None)
    paths = []
    for name in ("film.mp4", "horizontal.jpg", "vertical.png"):
        p = tmp_path / name
        p.write_bytes(name.encode())
        paths.append(str(p))
    return f.make_spec(
        title="标题",
        content="第一段\n\n第二段",
        video=paths[0],
        tags=["心理学", "科普"],
        thumbnail_horizontal=paths[1],
        thumbnail_vertical=paths[2],
        expected_account="测试账号",
    )


def work(spec):
    return {
        "work_id": "7697069527124774171",
        "title": "标题",
        "description": "标题 第一段 第二段 #心理学 #科普",
        "tags": ["心理学", "科普"],
        "visibility": "公开",
        "account_name": "测试账号",
        "account_uid": "123",
        "status": "published",
        "horizontal_cover_present": True,
        "vertical_cover_present": True,
        "created_at": 200,
        "downloadable": True,
    }


def test_independent_cover_files_are_preserved(spec):
    assert spec["covers"]["horizontal"]["path"].endswith("horizontal.jpg")
    assert spec["covers"]["vertical"]["path"].endswith("vertical.png")
    assert spec["covers"]["horizontal"]["sha256"] != spec["covers"]["vertical"]["sha256"]


def test_changed_media_blocks_before_browser(spec):
    from pathlib import Path

    Path(spec["covers"]["horizontal"]["path"]).write_text("changed")
    with pytest.raises(f.PublishFlowError, match="发生变化"):
        f.check_files(spec)


def test_schedule_never_falls_back_to_immediate(spec):
    with pytest.raises(f.PublishFlowError) as e:
        f.make_spec(title="x", content="", video=spec["video"]["path"], tags=[], schedule="2030-01-01T10:00:00+08:00")
    assert e.value.code == "unsupported_schedule"


def test_zero_width_and_spaces_normalize_but_extra_punctuation_does_not(spec):
    w = work(spec)
    w["description"] = "标题\n第一段\u200b\n\n第二段\u00a0 #心理学  #科普"
    assert f.copy_matches(w, spec)
    w["description"] = w["description"].replace("第二段", "*第二段")
    assert not f.copy_matches(w, spec)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("title", "其他标题", "title_or_description"),
        ("tags", ["科普"], "topic_tokens"),
        ("account_name", "错误账号", "account"),
        ("visibility", "仅自己可见", "visibility"),
        ("horizontal_cover_present", False, "covers"),
    ],
)
def test_verification_rejects_mismatches(spec, field, value, reason):
    w = work(spec)
    w[field] = value
    assert reason in f.verify_match(w, spec)


def test_business_status_and_reviewing_distinguished():
    base = {"aweme_id": "7697069527124774171", "status": {"in_reviewing": True, "private_status": 0}}
    assert f.work_view(base, {"review": {"status": 2}})["status"] == "reviewing"
    base["status"]["in_reviewing"] = False
    assert f.work_view(base, {"review": {"status": 2}})["status"] == "published"
    assert f.work_view(base, {})["status"] == "unknown"
    assert f.work_view(base, {})["work_id"] == "7697069527124774171"


def test_http_200_with_business_error_is_not_success():
    response = SimpleNamespace(status=200, json=AsyncMock(return_value={"status_code": 8, "aweme_list": []}))
    with pytest.raises(f.PublishFlowError):
        asyncio.run(f.read_works(SimpleNamespace(get=AsyncMock(return_value=response))))


def test_no_work_is_unverified_not_success(spec, monkeypatch):
    monkeypatch.setattr(f, "read_works", AsyncMock(return_value=[]))
    r = {"spec": spec, "before_ids": [], "started_epoch": 100, "submit_attempted": True}
    result = asyncio.run(f.verify_receipt(r, None, timeout=0))
    assert result["status"] == "submitted_unverified"


def test_old_same_copy_is_not_misidentified(spec, monkeypatch):
    w = work(spec)
    monkeypatch.setattr(f, "read_works", AsyncMock(return_value=[w]))
    r = {"spec": spec, "before_ids": [w["work_id"]], "started_epoch": 100, "submit_attempted": True}
    assert asyncio.run(f.verify_receipt(r, None))["status"] == "submitted_unverified"


def test_new_matching_work_verified_and_uid_checked(spec, monkeypatch):
    w = work(spec)
    monkeypatch.setattr(f, "read_works", AsyncMock(return_value=[w]))
    r = {"spec": spec, "before_ids": [], "started_epoch": 100, "submit_attempted": True, "account_uid": "123"}
    assert asyncio.run(f.verify_receipt(r, None))["status"] == "published"
    r["account_uid"] = "999"
    assert asyncio.run(f.verify_receipt(r, None))["status"] == "verification_failed"


def test_attempt_marker_blocks_repeat_even_after_timeout(spec, tmp_path):
    receipt = tmp_path / "receipt.json"
    f.atomic_json(receipt, {"spec": spec, "submit_attempted": True, "status": "submitted_unverified"})
    flow = f.VideoPublisher(SimpleNamespace(), spec, receipt)
    with pytest.raises(f.PublishFlowError) as e:
        asyncio.run(flow.run())
    assert e.value.code == "already_submitted"


def test_receipt_lock_prevents_concurrent_submit(tmp_path):
    p = tmp_path / "r.json"
    with f.receipt_lock(p):
        with pytest.raises(f.PublishFlowError) as e:
            with f.receipt_lock(p):
                pass
        assert e.value.code == "run_in_progress"


def test_receipt_lock_blocks_another_process_and_releases(tmp_path):
    path = tmp_path / "发布凭据.json"
    code = """
import sys
from dy_cli.engines.publish_flow import receipt_lock, PublishFlowError
try:
    with receipt_lock(sys.argv[1]):
        pass
except PublishFlowError as error:
    assert error.code == 'run_in_progress'
    sys.exit(75)
"""
    command = [sys.executable, "-c", code, str(path)]
    with f.receipt_lock(path):
        assert subprocess.run(command, timeout=15).returncode == 75
    assert subprocess.run(command, timeout=15).returncode == 0
    with pytest.raises(ValueError):
        with f.receipt_lock(path):
            raise ValueError("abort")
    assert subprocess.run(command, timeout=15).returncode == 0


def test_receipt_lock_rejects_symlink_without_changing_target(tmp_path):
    receipt = tmp_path / "receipt.json"
    target = tmp_path / "keep.txt"
    target.write_bytes(b"keep")
    try:
        (tmp_path / "receipt.json.lock").symlink_to(target)
    except OSError:
        pytest.skip("Creating symlinks requires permission on this machine")
    with pytest.raises(f.PublishFlowError) as error:
        with f.receipt_lock(receipt):
            pass
    assert error.value.code == "unsafe_receipt"
    assert target.read_bytes() == b"keep"


def test_resume_rejects_setting_override(spec, tmp_path):
    p = tmp_path / "r.json"
    f.atomic_json(p, {"spec": spec})
    result = CliRunner().invoke(cli, ["publish", "--resume", str(p), "--visibility", "仅自己可见", "--json-output"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["code"] == "invalid_argument"


def test_dry_run_does_not_upload_or_require_login(spec, tmp_path, monkeypatch):
    monkeypatch.setattr(f.VideoPublisher, "run", AsyncMock(side_effect=AssertionError("must not start browser")))
    result = CliRunner().invoke(
        cli,
        [
            "publish",
            "-t",
            "标题",
            "-v",
            spec["video"]["path"],
            "--thumbnail-horizontal",
            spec["covers"]["horizontal"]["path"],
            "--thumbnail-vertical",
            spec["covers"]["vertical"]["path"],
            "--dry-run",
            "--json-output",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["data"]["dry_run"] is True


def test_verify_unsubmitted_cannot_enable_archive(spec, tmp_path):
    p = tmp_path / "r.json"
    f.atomic_json(p, {"spec": spec, "submit_attempted": False})
    with pytest.raises(f.PublishFlowError) as e:
        asyncio.run(f.verify_file(p, "unused"))
    assert e.value.code == "not_submitted"


def test_string_author_uid_wins_over_rounded_numeric_duplicate():
    from dy_cli.engines.publish_flow import work_view

    view = work_view(
        {
            "aweme_id": "9007199254740993001",
            "author_user_id": 9007199254740992,
            "author": {"uid": "9007199254740993", "nickname": "测试账号"},
        }
    )
    assert view["account_uid"] == "9007199254740993"
