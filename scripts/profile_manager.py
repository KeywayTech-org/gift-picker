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
import time
import html
import io
from datetime import date
from pathlib import Path

# Windows 编码兼容：确保 stdin/stdout 使用 UTF-8
if sys.platform == "win32":
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROFILE_DIR = Path(os.environ.get("GIFT_PICKER_HOME", str(Path.home() / ".workbuddy" / "gift-picker" / "profiles")))
SCHEMA_VERSION = 1

# list 字段：追加合并（append），其余字段整体替换
APPEND_LIST_FIELDS = {"gift_history"}
# list 字段：追加合并（extend）
EXTEND_LIST_FIELDS = {"colors_like", "colors_dislike", "allergies", "diet_taboo",
                       "owned_items", "hobbies", "skincare_brands", "makeup_brands"}

MAX_NICKNAME_LENGTH = 50

# 画像完整度权重（见 references/profile-schema.md）
COMPLETENESS_WEIGHTS = {
    "nickname": 15, "relationship": 15, "relationship_stage": 15, "allergies": 15,
    "colors_like": 10, "style": 10, "hobbies": 10, "skincare_brands": 10,
    "scent": 5, "sizes": 5, "makeup_brands": 5, "owned_items": 5,
}

# 关系阶段中文映射：优先从 references/stages.json 读取（单一真相源），
# 文件缺失/损坏时回退到内置字典，保证脚本独立可用。
_STAGES_JSON = Path(__file__).parent.parent / "references" / "stages.json"


def _load_stage_cn() -> dict:
    try:
        data = json.loads(_STAGES_JSON.read_text(encoding="utf-8"))
        return {s["key"]: s["cn"] for s in data.get("stages", [])}
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return {
            "pursuit": "追求期", "honeymoon": "热恋期", "stable": "稳定期",
            "newlywed": "新婚期", "anniversary": "周年纪念", "longterm": "长期陪伴",
        }


STAGE_CN = _load_stage_cn()


def _auto_nickname(patch: dict) -> str:
    """根据画像关键词自动生成昵称。
    格式：[关系阶段] + [风格/爱好/颜色关键词]
    组合优先级：style > hobbies > colors_like
    """
    parts = []

    # 1. 关系阶段前缀
    stage = patch.get("relationship_stage", "")
    if stage and stage in STAGE_CN:
        parts.append(STAGE_CN[stage])

    # 2. 核心关键词（优先 style）
    style = patch.get("style", "")
    if style and isinstance(style, str) and style.strip():
        # 取第一个风格词
        word = style.strip().split()[0] if style.strip() else ""
        if word:
            parts.append(word)

    # 3. 如果还没有关键词，用爱好或颜色补充
    if len(parts) <= 1:
        hobbies = patch.get("hobbies", [])
        if hobbies and isinstance(hobbies, list) and len(hobbies) > 0:
            hobby = hobbies[0] if isinstance(hobbies[0], str) else str(hobbies[0])
            parts.append(hobby[:4])

    if len(parts) <= 1:
        colors = patch.get("colors_like", [])
        if colors and isinstance(colors, list) and len(colors) > 0:
            color = colors[0] if isinstance(colors[0], str) else str(colors[0])
            parts.append(color)

    # 4. 兜底
    if len(parts) <= (1 if stage and stage in STAGE_CN else 0):
        import random
        adjectives = ["小可爱", "小仙女", "宝贝", "甜心"]
        suffix = patch.get("nickname", "") or patch.get("name", "") or "她"
        parts.append(random.choice(adjectives))
        if suffix and isinstance(suffix, str):
            parts.append(suffix[:4])

    nickname = "".join(p for p in parts if p)
    # 确保长度和合法性
    nickname = _sanitize_nickname(nickname)
    if not nickname:
        nickname = "新画像"
    return nickname


def _sanitize_nickname(nickname: str) -> str:
    """清理昵称中的非法字符。"""
    safe = "".join(c for c in nickname if c not in '\\/:*?"<>|').strip()
    return safe[:MAX_NICKNAME_LENGTH]


def _path(nickname: str) -> Path:
    safe = "".join(c for c in nickname if c not in '\\/:*?"<>|').strip()
    if not safe:
        sys.exit("错误：昵称不合法")
    if ".." in safe or safe.startswith("."):
        sys.exit("错误：昵称不合法")
    if len(safe) > MAX_NICKNAME_LENGTH:
        sys.exit(f"错误：昵称过长（最多 {MAX_NICKNAME_LENGTH} 字符）")
    return PROFILE_DIR / f"{safe}.json"


def _load(p: Path, corrupt_tolerant: bool = False) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        if not corrupt_tolerant:
            sys.exit(f"错误：{p} 内容损坏，请人工检查后再操作（未做任何修改）")
        # 损坏容错模式：备份原文件 + 返回空画像，避免一个坏文件阻塞整个 list
        backup = p.with_suffix(f".json.corrupt.{int(time.time())}")
        try:
            p.rename(backup)
        except OSError:
            pass
        print(f"⚠️  画像 {p.stem} 损坏，已备份到 {backup}，本次按空画像处理")
        return {}


def _atomic_write(p: Path, data: dict, max_retries: int = 3):
    """原子写入：写临时文件 + rename，避免写入中断导致数据损坏。
    Windows 下偶发 PermissionError（文件被占用），按指数退避重试后再抛。"""
    last_err = None
    for attempt in range(max_retries):
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(p.parent), suffix=".json.tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(p))
            return
        except PermissionError as e:
            last_err = e
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            if attempt == max_retries - 1:
                raise
            time.sleep(0.5 * (attempt + 1))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    if last_err:
        raise last_err


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
            if k == "gift_history":
                _sanitize_gift_history(base[k])
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


def _is_filled(v) -> bool:
    """判断字段是否已填（非空 list/dict/str 视为已填，None/空视为未填）。"""
    if v is None:
        return False
    if isinstance(v, (list, dict, str)) and len(v) == 0:
        return False
    return True


def _completeness(data: dict) -> int:
    """计算画像完整度（0-100），权重见 COMPLETENESS_WEIGHTS。"""
    return sum(w for k, w in COMPLETENESS_WEIGHTS.items() if _is_filled(data.get(k)))


def cmd_completeness(args):
    p = _path(args.nickname)
    if not p.exists():
        sys.exit(f"未找到画像：{args.nickname}")
    data = _load(p)
    score = _completeness(data)
    print(f"COMPLETENESS:{score}")
    print(f"画像完整度：{score}%")
    missing = [k for k, w in COMPLETENESS_WEIGHTS.items() if w > 0 and not _is_filled(data.get(k))]
    if missing:
        print(f"缺失字段：{', '.join(missing)}")


VALID_FEEDBACK = {"positive", "neutral", "negative"}


def _sanitize_gift_history(entries):
    """将 gift_history 中非法的 feedback 值规范为 neutral，避免污染画像。"""
    for e in entries:
        if isinstance(e, dict):
            fb = e.get("feedback")
            if fb not in VALID_FEEDBACK:
                print(f"⚠️  gift_history.feedback 值非法（{fb!r}），已规范为 neutral")
                e["feedback"] = "neutral"


def _memory_path() -> Path:
    """memory.json 路径：环境变量 GIFT_PICKER_MEMORY_PATH 优先，否则为 skill 根目录。
    用 realpath 解析 symlink，确保通过软链加载 skill 时仍写入真实根目录。"""
    env = os.environ.get("GIFT_PICKER_MEMORY_PATH")
    if env:
        return Path(env)
    skill_dir = Path(os.path.realpath(__file__)).parent.parent
    return skill_dir / "memory.json"


def cmd_list(_args):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    names = sorted(p.stem for p in PROFILE_DIR.glob("*.json"))
    # 机器可解析行（首行，供 Agent 程序化解析），其余行为人类可读详情
    print(f"NICKNAMES:{','.join(names)}")
    if not names:
        print("（暂无画像）")
        return
    for n in names:
        d = _load(PROFILE_DIR / f"{n}.json", corrupt_tolerant=True)
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

    # 自动生成昵称（当 --auto-name 或昵称为空时）
    auto_nickname = args.auto_name if hasattr(args, 'auto_name') and args.auto_name else (not args.nickname or args.nickname == "auto")
    if auto_nickname:
        nickname = _auto_nickname(patch)
        print(f"🤖 自动生成昵称：{nickname}")
        print(f"NICKNAME_SUGGESTED:{nickname}")
    else:
        nickname = args.nickname

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    p = _path(nickname)

    # 写入前备份
    backup = p.with_suffix(".json.bak") if p.exists() else None
    if backup:
        try:
            backup.write_bytes(p.read_bytes())
        except OSError as e:
            sys.exit(f"错误：备份失败：{e}")

    # 记录临时 JSON 文件路径（用于成功后清理）
    json_file_path = args.json_file if hasattr(args, 'json_file') and args.json_file else None

    try:
        data = _load(p)
        created = not p.exists()
        data = _deep_merge(data, patch)
        if isinstance(data.get("gift_history"), list):
            _sanitize_gift_history(data["gift_history"])
        data["nickname"] = nickname
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

    # 新建画像时清理会话记忆，确保不掺杂之前信息
    if created:
        memory_file = _memory_path()
        if memory_file.exists():
            try:
                memory_file.unlink()
                print(f"🧹 已清理之前的会话记忆，确保新画像信息全新")
            except OSError:
                pass

    # 成功后清理临时 JSON 文件
    if json_file_path:
        tmp = Path(json_file_path)
        if tmp.exists():
            try:
                tmp.unlink()
                print(f"🧹 已清理临时数据文件")
            except OSError:
                pass

    print(f"{'已创建' if created else '已更新'}画像：{nickname}")


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
        changed = False
        # 迁移字段值命名：long_term -> longterm（与 STAGE_CN / 各 reference 文档统一）
        if data.get("relationship_stage") == "long_term":
            data["relationship_stage"] = "longterm"
            changed = True
        if "schema_version" not in data:
            data = _ensure_schema(data)
            changed = True
        if changed:
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
    s = sub.add_parser("set")
    s.add_argument("nickname", nargs="?", default="auto", help="画像昵称（auto=自动生成）")
    s.add_argument("--json"); s.add_argument("--json-file")
    s.add_argument("--auto-name", action="store_true", help="自动根据关键词生成昵称")
    s.add_argument("--stdin", action="store_true", help="从标准输入读取 JSON")
    d = sub.add_parser("delete"); d.add_argument("nickname"); d.add_argument("--confirm", action="store_true")
    sub.add_parser("migrate", help="迁移旧版画像到当前 schema")
    c = sub.add_parser("completeness", help="计算画像完整度（0-100）")
    c.add_argument("nickname")
    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        sys.exit(1)
    {"list": cmd_list, "get": cmd_get, "set": cmd_set, "delete": cmd_delete,
     "migrate": cmd_migrate, "completeness": cmd_completeness}[args.cmd](args)


if __name__ == "__main__":
    main()