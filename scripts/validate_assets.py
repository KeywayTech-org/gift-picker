"""Read-only validation for gift-picker's static assets and contracts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]


def load(name: str) -> dict:
    path = ROOT / "assets" / name
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{name}: root must be an object")
    return value


def require_keys(value: dict, keys: set[str], label: str) -> None:
    missing = sorted(keys - value.keys())
    if missing:
        raise ValueError(f"{label}: missing keys: {', '.join(missing)}")


def validate_catalog(name: str, item_key: str, required_item_keys: set[str]) -> None:
    data = load(name)
    require_keys(data, {"version", "updated", item_key}, name)
    items = data[item_key]
    if not isinstance(items, list) or not items:
        raise ValueError(f"{name}: {item_key} must be a non-empty list")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"{name}: {item_key}[{index}] must be an object")
        require_keys(item, required_item_keys, f"{name}:{item_key}[{index}]")


def validate_category_links() -> None:
    data = load("beauty-categories.json")
    ids = {item["id"] for item in data["categories"]}
    for index, item in enumerate(data["categories"]):
        target = item.get("downgrade_to")
        if target is not None and target not in ids:
            raise ValueError(f"beauty-categories.json:categories[{index}]: dangling downgrade_to={target}")


def validate_dependency_files() -> None:
    data = load("dependencies.json")
    for index, item in enumerate(data["data_files"]):
        path = ROOT / item["path"]
        if not path.is_file():
            raise ValueError(f"dependencies.json:data_files[{index}]: missing file {item['path']}")
    for group in ("mcp_servers", "skills"):
        for index, item in enumerate(data[group]):
            usage = item.get("usage_in_skill")
            if not isinstance(usage, dict) or not usage:
                raise ValueError(f"dependencies.json:{group}[{index}]: usage_in_skill must be a non-empty object")
            if any(re.fullmatch(r"step_\d+(\.\d+)?", key) for key in usage):
                raise ValueError(f"dependencies.json:{group}[{index}]: stale numeric workflow step id")


def validate_references_and_secrets() -> None:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    context = ROOT / "context.md"
    if context.exists():
        skill += "\n" + context.read_text(encoding="utf-8")
    for reference in re.findall(r"(?<!https://)(?<!http://)(?:assets|scripts|references)/[A-Za-z0-9_.-]+", skill):
        if not (ROOT / reference).is_file():
            raise ValueError(f"missing referenced file: {reference}")
    secret_patterns = (
        r"(?:sk|pk)-[A-Za-z0-9_-]{16,}",
        r"(?:api[_-]?key|token|password)\s*[:=]\s*['\"][^'\"]+['\"]",
    )
    for pattern in secret_patterns:
        if re.search(pattern, skill, flags=re.IGNORECASE):
            raise ValueError(f"possible secret found in documentation: {pattern}")


def validate_dry_run_contract() -> None:
    evidence = {
        "source_url": "https://example.invalid/post",
        "source_type": "post",
        "observed_at": "2026-08-07T00:00:00Z",
    }
    final_product = {
        "url": "https://detail.tmall.com/item.htm?id=1",
        "evidence_urls": [evidence["source_url"]],
        "source_type": "product_detail",
        "observed_at": evidence["observed_at"],
    }
    require_keys(evidence, {"source_url", "source_type", "observed_at"}, "dry-run:evidence")
    require_keys(final_product, {"url", "evidence_urls", "source_type", "observed_at"}, "dry-run:final_product")
    if not final_product["evidence_urls"]:
        raise ValueError("dry-run:final_product must retain evidence URLs")


def validate_dependencies() -> None:
    data = load("dependencies.json")
    require_keys(data, {"version", "updated", "mcp_servers", "skills", "python_deps", "data_files"}, "dependencies.json")
    for group in ("mcp_servers", "skills"):
        for index, item in enumerate(data[group]):
            require_keys(item, {"name", "source_url", "api_key_required", "paid"}, f"dependencies.json:{group}[{index}]")
            parsed = urlparse(item["source_url"])
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"dependencies.json:{group}[{index}]: invalid source_url")
            if item["api_key_required"] or item["paid"]:
                raise ValueError(f"dependencies.json:{group}[{index}]: dependency is not free/keyless")


def main() -> int:
    validate_catalog("beauty-brands.json", "brands", {"name", "tier"})
    validate_catalog("beauty-categories.json", "categories", {"id", "name", "tier"})
    validate_category_links()
    validate_dependencies()
    validate_dependency_files()
    validate_references_and_secrets()
    validate_dry_run_contract()
    print("PASS: assets, references, secret scan, and dry-run contract are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
