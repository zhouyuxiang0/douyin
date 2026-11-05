"""
dy init — 新用户引导式初始化。

自动完成: 检查环境 → 检查 Google Chrome → 配置代理 → 登录。
"""
from __future__ import annotations

import asyncio
import os
import platform
import sys

import click
from rich.panel import Panel

from dy_cli.utils import config
from dy_cli.utils.output import console, error, info, status, success, warning


@click.command("init", help="🚀 初始化设置 (新用户从这里开始)")
@click.option("--proxy", default=None, help="代理地址 (如 http://127.0.0.1:7897)")
@click.option("--no-proxy", is_flag=True, help="不使用代理 (在国内网络)")
@click.option("--skip-login", is_flag=True, help="跳过登录步骤")
@click.option("--skip-browser", "--skip-chromium", "skip_browser", is_flag=True, help="跳过 Google Chrome 启动检查（旧参数名兼容）")
def init(proxy, no_proxy, skip_login, skip_browser):
    """引导新用户完成初始化。"""
    console.print()
    console.print(Panel(
        "[bold]欢迎使用 🎬 dy-cli — 抖音命令行工具[/]\n\n"
        "接下来将引导你完成初始化设置:\n"
        "  [dim]1.[/] 检查系统环境\n"
        "  [dim]2.[/] 检查 Google Chrome\n"
        "  [dim]3.[/] 配置网络\n"
        "  [dim]4.[/] 登录抖音账号",
        title="🚀 初始化向导",
        border_style="blue",
    ))
    console.print()

    # ── Step 1: 环境检查 ──────────────────────────────────
    console.rule("[bold]Step 1/4 — 环境检查[/]")
    console.print()

    status("系统", f"{sys.platform} {platform.machine()}")
    status("Python", f"{sys.version.split()[0]}")

    # Check playwright
    pw_ok = _check_playwright()
    if pw_ok:
        status("Playwright", "✅ 已安装", "green")
    else:
        status("Playwright", "⚠️ 未安装", "yellow")

    # Check httpx
    try:
        import httpx
        status("httpx", f"✅ {httpx.__version__}", "green")
    except ImportError:
        status("httpx", "⚠️ 未安装", "yellow")

    console.print()

    # ── Step 2: 检查 Google Chrome ─────────────────────────────
    console.rule("[bold]Step 2/4 — 检查 Google Chrome[/]")
    console.print()

    if skip_browser:
        info("已跳过 Google Chrome 启动检查")
    elif pw_ok and _check_chrome():
        success("Google Chrome 启动正常")
    else:
        raise click.ClickException("无法启动 Google Chrome；请安装 Chrome 并运行 python -m dy_cli.utils.browser 查看错误。")

    console.print()

    # ── Step 3: 网络配置 ──────────────────────────────────
    console.rule("[bold]Step 3/4 — 网络配置[/]")
    console.print()

    cfg = config.load_config()

    if no_proxy:
        proxy_addr = ""
        info("不使用代理 (国内网络直连)")
    elif proxy:
        proxy_addr = proxy
        info(f"使用指定代理: {proxy}")
    else:
        console.print("  抖音在国内可以直连，海外可能需要代理。")
        console.print("  如果在[bold]国内[/]，直接回车跳过。")
        console.print()
        proxy_addr = click.prompt(
            "  代理地址",
            default=cfg["api"].get("proxy", ""),
            show_default=True,
        )
        if proxy_addr.strip().lower() in ("none", "no", "skip", "跳过", "无", ""):
            proxy_addr = ""

    cfg["api"]["proxy"] = proxy_addr
    config.save_config(cfg)
    success("配置已保存")
    console.print()

    # ── Step 4: 登录 ─────────────────────────────────────
    console.rule("[bold]Step 4/4 — 登录抖音[/]")
    console.print()

    if skip_login:
        info("已跳过登录步骤")
        info("稍后使用 [bold]dy login[/] 登录")
    else:
        from dy_cli.engines.playwright_client import PlaywrightClient, PlaywrightError

        client = PlaywrightClient(headless=False)

        # Check if already logged in
        if client.cookie_exists() and client.check_login():
            success("已登录抖音 ✅")
        else:
            info("即将打开浏览器，请使用抖音 App 扫码登录...")
            console.print()
            console.print(Panel(
                "[bold]请使用抖音 App 扫码登录:[/]\n\n"
                "  1. 打开抖音 App\n"
                "  2. 点击右下角 [bold]我[/]\n"
                "  3. 点击右上角 [bold]☰[/] → [bold]扫一扫[/]\n"
                "  4. 扫描浏览器中的二维码\n\n"
                "[dim]扫码后登录会自动完成，cookies 会持久保存。[/]",
                title="📱 扫码登录",
                border_style="green",
            ))
            console.print()

            try:
                ok = client.login()
                if ok:
                    success("登录成功! 🎉")
                else:
                    warning("登录超时，请稍后重试: dy login")
            except PlaywrightError as e:
                error(f"登录失败: {e}")
                info("稍后使用 [bold]dy login[/] 重试")
            except Exception as e:
                error(f"登录失败: {e}")
                info("请确保 Google Chrome 已安装；运行 python -m dy_cli.utils.browser 检查")

    # ── 完成 ─────────────────────────────────────────────
    console.print()
    console.rule("[bold green]✅ 初始化完成[/]")
    console.print()
    console.print(Panel(
        "[bold]🎉 你已准备就绪! 以下是常用命令:[/]\n\n"
        "  [bold cyan]dy search[/] \"关键词\"              搜索视频\n"
        "  [bold cyan]dy trending[/]                     抖音热榜\n"
        "  [bold cyan]dy download[/] URL                 无水印下载\n"
        "  [bold cyan]dy publish[/] -t 标题 -c 描述 -v 视频  发布视频\n"
        "  [bold cyan]dy detail[/] AWEME_ID              视频详情\n"
        "  [bold cyan]dy analytics[/]                    数据看板\n"
        "  [bold cyan]dy me[/]                           查看我的信息\n"
        "  [bold cyan]dy --help[/]                       查看所有命令\n\n"
        "[dim]提示: 大部分命令支持 --json-output 输出 JSON 格式[/]",
        title="📖 快速参考",
        border_style="cyan",
    ))
    console.print()


def _check_playwright() -> bool:
    """检查 playwright 是否已安装。"""
    try:
        import playwright
        return True
    except ImportError:
        return False


def _check_chrome() -> bool:
    """Actually launch Chrome; installer dry-run does not prove browser availability."""
    from dy_cli.utils.browser import check_chrome
    try:
        asyncio.run(check_chrome())
        return True
    except Exception:
        return False
