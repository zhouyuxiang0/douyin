"""Keep account state and index caches isolated during all local/CI checks."""
import copy

import pytest

from dy_cli.utils import config, index_cache


@pytest.fixture(autouse=True)
def isolate_account_state(tmp_path, monkeypatch):
    folder = tmp_path / '.dy'
    monkeypatch.setattr(config, 'CONFIG_DIR', str(folder))
    monkeypatch.setattr(config, 'CONFIG_FILE', str(folder / 'config.json'))
    monkeypatch.setattr(config, 'COOKIES_DIR', str(folder / 'cookies'))
    defaults = copy.deepcopy(config.DEFAULT_CONFIG)
    defaults['api']['cookie_file'] = str(folder / 'cookies/default.json')
    monkeypatch.setattr(config, 'DEFAULT_CONFIG', defaults)
    monkeypatch.setattr(index_cache, 'INDEX_FILE', str(folder / 'index.json'))
