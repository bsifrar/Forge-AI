from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from workspace_ai.app.settings import get_settings
from workspace_ai.workspace_memory.session_store import SessionStore


class SettingsService:
    def __init__(self, store: SessionStore | None = None) -> None:
        self.store = store or SessionStore()

    def defaults(self) -> Dict[str, Any]:
        settings = get_settings()
        return {
            "api_enabled": bool(settings.openai_api_key or settings.xai_api_key),
            "selected_provider": settings.default_provider,
            "selected_model": settings.default_model,
            "daily_spend_cap_usd": 5.0,
            "hourly_call_cap": 50,
            "price_input_per_1m_usd": 0.0,
            "price_output_per_1m_usd": 0.0,
        }

    def api_key(self, provider: str = "openai") -> str:
        normalized = provider.strip().lower()
        settings_map = self.store.list_settings()
        if normalized == "xai":
            stored = settings_map.get("xai_api_key", "")
            if isinstance(stored, str) and stored.strip():
                return stored.strip()
            return get_settings().xai_api_key
        stored = settings_map.get("api_key", "")
        if isinstance(stored, str) and stored.strip():
            return stored.strip()
        return get_settings().openai_api_key

    def get(self) -> Dict[str, Any]:
        payload = self.defaults()
        payload.update(self.store.list_settings())
        payload.pop("api_key", None)
        settings = get_settings()
        project_root = Path(__file__).resolve().parents[2]
        payload["adapter_mode"] = settings.adapter_mode
        payload["external_base_url"] = settings.external_base_url
        payload["env_workspace_present"] = (project_root / ".env.workspace").exists()
        payload["env_secret_present"] = (project_root / ".env.workspace.secret").exists()
        payload["api_key_configured"] = bool(self.api_key(str(payload.get("selected_provider") or "openai")))
        payload["available_providers"] = ["openai", "xai"]
        payload["usage"] = self.store.api_usage_summary()
        payload["remaining_daily_budget_usd"] = max(0.0, round(float(payload["daily_spend_cap_usd"]) - float(payload["usage"]["spent_today_usd"]), 6))
        payload["remaining_hourly_calls"] = max(0, int(payload["hourly_call_cap"]) - int(payload["usage"]["calls_this_hour"]))
        payload["first_run_complete"] = bool(payload["env_workspace_present"] and (payload["api_key_configured"] or not payload.get("api_enabled", False)))
        return payload

    def update(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        for key, value in updates.items():
            if value is not None:
                self.store.set_setting(key=key, value=value)
        return self.get()


    def bootstrap_local_setup(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        project_root = Path(__file__).resolve().parents[2]
        env_path = project_root / '.env.workspace'
        secret_path = project_root / '.env.workspace.secret'

        adapter_mode = (updates.get('adapter_mode') or 'null').strip().lower()
        external_base_url = (updates.get('external_base_url') or 'http://127.0.0.1:8080').strip()
        selected_provider = (updates.get('selected_provider') or 'openai').strip().lower()
        selected_model = (updates.get('selected_model') or 'gpt-5.4').strip()
        daily_cap = float(updates.get('daily_spend_cap_usd') or 0.0)
        hourly_cap = int(updates.get('hourly_call_cap') or 0)
        input_price = float(updates.get('price_input_per_1m_usd') or 0.0)
        output_price = float(updates.get('price_output_per_1m_usd') or 0.0)
        api_enabled = bool(updates.get('api_enabled'))
        api_key = (updates.get('api_key') or '').strip()

        env_lines = [
            '# Workspace runtime defaults. Keep secrets in .env.workspace.secret.',
            f'WORKSPACE_ADAPTER_MODE={adapter_mode}',
            f'WORKSPACE_HOST=127.0.0.1',
            f'WORKSPACE_PORT=8092',
            f'WORKSPACE_PROVIDER={selected_provider}',
            f'WORKSPACE_MODEL={selected_model}',
            f'WORKSPACE_DAILY_CAP={daily_cap:g}',
            f'WORKSPACE_HOURLY_CAP={hourly_cap}',
            f'WORKSPACE_INPUT_PRICE={input_price:g}',
            f'WORKSPACE_OUTPUT_PRICE={output_price:g}',
        ]
        if adapter_mode == 'external':
            env_lines.insert(2, f'WORKSPACE_EXTERNAL_BASE_URL={external_base_url}')
        env_path.write_text('\n'.join(env_lines) + '\n')

        if api_key:
            secret_path.write_text('# Local-only secrets for workspace runtime.\n' f'WORKSPACE_API_KEY="{api_key}"\n')
            self.store.set_setting(key='api_key', value=api_key)
        elif secret_path.exists():
            secret_path.unlink()
            self.store.set_setting(key='api_key', value='')

        self.update({
            'api_enabled': api_enabled,
            'selected_provider': selected_provider,
            'selected_model': selected_model,
            'daily_spend_cap_usd': daily_cap,
            'hourly_call_cap': hourly_cap,
            'price_input_per_1m_usd': input_price,
            'price_output_per_1m_usd': output_price,
        })
        return self.get()
