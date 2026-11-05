import ast
import asyncio
import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

from dy_cli.main import cli
from dy_cli.utils import config
from dy_cli.utils.browser import launch_chrome


@pytest.mark.parametrize('headless', [False, True])
def test_chrome_channel_preserves_display_and_delay(headless):
    launch = AsyncMock(return_value=object())
    pw = SimpleNamespace(chromium=SimpleNamespace(launch=launch))
    result = asyncio.run(launch_chrome(pw, headless=headless, slow_mo=25))
    launch.assert_awaited_once_with(channel='chrome', headless=headless, slow_mo=25)
    assert result is launch.return_value


def test_launch_failure_propagates_without_fallback_or_retry():
    failure = RuntimeError('Chrome unavailable')
    launch = AsyncMock(side_effect=failure)
    pw = SimpleNamespace(chromium=SimpleNamespace(launch=launch))
    with pytest.raises(RuntimeError) as exc:
        asyncio.run(launch_chrome(pw, headless=True))
    assert exc.value is failure
    launch.assert_awaited_once()


def test_no_entrypoint_bypasses_shared_browser_policy():
    root = Path(__file__).resolve().parents[1]
    for directory in ('src', 'scripts'):
        for path in (root / directory).rglob('*.py'):
            if path == root / 'src/dy_cli/utils/browser.py':
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in ('launch', 'launch_persistent_context'), str(path)


def test_init_checks_real_chrome_and_does_not_save_on_failure(tmp_path, monkeypatch):
    module = importlib.import_module('dy_cli.commands.init')
    monkeypatch.setattr(module, '_check_playwright', lambda: True)
    monkeypatch.setattr(module, '_check_chrome', lambda: False)
    monkeypatch.setattr(config, 'CONFIG_FILE', str(tmp_path / 'config.json'))
    result = CliRunner().invoke(cli, ['init', '--no-proxy', '--skip-login'])
    assert result.exit_code != 0
    assert '无法启动 Google Chrome' in result.output
    assert not Path(config.CONFIG_FILE).exists()


@pytest.mark.parametrize('flag', ['--skip-browser', '--skip-chromium'])
def test_init_preserves_legacy_skip_flag(flag, tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'CONFIG_DIR', str(tmp_path))
    monkeypatch.setattr(config, 'COOKIES_DIR', str(tmp_path / 'cookies'))
    monkeypatch.setattr(config, 'CONFIG_FILE', str(tmp_path / 'config.json'))
    result = CliRunner().invoke(cli, ['init', '--no-proxy', '--skip-login', flag])
    assert result.exit_code == 0, result.output
    assert '已跳过 Google Chrome 启动检查' in result.output
