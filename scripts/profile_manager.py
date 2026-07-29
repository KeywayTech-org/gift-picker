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
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

PROFILE_DIR = Path.home() / ".workbuddy" / "gift-picker" / "profiles"


def _path(nickname: str) -> Path:
    safe = "".join(c for c in nickname if c not in '\\/:*?"<>|').strip()
    if not safe:
        sys.exit("错误：昵称不合法")
    return PROFILE_DIR / f"{safe}.json"


def _load(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        sys.exit(f"错误：{p} 内容损坏，请人工检查后再操作（未做任何修改）")


def _deep_merge(base: dict, patch: dict) -> dict:
    """dict 递归合并；list 特殊规则：gift_history 追加，其余整体替换；null 表示删除该键。"""
    for k, v in patch.items():
        if v is None:
            base.pop(k, None)
        elif isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        elif k == "gift_history" and isinstance(v, list) and isinstance(base.get(k), list):
            base[k].extend(v)
        else:
            base[k] = v
    return base


def cmd_list(_args):
    if not PROFILE_DIR.exists():
        print("（暂无画像）")
        return
    names = sorted(p.stem for p in PROFILE_DIR.glob("*.json"))
    if not names:
        print("（暂无画像）")
        return
    for n in names:
        d = _load(PROFILE_DIR / f"{n}.json")
        print(f"- {n}  (关系: {d.get('relationship', '?')}, 更新: {d.get('updated_at', '?')})")


def cmd_get(args):
    p = _path(args.nickname)
    if not p.exists():
        sys.exit(f"未找到画像：{args.nickname}（用 set 创建）")
    print(json.dumps(_load(p), ensure_ascii=False, indent=2))


def cmd_set(args):
    if args.json:
        try:
            patch = json.loads(args.json)
        except json.JSONDecodeError as e:
            sys.exit(f"错误：--json 不是合法 JSON：{e}")
    elif args.json_file:
        patch = json.loads(Path(args.json_file).read_text(encoding="utf-8"))
    else:
        sys.exit("错误：需要 --json 或 --json-file")
    if not isinstance(patch, dict):
        sys.exit("错误：patch 必须是 JSON 对象")

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    p = _path(args.nickname)
    data = _load(p)
    created = not p.exists()
    data = _deep_merge(data, patch)
    data["nickname"] = args.nickname
    data["updated_at"] = date.today().isoformat()
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{'已创建' if created else '已更新'}画像：{p}")


def cmd_delete(args):
    p = _path(args.nickname)
    if not p.exists():
        sys.exit(f"未找到画像：{args.nickname}")
    if not args.confirm:
        sys.exit("删除为不可逆操作，请加 --confirm 确认")
    p.unlink()
    print(f"已删除画像：{args.nickname}")


def main():
    ap = argparse.ArgumentParser(description="恋人画像管理")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    g = sub.add_parser("get"); g.add_argument("nickname")
    s = sub.add_parser("set"); s.add_argument("nickname")
    s.add_argument("--json"); s.add_argument("--json-file")
    d = sub.add_parser("delete"); d.add_argument("nickname"); d.add_argument("--confirm", action="store_true")
    args = ap.parse_args()
    {"list": cmd_list, "get": cmd_get, "set": cmd_set, "delete": cmd_delete}[args.cmd](args)


if __name__ == "__main__":
    main()
