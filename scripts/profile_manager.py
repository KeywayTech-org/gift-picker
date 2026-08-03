#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""恋人画像管理：list / get / set(增量合并) / delete
存储位置：~/.workbuddy/gift-picker/profiles/<昵称>.json

用法：
  python profile_manager.py list
  python profile_manager.py get <昵称>
  python profile_manager.py set <昵称> --json '{"colors_like":["白色"]}'
  python profile_manager.py set <昵称> --json-file patch.json
  python profile_manager.py delete <昵称> --confirm
  python profile_manager.py migrate  # 迁移旧版画像
"""
import argparse
import json
import os
import sys
import tempfile
import html
from datetime import date
from pathlib import Path

PROFILE_DIR = Path(os.environ.get("GIFT_PICKER_HOME", str(Path.home() / ".workbuddy" / "gift-picker" / "profiles")))
SCHEMA_VERSION = 1

# list 字段：追加合并（append），其余字段整体替换
APPEND_LIST_FIELDS = {"gift_history"}
# list 字段：追加合并（extend）
EXTEND_LIST_FIELDS = {"colors_like", "colors_dislike", "allergies", "diet_taboo",
                       "owned_items", "hobbies", "skincare_brands", "makeup_brands"}

MAX_NICKNAME_LENGTH = 50


def _path(nickname: str) -> Path:
    safe = "".join(c for c in nickname if c not in '\\/:*?"<>|').strip()
    if not safe:
        sys.exit("错误：昵称不合法")
    if ".." in safe or safe.startswith("."):
        sys.exit("错误：昵称不合法")
    if len(safe) > MAX_NICKNAME_LENGTH:
        sys.exit(f"错误：昵称过长（最多 {MAX_NICKNAME_LENGTH} 字符）")
    return PROFILE_DIR / f"{safe}.json"


def _load(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        sys.exit(f"错误：{p} 内容损坏，请人工检查后再操作（未做任何修改）")


def _atomic_write(p: Path, data: dict):
    """原子写入：写临时文件 + rename，避免写入中断导致数据损坏。"""
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(p.parent), suffix=".json.tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, str(p))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _deep_merge(base: dict, patch: dict) -> dict:
    """dict 递归合并；list 特殊规则：
    - APPEND_LIST_FIELDS（gift_history）：追加
    - EXTEND_LIST_FIELDS：拼接合并（去重）
    - 其他 list 字段：整体替换
    - null 表示删除该键
    """
    for k, v in patch.items():
        if v is None:
            base.pop(k, None)
        elif isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        elif k in APPEND_LIST_FIELDS and isinstance(v, list) and isinstance(base.get(k), list):
            base[k].extend(v)
        elif k in EXTEND_LIST_FIELDS and isinstance(v, list) and isinstance(base.get(k), list):
            base[k].extend(item for item in v if item not in base[k])
        else:
            base[k] = v
    return base


def _ensure_schema(data: dict) -> dict:
    """确保画像数据包含 schema_version，缺失则视为 v0 进行迁移。"""
    version = data.get("schema_version", 0)
    if version == 0:
        data["schema_version"] = SCHEMA_VERSION
    return data


def _escape_text(text: str) -> str:
    """HTML 转义，防止 XSS。"""
    return html.escape(str(text))


def cmd_list(_args):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    names = sorted(p.stem for p in PROFILE_DIR.glob("*.json"))
    if not names:
        print("（暂无画像）")
        return
    for n in names:
        d = _load(PROFILE_DIR / f"{n}.json")
        rel = _escape_text(d.get("relationship", "?"))
        updated = _escape_text(str(d.get("updated_at", "?")))
        print(f"- {n}  (关系: {rel}, 更新: {updated})")


def cmd_get(args):
    p = _path(args.nickname)
    if not p.exists():
        sys.exit(f"未找到画像：{args.nickname}（用 set 创建）")
    data = _ensure_schema(_load(p))
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_set(args):
    if args.json:
        try:
            patch = json.loads(args.json)
        except json.JSONDecodeError as e:
            sys.exit(f"错误：--json 不是合法 JSON：{e}")
    elif args.json_file:
        try:
            patch = json.loads(Path(args.json_file).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            sys.exit(f"错误：--json-file 读取失败：{e}")
    elif args.stdin:
        # 从标准输入读取 JSON（推荐用于 Codex，避免命令行引号问题）
        try:
            patch = json.loads(sys.stdin.read())
        except json.JSONDecodeError as e:
            sys.exit(f"错误：stdin 不是合法 JSON：{e}")
    else:
        sys.exit("错误：需要 --json 或 --json-file 或 --stdin")
    if not isinstance(patch, dict):
        sys.exit("错误：patch 必须是 JSON 对象")

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    p = _path(args.nickname)

    # 写入前备份
    backup = p.with_suffix(".json.bak") if p.exists() else None
    if backup:
        try:
            backup.write_bytes(p.read_bytes())
        except OSError as e:
            sys.exit(f"错误：备份失败：{e}")

    try:
        data = _load(p)
        created = not p.exists()
        data = _deep_merge(data, patch)
        data["nickname"] = args.nickname
        data["schema_version"] = SCHEMA_VERSION
        data["updated_at"] = date.today().isoformat()
        _atomic_write(p, data)
    except Exception:
        # 恢复备份
        if backup and backup.exists():
            try:
                backup.replace(p)
            except OSError:
                pass
        raise

    # 成功后清理备份
    if backup and backup.exists():
        try:
            backup.unlink()
        except OSError:
            pass

    print(f"{'已创建' if created else '已更新'}画像：{p}")


def cmd_delete(args):
    p = _path(args.nickname)
    if not p.exists():
        sys.exit(f"未找到画像：{args.nickname}")
    if not args.confirm:
        sys.exit("删除为不可逆操作，请加 --confirm 确认")
    p.unlink()
    print(f"已删除画像：{args.nickname}")


def cmd_migrate(_args):
    """迁移旧版画像，确保 schema_version 字段存在。"""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    names = sorted(p.stem for p in PROFILE_DIR.glob("*.json"))
    if not names:
        print("（暂无画像需要迁移）")
        return
    migrated = 0
    for n in names:
        p = PROFILE_DIR / f"{n}.json"
        data = _load(p)
        if "schema_version" not in data:
            data = _ensure_schema(data)
            _atomic_write(p, data)
            migrated += 1
            print(f"  已迁移：{n}")
    if migrated:
        print(f"迁移完成：{migrated} 个画像已更新至 schema v{SCHEMA_VERSION}")
    else:
        print("（所有画像已是最新版本）")


def main():
    ap = argparse.ArgumentParser(description="恋人画像管理")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list")
    g = sub.add_parser("get"); g.add_argument("nickname")
    s = sub.add_parser("set"); s.add_argument("nickname")
    s.add_argument("--json"); s.add_argument("--json-file")
    d = sub.add_parser("delete"); d.add_argument("nickname"); d.add_argument("--confirm", action="store_true")
    sub.add_parser("migrate", help="迁移旧版画像到当前 schema")
    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        sys.exit(1)
    {"list": cmd_list, "get": cmd_get, "set": cmd_set, "delete": cmd_delete, "migrate": cmd_migrate}[args.cmd](args)


if __name__ == "__main__":
    main()