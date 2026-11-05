"""Verified video publishing. Receipts contain no cookies or signed media URLs."""

from __future__ import annotations

import asyncio
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from dy_cli.utils import config
from dy_cli.utils.browser import launch_chrome

if os.name == "nt":
    import msvcrt
else:
    import fcntl

CREATOR = "https://creator.douyin.com"
UPLOAD = CREATOR + "/creator-micro/content/upload"
MANAGE = CREATOR + "/creator-micro/content/manage"
WORKS = CREATOR + "/janus/douyin/creator/pc/work_list"


class PublishFlowError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def normalize(text):
    return " ".join(str(text).replace("\u200b", "").replace("\ufeff", "").split())


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise PublishFlowError("unsafe_receipt", "凭据文件不能是软链接")
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    with open(tmp, "x", encoding="utf-8") as f:
        os.chmod(tmp, 0o600)
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


@contextmanager
def receipt_lock(path):
    lock = Path(str(path) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.is_symlink():
        raise PublishFlowError("unsafe_receipt", "凭据锁不能是软链接")
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        opened, named = os.fstat(fd), lock.lstat()
        if (
            not stat.S_ISREG(named.st_mode)
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
            or getattr(named, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ):
            raise PublishFlowError("unsafe_receipt", "凭据锁路径已变化或不是普通文件")
        try:
            if os.name == "nt":
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise PublishFlowError("run_in_progress", "此发布凭据正在被另一个进程使用") from None
            raise
        try:
            yield
        finally:
            if os.name == "nt":
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    finally:
        os.close(fd)


def file_spec(path):
    p = Path(path).expanduser().resolve(strict=True)
    if not p.is_file():
        raise PublishFlowError("invalid_media", f"不是普通文件: {p}")
    return {"path": str(p), "sha256": sha256(p), "bytes": p.stat().st_size}


def make_spec(
    *,
    title,
    content,
    video,
    tags,
    visibility="公开",
    thumbnail=None,
    thumbnail_horizontal=None,
    thumbnail_vertical=None,
    account="default",
    expected_account=None,
    save_permission="keep",
    schedule=None,
):
    if not title or len(title) > 30:
        raise PublishFlowError("invalid_title", "视频标题需为1至30个字符")
    if len(tags) != len(set(tags)) or any(not t or "#" in t or any(c.isspace() for c in t) for t in tags):
        raise PublishFlowError("invalid_tags", "话题不得重复、包含空格或#；每个 --tags 提供准确名称")
    if len(content) + sum(len(t) + 2 for t in tags) > 1000:
        raise PublishFlowError("invalid_content", "简介和话题合计超过1000字符")
    if visibility not in ("公开", "好友可见", "仅自己可见"):
        raise PublishFlowError("invalid_visibility", "不支持的可见范围")
    if schedule:
        # Legacy implementation silently fell back to immediate publication. Never do that.
        raise PublishFlowError("unsupported_schedule", "新版视频流程暂未验证定时控件；停止，不会降级为立即发布")
    horizontal = thumbnail_horizontal or thumbnail
    vertical = thumbnail_vertical or thumbnail
    if not horizontal or not vertical:
        raise PublishFlowError("missing_covers", "请提供独立横竖封面图片，或用 --thumbnail 为两种封面提供同一图片")
    spec = {
        "title": title,
        "content": content,
        "rendered_content": normalize(content),
        "tags": list(tags),
        "visibility": visibility,
        "video": file_spec(video),
        "covers": {"horizontal": file_spec(horizontal), "vertical": file_spec(vertical)},
        "account": account,
        "expected_account": expected_account,
        "save_permission": save_permission,
        "schedule": None,
    }
    if shutil.which("ffprobe"):
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", spec["video"]["path"]],
                capture_output=True,
                text=True,
                check=True,
                timeout=20,
            )
            spec["video"]["duration_ms"] = round(float(json.loads(result.stdout)["format"]["duration"]) * 1000)
        except (subprocess.SubprocessError, ValueError, KeyError) as exc:
            raise PublishFlowError("invalid_video", "ffprobe 无法确认视频时长，停止上传") from exc
    spec["fingerprint"] = hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return spec


def check_files(spec):
    for f in [spec["video"], *spec["covers"].values()]:
        if not Path(f["path"]).is_file() or sha256(f["path"]) != f["sha256"]:
            raise PublishFlowError("media_changed", f"已准备的文件发生变化: {f['path']}")


def work_view(aweme, item=None):
    """Whitelist public/business fields. Preserve IDs as strings, never JS floats."""
    item = item or {}
    status = aweme.get("status") or {}
    review = (item.get("review") or {}).get("status")
    state = "unknown"
    if status.get("is_delete") or status.get("is_prohibited"):
        state = "unavailable"
    elif status.get("in_reviewing") is True:
        state = "reviewing"
    elif review == 2 and status.get("in_reviewing") is False:
        state = "published"
    visibility = {0: "公开", 1: "仅自己可见", 2: "好友可见"}.get(status.get("private_status"), "unknown")
    ident = str(aweme.get("aweme_id") or item.get("id") or "")
    tags = [x.get("cha_name") for x in aweme.get("cha_list", []) if x.get("cha_name")]
    extra_tags = [x.get("hashtag_name") for x in aweme.get("text_extra", []) if x.get("hashtag_name")]
    tags = list(dict.fromkeys(tags + extra_tags))
    return {
        "work_id": ident,
        "url": f"https://www.douyin.com/video/{ident}",
        "title": aweme.get("item_title", ""),
        "description": aweme.get("desc", ""),
        "account_name": (aweme.get("author") or {}).get("nickname", ""),
        "account_uid": str((aweme.get("author") or {}).get("uid") or aweme.get("author_user_id") or ""),
        "created_at": aweme.get("create_time"),
        "duration_ms": aweme.get("duration"),
        "tags": tags,
        "status": state,
        "review_code": review,
        "visibility": visibility,
        "horizontal_cover_present": bool(aweme.get("horizontal_cover")),
        "vertical_cover_present": bool(item.get("cover") or aweme.get("Cover")),
        "downloadable": item.get("downloadable"),
    }


async def read_works(request, count=50):
    response = await request.get(WORKS, params={"count": count, "cursor": 0}, timeout=30000)
    if response.status != 200:
        raise PublishFlowError("verification_unavailable", f"作品列表HTTP状态: {response.status}")
    data = await response.json()
    if data.get("status_code") != 0 or not isinstance(data.get("aweme_list"), list):
        raise PublishFlowError("verification_unavailable", "作品列表未返回成功业务状态；不重试发布")
    items = {str(x.get("id")): x for x in data.get("items", [])}
    return [work_view(a, items.get(str(a.get("aweme_id")))) for a in data["aweme_list"]]


def copy_matches(work, spec):
    # Douyin may prepend item_title to desc, and normalizes paragraph whitespace.
    expected = normalize(spec["content"] + " " + " ".join("#" + t for t in spec["tags"]))
    actual = normalize(work["description"])
    return actual in (expected, normalize(spec["title"] + " " + expected)) and work["title"] == spec["title"]


def verify_match(work, spec):
    problems = []
    if not copy_matches(work, spec):
        problems.append("title_or_description")
    duration = spec["video"].get("duration_ms")
    if duration is not None and (work.get("duration_ms") is None or abs(work["duration_ms"] - duration) > 150):
        problems.append("duration")
    if set(work["tags"]) != set(spec["tags"]):
        problems.append("topic_tokens")
    if work["visibility"] != spec["visibility"]:
        problems.append("visibility")
    if spec.get("expected_account") and work["account_name"] != spec["expected_account"]:
        problems.append("account")
    if not work["horizontal_cover_present"] or not work["vertical_cover_present"]:
        problems.append("covers")
    if spec.get("save_permission") != "keep" and work["downloadable"] != (spec["save_permission"] == "allow"):
        problems.append("save_permission")
    return problems


async def verify_receipt(receipt, request, timeout=0):
    deadline = time.monotonic() + timeout
    spec = receipt["spec"]
    while True:
        works = await read_works(request)
        ident = receipt.get("work_id")
        candidates = (
            [w for w in works if w["work_id"] == ident]
            if ident
            else [
                w
                for w in works
                if w["work_id"] not in receipt.get("before_ids", [])
                and copy_matches(w, spec)
                and (w.get("created_at") or 0) >= receipt.get("started_epoch", 0) - 120
            ]
        )
        if len(candidates) > 1:
            raise PublishFlowError("ambiguous_work", "找到多个候选作品；不重复发布，需核对作品ID")
        if candidates:
            work = candidates[0]
            receipt.update(work_id=work["work_id"], work=work, verified_at=datetime.now(timezone.utc).isoformat())
            problems = verify_match(work, spec)
            if receipt.get("account_uid") and work.get("account_uid") != receipt["account_uid"]:
                problems.append("account_uid")
            receipt["verification_mismatches"] = problems
            receipt["status"] = (
                "published"
                if work["status"] == "published" and not problems
                else ("verification_failed" if problems else work["status"])
            )
            if receipt["status"] != "reviewing" or time.monotonic() >= deadline:
                return receipt
        elif time.monotonic() >= deadline:
            receipt["status"] = "submitted_unverified"
            return receipt
        await asyncio.sleep(min(5, max(0, deadline - time.monotonic())))


class VideoPublisher:
    def __init__(
        self,
        client,
        spec,
        receipt_path,
        *,
        review=False,
        prepare_only=False,
        resume=False,
        upload_timeout=600,
        verify_timeout=90,
    ):
        self.client, self.spec = client, spec
        self.path = Path(receipt_path).expanduser().resolve()
        self.assets = self.path.with_suffix(".assets")
        self.review, self.prepare_only, self.resume = review, prepare_only, resume
        self.upload_timeout, self.verify_timeout = upload_timeout, verify_timeout
        self.receipt = {}
        self.submitted = False
        self.response_tasks = set()

    def save(self, **fields):
        self.receipt.update(fields)
        self.receipt["updated_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(self.path, self.receipt)

    async def snapshot(self, page, name):
        self.assets.mkdir(parents=True, exist_ok=True)
        target = self.assets / f"{name}.png"
        await page.screenshot(path=str(target), full_page=True, timeout=15000)
        self.receipt.setdefault("screenshots", {})[name] = str(target)
        self.save()
        return str(target)

    async def account(self, request):
        response = await request.get(CREATOR + "/aweme/v1/creator/pc/user/info/", timeout=30000)
        data = await response.json()
        if response.status != 200 or data.get("status_code") != 0 or not data.get("uid"):
            raise PublishFlowError("not_authenticated", "创作者账号验证失败，请先 dy login")
        return str(data["uid"])

    async def dismiss_help(self, page):
        for button in await page.get_by_role("button", name="我知道了", exact=True).all():
            if await button.is_visible():
                await button.click(timeout=3000)

    async def fill_copy(self, page):
        spec = self.spec
        title = page.get_by_placeholder("填写作品标题，为作品获得更多流量", exact=True)
        await title.fill(spec["title"])
        editor = page.locator('[contenteditable="true"]')
        # A single paragraph avoids the creator editor serializing line breaks as '*'.
        await editor.fill(spec["rendered_content"])
        for tag in spec["tags"]:
            await editor.press("Meta+ArrowDown" if sys.platform == "darwin" else "Control+End")
            await editor.press_sequentially(" #" + tag, delay=45)
            option = page.locator(".mention-suggest-mount-dom").get_by_text(tag, exact=True)
            try:
                await option.wait_for(state="visible", timeout=12000)
                await option.click()
            except Exception as exc:
                raise PublishFlowError("topic_not_found", f"未能选中准确话题: {tag}") from exc
            token = editor.locator('[data-mention="#"]').filter(has_text="#" + tag)
            await token.wait_for(state="attached", timeout=5000)
        return await self.check_copy(page)

    async def check_copy(self, page):
        title = await page.get_by_placeholder("填写作品标题，为作品获得更多流量", exact=True).input_value()
        editor = page.locator('[contenteditable="true"]')
        content = normalize(await editor.inner_text())
        tags = [normalize(x).lstrip("#") for x in await editor.locator('[data-mention="#"]').all_text_contents()]
        expected = normalize(self.spec["rendered_content"] + " " + " ".join("#" + t for t in self.spec["tags"]))
        if title != self.spec["title"] or content != expected or tags != self.spec["tags"]:
            raise PublishFlowError("copy_mismatch", "表单标题、完整简介或真实话题元素与请求不符，停止提交")
        return {"title": title, "description": content, "tags": tags}

    def cover_card(self, page, orientation):
        label = "横封面4:3" if orientation == "horizontal" else "竖封面3:4"
        return page.locator('[class*="coverControl-"]').filter(has_text=label)

    async def covers(self, page):
        # Both are independent input images; no frame extraction or AI generation.
        before = {}
        for orientation in ("horizontal", "vertical"):
            image = self.cover_card(page, orientation).locator("img")
            src = await image.get_attribute("src") if await image.count() == 1 else None
            before[orientation] = urlsplit(src).path if src else None
        await self.cover_card(page, "horizontal").locator('[class*="cover-"]').first.click()
        for orientation in ("horizontal", "vertical"):
            if orientation == "vertical":
                await page.get_by_role("button", name="设置竖封面", exact=True).click()
            await page.get_by_text(
                "横封面预览（4:3）" if orientation == "horizontal" else "竖封面预览（3:4）", exact=True
            ).wait_for()
            upload = page.locator(".semi-upload").filter(has=page.locator(".semi-upload-drag-area-main-text"))
            # Never use the last generic file input: reference-image inputs share its accept type.
            field = upload.locator("input.semi-upload-hidden-input")
            if await field.count() != 1:
                raise PublishFlowError("cover_control_changed", "无法唯一定位真正的封面图片上传框")
            await field.set_input_files(self.spec["covers"][orientation]["path"])
            await page.wait_for_timeout(1800)
            await self.snapshot(page, f"cover-editor-{orientation}")
        await page.get_by_role("button", name="完成", exact=True).click()
        await page.get_by_role("button", name="完成", exact=True).wait_for(state="hidden", timeout=90000)
        await self.wait_covers(page, before)
        await self.check_covers(page)

    async def wait_covers(self, page, before):
        # Loaded thumbnails may still be the old defaults while the platform processes the upload.
        deadline, previous, stable_since = time.monotonic() + 120, None, None
        while time.monotonic() < deadline:
            paths = []
            for orientation in ("horizontal", "vertical"):
                image = self.cover_card(page, orientation).locator("img")
                if await image.count() != 1:
                    break
                state = await image.evaluate("el=>({src:el.src,complete:el.complete,width:el.naturalWidth})")
                path = urlsplit(state["src"]).path
                if not (
                    state["complete"]
                    and state["width"] > 0
                    and state["src"].startswith("https://")
                    and path != before[orientation]
                ):
                    break
                paths.append(path)
            distinct = self.spec["covers"]["horizontal"]["sha256"] != self.spec["covers"]["vertical"]["sha256"]
            ready = (
                len(paths) == 2
                and (not distinct or paths[0] != paths[1])
                and "封面检测中" not in await page.locator("body").inner_text()
            )
            current = tuple(paths) if ready else None
            if current is None or current != previous:
                stable_since = time.monotonic() if current else None
            elif stable_since is not None and time.monotonic() - stable_since >= 8:
                self.save(cover_processing={"both_updated": True, "stable_seconds": 8})
                return
            previous = current
            await asyncio.sleep(1)
        raise PublishFlowError("cover_processing_timeout", "两张封面尚未更新并稳定，停止提交")

    async def check_covers(self, page):
        observed = {}
        for orientation in ("horizontal", "vertical"):
            card = self.cover_card(page, orientation)
            image = card.locator("img")
            await image.wait_for(state="visible", timeout=60000)
            await page.wait_for_function(
                "(el)=>el.complete && el.naturalWidth > 0", arg=await image.element_handle(), timeout=30000
            )
            src = await image.get_attribute("src")
            if not src or not src.startswith("https://"):
                raise PublishFlowError("cover_not_saved", f"{orientation}封面尚未上传完成")
            # Strip query strings that can carry signed private image URLs.
            observed[orientation] = {
                "image_path": urlsplit(src).path,
                "source_sha256": self.spec["covers"][orientation]["sha256"],
            }
            self.assets.mkdir(parents=True, exist_ok=True)
            p = self.assets / f"cover-{orientation}.png"
            await card.screenshot(path=str(p))
            self.receipt.setdefault("screenshots", {})[f"cover-{orientation}"] = str(p)
        previous = self.receipt.get("covers")
        if previous and any(previous[k]["image_path"] != observed[k]["image_path"] for k in observed):
            raise PublishFlowError("cover_changed", "封面在预览后发生变化，停止提交")
        self.save(covers=observed)
        return observed

    async def settings(self, page):
        for text in (self.spec["visibility"], "立即发布"):
            label = page.locator("label").filter(has_text=re.compile("^" + re.escape(text) + r"\s*$"))
            if not await label.locator("input").is_checked():
                await label.click()
            if not await label.locator("input").is_checked():
                raise PublishFlowError("settings_mismatch", f"设置未生效: {text}")
        if self.spec["save_permission"] != "keep":
            label_text = "允许" if self.spec["save_permission"] == "allow" else "不允许"
            await page.locator("label").filter(has_text=re.compile("^" + label_text + r"\s*$")).click()
        return await self.check_settings(page)

    async def check_settings(self, page):
        selected = await page.locator("label:has(input:checked)").all_text_contents()
        selected = [normalize(s) for s in selected]
        if self.spec["visibility"] not in selected or "立即发布" not in selected:
            raise PublishFlowError("settings_mismatch", "可见范围或发布时间与请求不符")
        download = "allow" if "允许" in selected else "deny" if "不允许" in selected else "unknown"
        if self.spec["save_permission"] != "keep" and download != self.spec["save_permission"]:
            raise PublishFlowError("settings_mismatch", "保存权限与请求不符")
        # The supported workflow starts with an empty form. Do not add recommended events,
        # POIs, collections, products, declarations, music or sync destinations.
        return {
            "visibility": self.spec["visibility"],
            "timing": "immediate",
            "save_permission": download,
            "selected_labels": selected,
        }

    async def wait_upload(self, page):
        deadline = time.monotonic() + self.upload_timeout
        while time.monotonic() < deadline:
            body = await page.locator("body").inner_text()
            if "上传失败" in body or "解析失败" in body:
                raise PublishFlowError("upload_failed", "视频上传或解析失败")
            pending = ("文件解析中，请稍等", "预览转码中", "视频上传中", "正在上传视频")
            if await page.get_by_text("重新上传", exact=True).is_visible() and not any(
                text in body for text in pending
            ):
                return
            await asyncio.sleep(2)
        raise PublishFlowError("upload_timeout", "上传尚未完成；不会提前点击发布")

    async def save_draft(self, page, context):
        await page.get_by_role("button", name="暂存离开", exact=True).click()
        await page.get_by_text("继续编辑", exact=True).wait_for(state="visible", timeout=30000)
        # Reopen and verify it really persisted, then save once more before closing.
        await page.get_by_text("继续编辑", exact=True).click()
        await page.get_by_placeholder("填写作品标题，为作品获得更多流量", exact=True).wait_for()
        await self.check_copy(page)
        await self.check_covers(page)
        await page.get_by_role("button", name="暂存离开", exact=True).click()
        await page.get_by_text("继续编辑", exact=True).wait_for(state="visible", timeout=30000)
        private_dir = Path(config.CONFIG_DIR) / "publish-sessions"
        private_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        session = private_dir / (hashlib.sha256(str(self.path).encode()).hexdigest() + ".json")
        if session.is_symlink():
            raise PublishFlowError("unsafe_session", "发布会话文件不能是软链接")
        # Write private auth state separately; it must never be copied into the public receipt.
        state = await context.storage_state(indexed_db=True)
        atomic_json(session, state)
        # A successful same-tab reload is insufficient: verify a fresh context can restore it.
        probe = await context.browser.new_context(storage_state=str(session), viewport={"width": 1440, "height": 1100})
        try:
            restored = await probe.new_page()
            await restored.goto(UPLOAD, wait_until="domcontentloaded")
            await restored.get_by_text("继续编辑", exact=True).wait_for(state="visible", timeout=15000)
            await restored.get_by_text("继续编辑", exact=True).click()
            await restored.get_by_placeholder("填写作品标题，为作品获得更多流量", exact=True).wait_for()
            await self.check_copy(restored)
            await self.check_covers(restored)
        finally:
            await probe.close()
        self.save(status="prepared", draft_saved=True, fresh_context_restore_verified=True, session_file=str(session))

    async def capture_response(self, response):
        path = urlsplit(response.url).path
        if response.request.method != "POST" or not re.search(r"/(?:create|create_v\d+)/?$", path):
            return
        try:
            data = await response.json()
        except Exception:
            return
        code = data.get("status_code")
        aweme = data.get("aweme") or data.get("aweme_info") or data.get("data") or {}
        ident = data.get("aweme_id") or (aweme.get("aweme_id") if isinstance(aweme, dict) else None)
        proof = {"endpoint": path, "http_status": response.status, "status_code": code}
        self.receipt.setdefault("submit_responses", []).append(proof)
        if ident:
            self.receipt["work_id"] = str(ident)
        self.save()

    async def run(self):
        from playwright.async_api import async_playwright

        self.assets.mkdir(parents=True, exist_ok=True)
        with receipt_lock(self.path):
            if self.path.exists():
                old = json.loads(self.path.read_text(encoding="utf-8"))
                if old["spec"]["fingerprint"] != self.spec["fingerprint"]:
                    raise PublishFlowError("receipt_mismatch", "此凭据属于不同的文件或文案，请勿覆盖")
                if old.get("submit_attempted"):
                    raise PublishFlowError(
                        "already_submitted", "此凭据已经尝试提交；请运行 dy publish-verify，禁止盲目重发"
                    )
                if not self.resume:
                    raise PublishFlowError("receipt_exists", "凭据已存在；使用 --resume 继续已保存的草稿")
                if old.get("status") != "prepared" or not old.get("draft_saved"):
                    raise PublishFlowError("draft_unavailable", "当前凭据没有可验证的已保存草稿")
                self.receipt = old
            else:
                if self.resume:
                    raise PublishFlowError("missing_receipt", "继续发布需要原凭据")
                self.save(
                    schema_version=1,
                    status="starting",
                    spec=self.spec,
                    started_epoch=time.time(),
                    submit_attempted=False,
                )
            check_files(self.spec)
            async with async_playwright() as pw:
                browser = await launch_chrome(pw, headless=self.client.headless, slow_mo=self.client.slow_mo)
                session = self.receipt.get("session_file") if self.resume else self.client.cookie_file
                context = await browser.new_context(storage_state=session, viewport={"width": 1440, "height": 1100})
                page = await context.new_page()
                page.set_default_timeout(15000)
                try:
                    uid = await self.account(context.request)
                    if self.receipt.get("account_uid") and self.receipt["account_uid"] != uid:
                        raise PublishFlowError("account_mismatch", "草稿凭据与当前登录账号不同")
                    self.save(account_uid=uid)
                    works = await read_works(context.request)
                    # The same text on an existing work is a collision, not permission to repost.
                    if any(copy_matches(w, self.spec) for w in works):
                        raise PublishFlowError(
                            "existing_work", "作品列表已有相同标题和全文；请核对既有作品，停止重复投稿"
                        )
                    self.save(before_ids=[w["work_id"] for w in works])
                    await page.goto(UPLOAD, wait_until="domcontentloaded")
                    await page.locator('input[type="file"][accept*="video"]').wait_for(state="attached")
                    if self.resume:
                        await page.get_by_text("继续编辑", exact=True).click()
                        await page.get_by_placeholder("填写作品标题，为作品获得更多流量", exact=True).wait_for()
                        await self.check_copy(page)
                        await self.check_covers(page)
                    else:
                        if await page.get_by_text("继续编辑", exact=True).is_visible():
                            raise PublishFlowError(
                                "unrelated_draft", "账号已有草稿；不会覆盖。请使用其发布凭据继续处理"
                            )
                        await page.locator('input[type="file"][accept*="video"]').set_input_files(
                            self.spec["video"]["path"]
                        )
                        await page.get_by_placeholder("填写作品标题，为作品获得更多流量", exact=True).wait_for(
                            timeout=self.upload_timeout * 1000
                        )
                        self.save(status="uploading")
                        await self.wait_upload(page)
                        await self.dismiss_help(page)
                        if self.spec.get("expected_account"):
                            # Actual preview is produced by the signed-in creator account.
                            expected = self.spec["expected_account"]
                            await page.get_by_text("@" + expected, exact=True).first.wait_for(
                                state="visible", timeout=60000
                            )
                            body = await page.locator("body").inner_text()
                            if f"@{expected}" not in body:
                                raise PublishFlowError("account_mismatch", f"预览账号与预期 {expected} 不符")
                        await self.fill_copy(page)
                        await self.covers(page)
                        await self.settings(page)
                    form = await self.check_copy(page)
                    form["settings"] = await self.check_settings(page)
                    await self.check_covers(page)
                    self.save(status="ready", form=form)
                    await self.snapshot(page, "before-submit")
                    if self.prepare_only:
                        await self.save_draft(page, context)
                        return self.receipt
                    if self.review:
                        print(
                            f"[dy] 发布前预览: {self.path}\n[dy] 输入 publish 提交；输入 save 保存草稿；其他输入或EOF将保存草稿并退出。",
                            file=sys.stderr,
                            flush=True,
                        )
                        answer = (await asyncio.to_thread(sys.stdin.readline)).strip()
                        if answer != "publish":
                            await self.save_draft(page, context)
                            return self.receipt
                    # Re-read after the review pause; a human may have changed the form.
                    await self.check_copy(page)
                    await self.check_settings(page)
                    await self.check_covers(page)
                    await self.wait_upload(page)

                    def on_response(response):
                        task = asyncio.create_task(self.capture_response(response))
                        self.response_tasks.add(task)
                        task.add_done_callback(self.response_tasks.discard)

                    page.on("response", on_response)
                    # Durable marker BEFORE click. A timeout/crash can never cause an automatic retry.
                    self.save(status="submitting", submit_attempted=True, submitted_epoch=time.time())
                    self.submitted = True
                    await page.get_by_role("button", name="发布", exact=True).click(timeout=15000)
                    try:
                        await page.wait_for_url("**/content/manage**", timeout=45000)
                    except Exception:
                        pass  # Work-list verification resolves outcome; never click twice.
                    await verify_receipt(self.receipt, context.request, self.verify_timeout)
                    self.save()
                    await self.snapshot(page, "after-submit")
                    return self.receipt
                except Exception as exc:
                    status = "submitted_unverified" if self.submitted else "failed_before_submit"
                    self.save(
                        status=status,
                        error={"code": getattr(exc, "code", "publish_flow_error"), "message": str(exc)[:700]},
                    )
                    try:
                        await self.snapshot(page, "failure")
                    except Exception:
                        pass
                    if isinstance(exc, PublishFlowError):
                        raise
                    raise PublishFlowError("publish_flow_error", f"{exc}; 凭据: {self.path}") from exc
                finally:
                    if self.response_tasks:
                        await asyncio.gather(*list(self.response_tasks), return_exceptions=True)
                    await browser.close()


async def verify_pages(receipt, browser, cookie_file, receipt_path):
    """Read management/public pages. Report playback separately from API publication."""
    context = await browser.new_context(storage_state=cookie_file, viewport={"width": 1440, "height": 1100})
    page = await context.new_page()
    assets = Path(receipt_path).with_suffix(".assets")
    assets.mkdir(parents=True, exist_ok=True)
    result = {"status": "partial", "checked_at": datetime.now(timezone.utc).isoformat()}
    spec = receipt["spec"]
    expected = normalize(spec["title"] + " " + spec["content"] + " " + " ".join("#" + t for t in spec["tags"]))
    try:
        await page.goto(MANAGE, wait_until="domcontentloaded")
        card = page.locator('[class*="video-card-info-"]').filter(has_text=spec["title"])
        await card.wait_for(state="visible", timeout=30000)
        result["manage_copy_matches"] = expected in normalize(await card.inner_text())
        result["manage_published"] = await card.get_by_text("已发布", exact=True).is_visible()
        shot = assets / "manage-verified.png"
        try:
            await page.screenshot(path=str(shot), full_page=True, timeout=15000)
            receipt.setdefault("screenshots", {})["manage-verified"] = str(shot)
        except Exception as exc:
            result["manage_screenshot_error"] = str(exc)[:300]
        await page.goto(receipt["work"]["url"], wait_until="domcontentloaded")
        await page.get_by_text(spec["title"], exact=False).first.wait_for(state="visible", timeout=30000)
        await page.wait_for_timeout(3000)
        body = normalize(await page.locator("body").inner_text())
        result["public_copy_matches"] = expected in body
        name = spec.get("expected_account") or receipt["work"].get("account_name")
        result["public_account_matches"] = bool(
            name and any([await node.is_visible() for node in await page.get_by_text(name, exact=True).all()])
        )
        media = page.locator("video")
        first = await media.evaluate_all(
            "(es)=>es.map(e=>({duration:Number.isFinite(e.duration)?e.duration:null,time:e.currentTime,ready:e.readyState,error:e.error?.code??null}))"
        )
        await page.wait_for_timeout(2000)
        second = await media.evaluate_all(
            "(es)=>es.map(e=>({duration:Number.isFinite(e.duration)?e.duration:null,time:e.currentTime,ready:e.readyState,error:e.error?.code??null}))"
        )
        expected_seconds = receipt["work"]["duration_ms"] / 1000
        matches = [
            (a, b)
            for a, b in zip(first, second)
            if b["duration"] is not None and abs(b["duration"] - expected_seconds) < 0.2
        ]
        result["public_duration_matches"] = bool(matches)
        result["playback_advancing"] = any(
            b["time"] > a["time"] + 0.2 and b["ready"] >= 2 and not b["error"] for a, b in matches
        )
        result["public_duration_seconds"] = matches[0][1]["duration"] if matches else None
        shot = assets / "public-verified.png"
        try:
            await page.screenshot(path=str(shot), full_page=True, timeout=15000)
            receipt.setdefault("screenshots", {})["public-verified"] = str(shot)
        except Exception as exc:
            result["public_screenshot_error"] = str(exc)[:300]
        checks = (
            "manage_copy_matches",
            "manage_published",
            "public_copy_matches",
            "public_account_matches",
            "public_duration_matches",
            "playback_advancing",
        )
        result["status"] = "verified" if all(result.get(k) for k in checks) else "partial"
    except Exception as exc:
        result["error"] = str(exc)[:700]
    finally:
        await context.close()
    receipt["page_verification"] = result
    return result


async def verify_file(receipt_path, cookie_file, timeout=0, check_pages=False):
    from playwright.async_api import async_playwright

    path = Path(receipt_path).expanduser().resolve(strict=True)
    with receipt_lock(path):
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if not receipt.get("submit_attempted"):
            raise PublishFlowError("not_submitted", "此凭据尚未提交，不能标记已发布或归档")
        async with async_playwright() as pw:
            request = await pw.request.new_context(storage_state=cookie_file)
            try:
                await verify_receipt(receipt, request, timeout)
                if check_pages and receipt.get("work"):
                    browser = await launch_chrome(pw, headless=True)
                    try:
                        await verify_pages(receipt, browser, cookie_file, path)
                    finally:
                        await browser.close()
                receipt["updated_at"] = datetime.now(timezone.utc).isoformat()
                atomic_json(path, receipt)
                return receipt
            finally:
                await request.dispose()
