import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"


@dataclass(frozen=True)
class AccountDiscovery:
    account_id: str
    platform: str
    accounts_path: Path
    config_path: Path


def get_hermes_path() -> Path:
    """Return the Hermes Agent state path."""
    return Path.home() / ".hermes"


def get_openclaw_path() -> Path:
    """Return the OpenClaw state path."""
    state_dir = os.environ.get("OPENCLAW_STATE_DIR")
    if state_dir:
        return Path(state_dir).expanduser()
    if sys.platform == "win32":
        return Path.home() / ".openclaw"
    return Path.home() / ".openclaw"


def candidate_account_paths() -> List[tuple[str, Path]]:
    """Return all known WeChat account directories without platform preference."""
    candidates = [
        ("OpenClaw", get_openclaw_path() / "openclaw-weixin" / "accounts"),
        ("OpenClaw", get_openclaw_path() / "weixin" / "accounts"),
        ("Hermes Agent", get_hermes_path() / "weixin" / "accounts"),
    ]

    seen = set()
    unique = []
    for platform, path in candidates:
        resolved_key = str(path.expanduser())
        if resolved_key in seen:
            continue
        seen.add(resolved_key)
        unique.append((platform, path.expanduser()))
    return unique


def _is_account_config(path: Path) -> bool:
    if path.suffix != ".json":
        return False
    if path.name == "wechat_account.json":
        return False
    return not (
        path.name.endswith(".context-tokens.json")
        or path.name.endswith(".sync.json")
    )


def _account_id_from_config(path: Path) -> str:
    return path.name[:-5]


def iter_account_configs() -> Iterable[AccountDiscovery]:
    for platform, accounts_path in candidate_account_paths():
        if not accounts_path.exists() or not accounts_path.is_dir():
            continue
        for config_path in accounts_path.iterdir():
            if _is_account_config(config_path):
                yield AccountDiscovery(
                    account_id=_account_id_from_config(config_path),
                    platform=platform,
                    accounts_path=accounts_path,
                    config_path=config_path,
                )


def find_weixin_account() -> Optional[AccountDiscovery]:
    """Find a usable account from Hermes Agent or OpenClaw account directories."""
    accounts = list(iter_account_configs())
    if not accounts:
        return None
    return max(accounts, key=lambda item: item.config_path.stat().st_mtime)


def _resolve_accounts_path(use_path: str | Path) -> Optional[Path]:
    base_path = Path(use_path).expanduser()
    if base_path.name == "accounts" and base_path.exists():
        return base_path

    for relative in (
        Path("weixin") / "accounts",
        Path("openclaw-weixin") / "accounts",
    ):
        accounts_path = base_path / relative
        if accounts_path.exists():
            return accounts_path
    return None


def find_account_json(account_id: str, use_path: str | Path | bool = False) -> Dict[str, Any]:
    """
    Find and load account JSON files from Hermes Agent or OpenClaw configuration.
    """
    try:
        if use_path:
            accounts_path = _resolve_accounts_path(use_path)
            if accounts_path is None:
                return {"error": f"微信账号路径不存在: {Path(use_path).expanduser()}"}
        else:
            accounts_path = None
            for account in iter_account_configs():
                if account.account_id == account_id:
                    accounts_path = account.accounts_path
                    break

            if accounts_path is None:
                searched = "\n  ".join(
                    str(path) for _, path in candidate_account_paths()
                )
                return {
                    "error": (
                        f"未找到账号 {account_id} 的微信配置。已搜索:\n  {searched}"
                    )
                }

        data: Dict[str, Any] = {}
        for file_suffix in ("", ".context-tokens", ".sync"):
            json_file = accounts_path / f"{account_id}{file_suffix}.json"
            if not json_file.exists():
                continue
            key = account_id + file_suffix if file_suffix else account_id
            try:
                data[key] = json.loads(json_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                return {"error": f"配置文件 JSON 格式错误: {json_file} ({exc})"}
            except OSError as exc:
                return {"error": f"读取配置文件失败: {json_file} ({exc})"}

        if account_id not in data:
            return {"error": f"账号主配置文件不存在: {accounts_path / f'{account_id}.json'}"}

        return {
            "account_id": account_id,
            "file_path": str(accounts_path),
            "data": data,
        }
    except OSError as exc:
        return {"error": f"读取微信配置失败: {exc}"}


def load_account_credentials(account_id: str) -> Dict[str, Any]:
    """Load and validate credentials needed by the sendmessage API."""
    result = find_account_json(account_id)
    if "error" in result:
        return result

    data = result["data"]
    bot_config = data.get(account_id, {})
    token = bot_config.get("token", "")
    user_id = bot_config.get("userId") or bot_config.get("user_id") or ""
    base_url = bot_config.get("baseUrl") or bot_config.get("base_url") or DEFAULT_BASE_URL

    missing = []
    if not token:
        missing.append("token")
    if not user_id:
        missing.append("user_id/userId")
    if missing:
        return {
            "error": (
                f"账号 {account_id} 缺少必填配置: {', '.join(missing)}。"
                f"配置路径: {result['file_path']}"
            )
        }

    context_token = ""
    context_tokens_file = f"{account_id}.context-tokens"
    context_tokens_data = data.get(context_tokens_file, {})
    if isinstance(context_tokens_data, dict) and context_tokens_data:
        context_token = context_tokens_data.get(user_id) or next(
            (value for value in context_tokens_data.values() if value),
            "",
        )

    return {
        "account_id": account_id,
        "base_url": base_url,
        "token": token,
        "user_id": user_id,
        "context_token": context_token,
        "file_path": result["file_path"],
    }


def print_auto_discovery_help() -> None:
    print("自动模式会在以下位置查找微信账号配置:")
    for platform, path in candidate_account_paths():
        print(f"  - {platform}: {path}")
