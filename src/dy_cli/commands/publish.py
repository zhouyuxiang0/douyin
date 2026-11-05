"""dy publish: staged, verified video publishing; legacy image support is unchanged."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import click

from dy_cli.engines.playwright_client import PlaywrightClient, PlaywrightError
from dy_cli.engines.publish_flow import PublishFlowError, VideoPublisher, make_spec, verify_file
from dy_cli.utils import config
from dy_cli.utils.output import DyCliError, console, info, print_json, success


@click.command("publish", help="发布视频或图文到抖音；视频支持独立双封面、预览、草稿与结果核验")
@click.option("--title", "-t", help="标题；--resume 时从凭据读取")
@click.option("--content", "-c", default=None, help="描述正文")
@click.option("--content-file", type=click.Path(exists=True), help="从文件读取完整描述")
@click.option("--video", "-v", default=None, help="视频文件路径")
@click.option("--images", "-i", multiple=True, help="图片路径（可多个）")
@click.option("--tags", multiple=True, help="真实话题名称（可多个，不带#）")
@click.option("--visibility", type=click.Choice(["公开", "好友可见", "仅自己可见"]), default="公开", help="可见范围")
@click.option("--schedule", default=None, help="定时发布；新版视频路径暂不支持，失败不会转为立即发布")
@click.option("--thumbnail", type=click.Path(exists=True), help="通用独立封面图片，供横竖封面使用")
@click.option("--thumbnail-horizontal", type=click.Path(exists=True), help="独立横封面图片，建议4:3")
@click.option("--thumbnail-vertical", type=click.Path(exists=True), help="独立竖封面图片，建议3:4")
@click.option("--account", default=None, help="登录账号配置名")
@click.option("--expected-account", default=None, help="预期创作者昵称，不符则停止")
@click.option("--save-permission", type=click.Choice(["keep", "allow", "deny"]), default="keep", help="视频保存权限")
@click.option("--headless", is_flag=True, help="使用无头浏览器")
@click.option("--dry-run", is_flag=True, help="仅检查本地参数，不上传、不打开浏览器")
@click.option("--review", is_flag=True, help="上传并配置后暂停，查看预览，再从stdin输入publish或save")
@click.option("--prepare-only", is_flag=True, help="上传、配置并验证保存草稿，不发布")
@click.option("--receipt", type=click.Path(), help="发布凭据JSON路径；默认在视频旁保存")
@click.option("--resume", type=click.Path(exists=True), help="从已保存草稿的原凭据继续，不重复上传")
@click.option("--upload-timeout", type=click.IntRange(30, 1800), default=600, help="上传等待秒数")
@click.option("--verify-timeout", type=click.IntRange(0, 600), default=90, help="发布后核验等待秒数")
@click.option("--json-output", "as_json", is_flag=True, help="输出JSON信封")
def publish(
    title,
    content,
    content_file,
    video,
    images,
    tags,
    visibility,
    schedule,
    thumbnail,
    thumbnail_horizontal,
    thumbnail_vertical,
    account,
    expected_account,
    save_permission,
    headless,
    dry_run,
    review,
    prepare_only,
    receipt,
    resume,
    upload_timeout,
    verify_timeout,
    as_json,
):
    if resume:
        if any(
            (
                title,
                content is not None,
                content_file,
                video,
                images,
                tags,
                thumbnail,
                thumbnail_horizontal,
                thumbnail_vertical,
                receipt,
                schedule,
                expected_account,
            )
        ):
            raise DyCliError("invalid_argument", "--resume 使用原凭据，不可同时传入新文案、媒体或凭据路径")
        # Reject explicit setting overrides instead of silently ignoring them.
        ctx = click.get_current_context()
        for key in ("visibility", "save_permission", "account"):
            if ctx.get_parameter_source(key) == click.core.ParameterSource.COMMANDLINE:
                raise DyCliError("invalid_argument", f"--resume 不接受覆盖原设置: {key}")
        try:
            previous = json.loads(Path(resume).read_text(encoding="utf-8"))
            spec = previous["spec"]
        except (ValueError, KeyError, OSError) as exc:
            raise DyCliError("invalid_receipt", str(exc)) from exc
        if dry_run:
            print_json({"dry_run": True, "resume": str(Path(resume).resolve()), "spec": spec})
            return
        receipt, account, video = resume, spec["account"], spec["video"]["path"]
    else:
        if not title:
            raise DyCliError("invalid_argument", "必须提供 --title")
        if content_file:
            content = Path(content_file).read_text(encoding="utf-8").strip()
        content = content or ""
        images, tags = list(images), list(tags)
        if not images and not video:
            raise DyCliError("invalid_argument", "必须提供视频 (--video) 或图片 (--images)")
        if video and images:
            raise DyCliError("invalid_argument", "不能同时提供视频和图片，请选择一种")
        for media in [video] if video else images:
            if not media.startswith("http") and not os.path.isfile(media):
                raise DyCliError("invalid_argument", f"文件不存在: {media}")
        if dry_run:
            preview = {
                "dry_run": True,
                "title": title,
                "content": content,
                "video": video,
                "images": images,
                "tags": tags,
                "visibility": visibility,
                "schedule": schedule,
                "thumbnail": thumbnail,
                "thumbnail_horizontal": thumbnail_horizontal,
                "thumbnail_vertical": thumbnail_vertical,
                "expected_account": expected_account,
                "save_permission": save_permission,
                "review": review,
                "prepare_only": prepare_only,
                "receipt": receipt,
            }
            if as_json:
                print_json(preview)
            else:
                console.print_json(json.dumps(preview, ensure_ascii=False))
            return
        if images and any((review, prepare_only, receipt, thumbnail_horizontal, thumbnail_vertical, expected_account)):
            raise DyCliError("invalid_argument", "双封面、草稿和凭据选项仅支持视频；图文路径未改造")
        if video:
            try:
                spec = make_spec(
                    title=title,
                    content=content,
                    video=video,
                    tags=tags,
                    visibility=visibility,
                    thumbnail=thumbnail,
                    thumbnail_horizontal=thumbnail_horizontal,
                    thumbnail_vertical=thumbnail_vertical,
                    account=account or config.get("default.account", "default"),
                    expected_account=expected_account,
                    save_permission=save_permission,
                    schedule=schedule,
                )
            except (PublishFlowError, OSError) as exc:
                raise DyCliError(getattr(exc, "code", "invalid_media"), str(exc)) from exc
            receipt = receipt or str(Path(video).resolve().with_suffix(".publish.json"))
    cfg = config.load_config()
    client = PlaywrightClient(
        account=account or config.get("default.account", "default"),
        headless=headless or cfg["playwright"].get("headless", False),
        slow_mo=cfg["playwright"].get("slow_mo", 0),
    )
    if not client.cookie_exists():
        raise DyCliError("not_authenticated", "未登录，请先运行: dy login")
    try:
        if video:
            info("视频发布流程启动；凭据: " + receipt)
            flow = VideoPublisher(
                client,
                spec,
                receipt,
                review=review,
                prepare_only=prepare_only,
                resume=bool(resume),
                upload_timeout=upload_timeout,
                verify_timeout=verify_timeout,
            )
            result = asyncio.run(flow.run())
            status = result["status"]
            if as_json:
                print_json(result)
            else:
                console.print_json(json.dumps(result, ensure_ascii=False))
            if status == "published":
                success("作品已发布，标题、全文、话题、可见范围与双封面存在性已核验")
            elif status == "prepared":
                info("草稿已保存并验证可恢复，尚未发布")
            elif status == "reviewing":
                info("作品已提交，仍在审核中；不得归档清理")
            else:
                info("发布结果未完全核实，状态: " + status + "；使用 dy publish-verify 检查，不重复投稿")
                raise click.exceptions.Exit(2)
        else:
            result = client.publish_image_text(
                title=title,
                content=content,
                images=[os.path.abspath(img) if not img.startswith("http") else img for img in images],
                tags=tags or None,
                visibility=visibility,
                schedule_at=schedule,
            )
            info("图文旧流程已返回，需另行核对作品状态")
            if as_json:
                print_json(result)
    except (PublishFlowError, PlaywrightError) as exc:
        raise DyCliError(getattr(exc, "code", "playwright_error"), str(exc)) from exc


@click.command("publish-verify", help="只读核对发布凭据对应作品；不上传、不重发")
@click.argument("receipt", type=click.Path(exists=True))
@click.option("--timeout", type=click.IntRange(0, 600), default=0, help="等待审核/列表更新的秒数")
@click.option("--check-pages", is_flag=True, help="另核对管理页、公开全文、账号与播放器，并保存截图")
@click.option("--json-output", "as_json", is_flag=True)
def publish_verify(receipt, timeout, check_pages, as_json):
    try:
        data = json.loads(Path(receipt).read_text(encoding="utf-8"))
        result = asyncio.run(
            verify_file(receipt, config.get_cookie_file(data["spec"]["account"]), timeout, check_pages)
        )
    except (PublishFlowError, KeyError, ValueError, OSError) as exc:
        raise DyCliError(getattr(exc, "code", "invalid_receipt"), str(exc)) from exc
    if as_json:
        print_json(result)
    else:
        console.print_json(json.dumps(result, ensure_ascii=False))
    if result["status"] not in ("published", "reviewing") or (
        check_pages and result.get("page_verification", {}).get("status") != "verified"
    ):
        raise click.exceptions.Exit(2)
