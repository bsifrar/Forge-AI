from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspaceSettings:
    host: str
    port: int
    storage_path: Path
    external_base_url: str
    adapter_mode: str
    openai_api_key: str
    xai_api_key: str
    default_provider: str
    default_model: str


def _load_env_files() -> None:
    app_root = Path(__file__).resolve().parents[1]
    project_root = app_root.parent
    for filename in ['.env.workspace', '.env.workspace.secret']:
        path = project_root / filename
        if not path.exists():
            continue
        for raw_line in path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)

    if os.getenv('WORKSPACE_API_KEY') and not os.getenv('WORKSPACE_OPENAI_API_KEY'):
        os.environ['WORKSPACE_OPENAI_API_KEY'] = os.environ['WORKSPACE_API_KEY']


def get_settings() -> WorkspaceSettings:
    _load_env_files()
    root = Path(__file__).resolve().parents[1]
    return WorkspaceSettings(
        host=os.getenv('WORKSPACE_HOST', '127.0.0.1'),
        port=int(os.getenv('WORKSPACE_PORT', '8092')),
        storage_path=Path(
            os.getenv('WORKSPACE_STORAGE_PATH', str(root / 'storage' / 'workspace.db'))
        ).expanduser().resolve(),
        external_base_url=os.getenv('WORKSPACE_EXTERNAL_BASE_URL', 'http://127.0.0.1:8080'),
        adapter_mode=os.getenv('WORKSPACE_ADAPTER_MODE', 'null').strip().lower(),
        openai_api_key=os.getenv('WORKSPACE_API_KEY', os.getenv('WORKSPACE_OPENAI_API_KEY', os.getenv('OPENAI_API_KEY', ''))),
        xai_api_key=os.getenv('WORKSPACE_XAI_API_KEY', os.getenv('XAI_API_KEY', '')),
        default_provider=os.getenv('WORKSPACE_PROVIDER', 'openai').strip().lower(),
        default_model=os.getenv('WORKSPACE_MODEL', os.getenv('OPENAI_MODEL', 'gpt-5.4')),
    )
