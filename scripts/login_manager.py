#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""登录态管理：login / check / check_and_login / list / clear

基于 Playwright 的持久化登录态管理。
存储位置：~/.workbuddy/gift-picker/sessions/<channel>.json

用法：
  python login_manager.py list                           # 查看所有已保存的登录态
  python login_manager.py login taobao                   # 启动浏览器登录淘宝
  python login_manager.py check taobao                    # 检查淘宝登录态是否有效
  python login_manager.py check_and_login taobao          # 检查并自动跳转登录（推荐）
  python login_manager.py clear taobao                    # 清除淘宝登录态
  python login_manager.py login taobao --timeout 300       # 自定义登录等待超时（秒）
  python login_manager.py check taobao --url https://...   # 自定义校验页面
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from _compat import ensure_utf8_stdio, atomic_write

# Windows 编码兼容：确保 stdin/stdout 使用 UTF-8（与 profile_manager.py 共用 _compat）
ensure_utf8_stdio()

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("❌ 未安装 Playwright。请运行：pip install playwright && playwright install chromium")
    print("   或使用 '跳过登录，用公开数据' 模式继续（置信度低）")
    sys.exit(2)

SESSION_DIR = Path(os.environ.get(
    "GIFT_PICKER_SESSION_HOME",
    str(Path(os.environ.get("GIFT_PICKER_HOME", str(Path.home() / ".workbuddy" / "gift-picker"))) / "sessions")
))

# 渠道配置外置到 assets/channels.json（修改渠道信号/新增渠道无需改代码）
CHANNELS_JSON = Path(__file__).parent.parent / "assets" / "channels.json"
try:
    with open(CHANNELS_JSON, encoding="utf-8") as _f:
        CHANNEL_CONFIG = json.load(_f)
except (OSError, json.JSONDecodeError) as _e:
    print(f"❌ 读取渠道配置失败：{CHANNELS_JSON}（{_e}）")
    sys.exit(1)

DEFAULT_TIMEOUT = 300  # 登录等待超时（秒）
CHECK_TIMEOUT = 15000  # 单次检查超时（毫秒）


def _session_path(channel: str) -> Path:
    """获取存储态文件路径。"""
    return SESSION_DIR / f"{channel}.json"


def _save_storage_state(context, channel: str):
    """保存浏览器存储态（cookies + localStorage）。"""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    state = context.storage_state()
    state["_meta"] = {
        "channel": channel,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "version": 1,
    }
    path = _session_path(channel)
    atomic_write(path, state)
    return path


def _load_storage_state(channel: str) -> Optional[dict]:
    """加载已保存的存储态。"""
    path = _session_path(channel)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _detect_signal(page, signals: list) -> dict:
    """检测页面是否满足一组信号条件。"""
    for sig in signals:
        sig_type = sig.get("type", "")
        value = sig.get("value", "")
        selector = sig.get("selector", "body")

        try:
            if sig_type == "url_contains":
                if value in page.url:
                    return {"matched": True, "signal": sig}
            elif sig_type == "url_not_contains":
                if value not in page.url:
                    return {"matched": True, "signal": sig}
            elif sig_type == "selector_exists":
                if page.locator(selector).count() > 0:
                    return {"matched": True, "signal": sig}
            elif sig_type == "text_contains":
                el = page.locator(selector).first
                if el.count() > 0 and value in el.inner_text(timeout=2000):
                    return {"matched": True, "signal": sig}
        except Exception:
            continue
    return {"matched": False, "signal": None}


def _count_matched_signals(page, signals: list) -> int:
    """统计匹配的信号数量。"""
    count = 0
    for sig in signals:
        sig_type = sig.get("type", "")
        value = sig.get("value", "")
        selector = sig.get("selector", "body")

        try:
            if sig_type == "url_contains":
                if value in page.url:
                    count += 1
            elif sig_type == "url_not_contains":
                if value not in page.url:
                    count += 1
            elif sig_type == "selector_exists":
                if page.locator(selector).count() > 0:
                    count += 1
            elif sig_type == "text_contains":
                el = page.locator(selector).first
                if el.count() > 0 and value in el.inner_text(timeout=2000):
                    count += 1
        except Exception:
            continue
    return count


def _check_login_status(page, channel: str) -> dict:
    """检查指定渠道的登录状态。
    
    逻辑改进：
    1. 先检查失效信号（fail_signals），任一匹配则返回 expired
    2. 再检查成功信号（success_signals），需要至少 2 个信号匹配才算 ok
    3. 都不匹配则返回 unknown
    """
    config = CHANNEL_CONFIG.get(channel)
    if not config:
        return {"status": "unknown", "reason": f"未知渠道：{channel}"}

    # 先检查失效信号（任一匹配即失效）
    fail_result = _detect_signal(page, config["fail_signals"])
    if fail_result["matched"]:
        return {"status": "expired", "reason": f"检测到失效信号：{fail_result['signal']}"}

    # 再检查成功信号（需要至少2个匹配才视为登录成功）
    success_count = _count_matched_signals(page, config["success_signals"])
    if success_count >= 2:
        return {"status": "ok", "reason": f"登录态有效（{success_count}个成功信号匹配）"}

    return {"status": "unknown", "reason": f"无法判断登录状态（仅{success_count}个成功信号匹配）"}


def _acquire_session_lock(channel: str, timeout: int = 30):
    """跨平台互斥锁（免依赖）：防止两进程同时读写同一渠道 session 导致 Profile 损坏。
    基于 msvcrt.locking(Windows) / fcntl.flock(Unix) 对 .lock 文件加独占锁。
    OS 会在进程退出时自动释放锁，因此崩溃不会造成永久死锁。"""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = SESSION_DIR / f"{channel}.lock"
    deadline = time.time() + timeout
    while True:
        f = open(lock_path, "w")
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f
        except (OSError, IOError):
            try:
                f.close()
            except Exception:
                pass
            if time.time() >= deadline:
                sys.exit(f"⚠️  {channel} 渠道正在被其他进程操作，等待 {timeout}s 超时，已中止本次操作。")
            print(f"⚠️  {channel} 渠道正被其他进程占用，等待锁释放（最多 {timeout}s）...")
            time.sleep(1)


def _release_session_lock(f):
    """释放 _acquire_session_lock 获取的锁并关闭文件。"""
    if f is None:
        return
    try:
        if sys.platform == "win32":
            import msvcrt
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            except (OSError, IOError):
                pass
        else:
            import fcntl
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except (OSError, IOError):
                pass
    finally:
        try:
            f.close()
        except Exception:
            pass


def cmd_login(args, hold_lock: bool = False):
    """启动浏览器让用户手动登录，然后保存登录态。

    登录成功后会输出：
    LOGIN_STATUS:OK
    LOGIN_CHANNEL:<channel>
    LOGIN_SAVED:<path>
    """
    channel = args.channel
    if channel not in CHANNEL_CONFIG:
        sys.exit(f"错误：未知渠道 '{channel}'。支持的渠道：{', '.join(CHANNEL_CONFIG.keys())}")

    config = CHANNEL_CONFIG[channel]
    timeout = args.timeout or DEFAULT_TIMEOUT
    state_path = _session_path(channel)

    lock = None if hold_lock else _acquire_session_lock(channel)
    try:
        print(f"🌐 即将打开 {config['name']} 登录页...")
        print(f"⏰ 请在 {timeout} 秒内完成登录（扫码/账号密码）")
        print(f"💾 登录成功后将自动保存状态到：{state_path}")
        print(f"LOGIN_STATUS:PENDING")

        try:
            with sync_playwright() as p:
                # 使用持久化上下文，避免每次重新登录
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=str(SESSION_DIR / f"{channel}_profile"),
                    headless=False,
                    viewport={"width": 1280, "height": 800},
                )

                page = browser.pages[0] if browser.pages else browser.new_page()

                try:
                    page.goto(config["login_url"], wait_until="domcontentloaded", timeout=30000)
                    print(f"📄 页面已打开，请在浏览器中完成登录...")
                except PlaywrightTimeout:
                    print(f"⚠️  页面加载超时，但浏览器已打开，请继续登录...")

                # 等待登录成功
                deadline = time.time() + timeout
                checked = 0
                last_status = None

                while time.time() < deadline:
                    checked += 1
                    time.sleep(min(1 + checked * 0.5, 3))

                    status = _check_login_status(page, channel)
                    last_status = status
                    remaining = max(0, int(deadline - time.time()))

                    if status["status"] == "ok":
                        # 登录成功，保存状态
                        saved = _save_storage_state(browser, channel)
                        print(f"\n✅ 登录成功！{config['name']}登录态已保存到：{saved}")
                        print(f"   保存时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

                        # 输出状态标记，供 Codex 解析
                        print(f"LOGIN_STATUS:OK")
                        print(f"LOGIN_CHANNEL:{channel}")
                        print(f"LOGIN_SAVED:{saved}")

                        # 如果需要验证页面（如购物车），额外检测
                        if config.get("verify_urls"):
                            for verify_url in config["verify_urls"]:
                                try:
                                    page.goto(verify_url, wait_until="domcontentloaded", timeout=10000)
                                    v_status = _check_login_status(page, channel)
                                    if v_status["status"] != "ok":
                                        print(f"   ⚠️  验证页面 {verify_url} 可能需要重新登录：{v_status['reason']}")
                                except Exception:
                                    pass

                        print(f"💡 下次使用时将自动复用此登录态，无需重新登录。")
                        return
                    else:
                        if checked % 5 == 0:
                            print(f"   ⏳ 等待登录中... ({remaining}秒剩余)")

                # 超时
                if last_status and last_status["status"] != "ok":
                    print(f"\n⏰ 登录等待超时（{timeout}秒）。")
                    print(f"LOGIN_STATUS:TIMEOUT")
                    print(f"   最后检测状态：{last_status['status']} - {last_status['reason']}")
                    print(f"💡 如果已完成登录但未保存，请使用 --timeout 参数增加等待时间，或重新执行登录。")

        except Exception as e:
            print(f"\n❌ 登录过程出错：{e}")
            print(f"LOGIN_STATUS:ERROR")
            sys.exit(1)
    finally:
        _release_session_lock(lock)


def cmd_check(args):
    """检查指定渠道的登录态是否有效。
    
    检查完成后会输出：
    CHECK_STATUS:OK 或 CHECK_STATUS:EXPIRED 或 CHECK_STATUS:NO_STATE
    """
    channel = args.channel
    if channel not in CHANNEL_CONFIG:
        sys.exit(f"错误：未知渠道 '{channel}'。支持的渠道：{', '.join(CHANNEL_CONFIG.keys())}")

    config = CHANNEL_CONFIG[channel]
    check_url = args.url or config.get("check_url", config["login_url"])
    state_path = _session_path(channel)

    lock = _acquire_session_lock(channel)
    try:
        state = _load_storage_state(channel)
        if state is None:
            print(f"❌ 未找到 {config['name']} 的登录态，请先执行 login 命令。")
            print(f"CHECK_STATUS:NO_STATE")
            return

        # 显示保存时间
        meta = state.get("_meta", {})
        saved_at = meta.get("saved_at", "未知")
        print(f"📋 检查 {config['name']} 登录态...")
        print(f"   存储时间：{saved_at}")

        try:
            with sync_playwright() as p:
                profile_dir = SESSION_DIR / f"{channel}_profile"
                page = None
                browser = None
                context = None

                if profile_dir.exists():
                    # 方式1：使用持久化 Profile 目录（最可靠，含全部浏览器状态）
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=str(profile_dir),
                        headless=True,
                    )
                    page = context.pages[0] if context.pages else context.new_page()
                else:
                    # 方式2：使用 Storage State JSON 文件
                    browser = p.chromium.launch(headless=True)
                    if (state or {}).get("cookies"):
                        context = browser.new_context(storage_state=str(state_path))
                        page = context.new_page()
                    else:
                        page = browser.new_page()

                try:
                    page.goto(check_url, wait_until="domcontentloaded", timeout=CHECK_TIMEOUT)
                except PlaywrightTimeout:
                    print(f"⚠️  页面加载超时，但仍在检测登录态...")

                status = _check_login_status(page, channel)

                if status["status"] == "ok":
                    print(f"✅ {config['name']} 登录态有效！")
                    print(f"   原因：{status['reason']}")
                    print(f"   当前页面：{page.url}")
                    print(f"CHECK_STATUS:OK")
                elif status["status"] == "expired":
                    print(f"❌ {config['name']} 登录态已失效！")
                    print(f"   原因：{status['reason']}")
                    print(f"   请重新执行：python login_manager.py login {channel}")
                    print(f"CHECK_STATUS:EXPIRED")
                else:
                    print(f"⚠️  无法判断 {config['name']} 的登录状态。")
                    print(f"   原因：{status['reason']}")
                    print(f"   当前页面：{page.url}")
                    print(f"CHECK_STATUS:UNKNOWN")

                if context:
                    context.close()
                if browser:
                    browser.close()
        except Exception as e:
            print(f"❌ 检查过程出错：{e}")
            print(f"CHECK_STATUS:ERROR")
    finally:
        _release_session_lock(lock)


def cmd_check_and_login(args):
    """检查登录态，失效则自动打开浏览器跳转到登录页。
    
    流程：
    1. 如果没有登录态 → 直接打开浏览器让用户登录
    2. 如果有登录态 → 先用 headless 模式检查是否有效
    3. 如果有效 → 输出 CHECK_STATUS:OK 直接返回
    4. 如果失效 → 自动打开浏览器让用户登录
    
    最终输出：
    - CHECK_AND_LOGIN_STATUS:OK  （登录态有效，直接使用）
    - CHECK_AND_LOGIN_STATUS:LOGGED_IN  （已自动登录成功）
    - CHECK_AND_LOGIN_STATUS:TIMEOUT  （登录超时）
    - CHECK_AND_LOGIN_STATUS:ERROR  （出错）
    """
    channel = args.channel
    if channel not in CHANNEL_CONFIG:
        sys.exit(f"错误：未知渠道 '{channel}'。支持的渠道：{', '.join(CHANNEL_CONFIG.keys())}")

    config = CHANNEL_CONFIG[channel]
    timeout = args.timeout or DEFAULT_TIMEOUT
    state_path = _session_path(channel)

    lock = _acquire_session_lock(channel)
    try:
        state = _load_storage_state(channel)
        profile_dir = SESSION_DIR / f"{channel}_profile"

        # 情况1：没有存储态文件且没有profile目录 → 直接打开浏览器登录
        if state is None and not profile_dir.exists():
            print(f"❌ 未找到 {config['name']} 登录态，即将打开浏览器跳转到登录页...")
            print(f"CHECK_AND_LOGIN_STATUS:NEED_LOGIN")
            cmd_login(args, hold_lock=True)
            return

        # 情况2：有存储态 → 先检查是否有效
        print(f"📋 检查 {config['name']} 登录态...")

        login_needed = False

        try:
            with sync_playwright() as p:
                page = None
                browser = None
                context = None

                if profile_dir.exists():
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=str(profile_dir),
                        headless=True,
                    )
                    page = context.pages[0] if context.pages else context.new_page()
                else:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        storage_state=str(state_path) if (state or {}).get("cookies") else None
                    )
                    page = context.new_page()

                try:
                    page.goto(config["check_url"], wait_until="domcontentloaded", timeout=CHECK_TIMEOUT)
                except PlaywrightTimeout:
                    pass

                status = _check_login_status(page, channel)

                if status["status"] == "ok":
                    print(f"✅ {config['name']} 登录态有效，可直接使用！")
                    print(f"CHECK_AND_LOGIN_STATUS:OK")
                    if context:
                        context.close()
                    if browser:
                        browser.close()
                    return
                else:
                    print(f"⚠️  {config['name']} 登录态已失效或无法判断（{status['reason']}）")
                    print(f"🌐 即将打开 {config['name']} 登录页，请在浏览器中完成登录...")
                    print(f"CHECK_AND_LOGIN_STATUS:NEED_LOGIN")
                    login_needed = True

                if context:
                    context.close()
                if browser:
                    browser.close()
        except Exception as e:
            print(f"⚠️  检查过程出错：{e}")
            print(f"🌐 即将打开 {config['name']} 登录页，请在浏览器中完成登录...")
            print(f"CHECK_AND_LOGIN_STATUS:NEED_LOGIN")
            login_needed = True

        # 情况3：登录态失效 → 自动打开浏览器让用户登录
        if login_needed:
            cmd_login(args, hold_lock=True)
    finally:
        _release_session_lock(lock)


def cmd_list(_args):
    """列出所有已保存的登录态。"""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    states = []

    for state_file in SESSION_DIR.glob("*.json"):
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            meta = data.get("_meta", {})
            channel = meta.get("channel", state_file.stem)
            channel_name = CHANNEL_CONFIG.get(channel, {}).get("name", channel)
            saved_at = meta.get("saved_at", "未知")
            cookie_count = len(data.get("cookies", []))
            states.append({
                "channel": channel,
                "channel_name": channel_name,
                "saved_at": saved_at,
                "cookie_count": cookie_count,
            })
        except (json.JSONDecodeError, OSError):
            pass

    # 同时检查持久化 profile 目录
    for profile_dir in SESSION_DIR.glob("*_profile"):
        channel = profile_dir.stem.replace("_profile", "")
        if channel not in [s["channel"] for s in states]:
            channel_name = CHANNEL_CONFIG.get(channel, {}).get("name", channel)
            states.append({
                "channel": channel,
                "channel_name": channel_name,
                "saved_at": "（持久化 Profile）",
                "cookie_count": 0,
            })

    if not states:
        print("（暂无已保存的登录态）")
        return

    print(f"已保存 {len(states)} 个渠道的登录态：\n")
    for s in states:
        print(f"  {s['channel_name']} ({s['channel']})")
        print(f"    存储时间：{s['saved_at']}")
        if s["cookie_count"]:
            print(f"    Cookie 数量：{s['cookie_count']}")
        print()


def cmd_clear(args):
    """清除指定渠道的登录态。"""
    channel = args.channel
    if channel not in CHANNEL_CONFIG:
        sys.exit(f"错误：未知渠道 '{channel}'。支持的渠道：{', '.join(CHANNEL_CONFIG.keys())}")

    state_path = _session_path(channel)
    profile_dir = SESSION_DIR / f"{channel}_profile"

    cleared = False

    if state_path.exists():
        state_path.unlink()
        print(f"🗑️  已删除存储态文件：{state_path}")
        cleared = True

    if profile_dir.exists():
        import shutil
        try:
            shutil.rmtree(profile_dir)
            print(f"🗑️  已删除持久化 Profile 目录：{profile_dir}")
            cleared = True
        except OSError as e:
            print(f"⚠️  删除 Profile 目录失败：{e}")

    if not cleared:
        print(f"（{CHANNEL_CONFIG[channel]['name']} 没有已保存的登录态）")


def main():
    ap = argparse.ArgumentParser(
        description="登录态管理（基于 Playwright）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
支持的渠道：
  taobao        淘宝/天猫
  jd            京东
  xiaohongshu   小红书

推荐用法：
  check_and_login <channel>   自动检查+跳转登录（最便捷）

环境变量：
  GIFT_PICKER_HOME              存储根目录（默认 ~/.workbuddy/gift-picker）
  GIFT_PICKER_SESSION_HOME      登录态存储目录（默认 $GIFT_PICKER_HOME/sessions）
        """,
    )
    sub = ap.add_subparsers(dest="cmd")

    # list
    sub.add_parser("list", help="列出所有已保存的登录态")

    # login
    p_login = sub.add_parser("login", help="启动浏览器手动登录并保存状态")
    p_login.add_argument("channel", choices=list(CHANNEL_CONFIG.keys()),
                         help="要登录的渠道")
    p_login.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                         help=f"登录等待超时秒数（默认 {DEFAULT_TIMEOUT}）")

    # check
    p_check = sub.add_parser("check", help="检查登录态是否有效")
    p_check.add_argument("channel", choices=list(CHANNEL_CONFIG.keys()),
                         help="要检查的渠道")
    p_check.add_argument("--url", type=str, default=None,
                         help="自定义校验页面URL")

    # check_and_login
    p_cal = sub.add_parser("check_and_login", help="检查登录态，失效则自动打开浏览器跳转到登录页")
    p_cal.add_argument("channel", choices=list(CHANNEL_CONFIG.keys()),
                       help="要检查的渠道")
    p_cal.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                       help=f"登录等待超时秒数（默认 {DEFAULT_TIMEOUT}）")

    # clear
    p_clear = sub.add_parser("clear", help="清除已保存的登录态")
    p_clear.add_argument("channel", choices=list(CHANNEL_CONFIG.keys()),
                         help="要清除的渠道")
    p_clear.add_argument("--confirm", action="store_true",
                         help="确认删除")

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        sys.exit(1)

    handlers = {
        "list": cmd_list,
        "login": cmd_login,
        "check": cmd_check,
        "check_and_login": cmd_check_and_login,
        "clear": cmd_clear,
    }

    if args.cmd == "clear" and not args.confirm:
        sys.exit("清除登录态为不可逆操作，请加 --confirm 确认")

    handlers[args.cmd](args)


if __name__ == "__main__":
    main()
