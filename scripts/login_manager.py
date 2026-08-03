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

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

SESSION_DIR = Path(os.environ.get(
    "GIFT_PICKER_SESSION_HOME",
    str(Path(os.environ.get("GIFT_PICKER_HOME", str(Path.home() / ".workbuddy" / "gift-picker"))) / "sessions")
))

# 各渠道配置：登录页URL、登录成功检测规则、校验页面、风控信号
CHANNEL_CONFIG = {
    "taobao": {
        "name": "淘宝",
        "login_url": "https://login.taobao.com/member/signin.htm",
        "check_url": "https://www.taobao.com",
        "success_signals": [
            # 正向：任一满足即视为登录成功
            {"type": "url_not_contains", "value": "login.taobao.com"},
            {"type": "text_contains", "selector": "body", "value": "你好"},
            {"type": "selector_exists", "value": ".user-info"},
            {"type": "selector_exists", "value": ".nav-user-nick"},
        ],
        "fail_signals": [
            # 负向：任一满足视为登录失效
            {"type": "url_contains", "value": "login.taobao.com"},
            {"type": "text_contains", "selector": "body", "value": "请登录"},
            {"type": "selector_exists", "value": ".login-box"},
        ],
        "verify_urls": [
            "https://buy.taobao.com/auction/buy_now.htm",  # 立即购买
        ],
    },
    "jd": {
        "name": "京东",
        "login_url": "https://passport.jd.com/new/login.aspx",
        "check_url": "https://www.jd.com",
        "success_signals": [
            # 京东首页需要登录才能看到用户信息
            {"type": "selector_exists", "value": ".user-info"},
            {"type": "selector_exists", "value": ".ft-user-name"},
            {"type": "selector_exists", "value": ".user-name"},
            {"type": "text_contains", "selector": ".user-info", "value": "你好"},
        ],
        "fail_signals": [
            # 访问需要登录的页面来检测
            {"type": "selector_exists", "value": ".login-mask"},
            {"type": "text_contains", "selector": "body", "value": "你好,请登录"},
            # 京东首页未登录时显示的登录按钮
            {"type": "selector_exists", "value": ".login-item"},
        ],
        "verify_urls": [
            "https://trade.jd.com/trade/order/productList.action",  # 订单页面，需登录
        ],
    },
    "xiaohongshu": {
        "name": "小红书",
        "login_url": "https://www.xiaohongshu.com",
        "check_url": "https://www.xiaohongshu.com",
        "success_signals": [
            {"type": "selector_exists", "value": ".user-home"},
            {"type": "selector_exists", "value": ".avatar-container"},
        ],
        "fail_signals": [
            {"type": "selector_exists", "value": ".login-mask"},
            {"type": "text_contains", "selector": "body", "value": "登录后"},
        ],
        "verify_urls": [],
    },
}

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
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load_storage_state(channel: str) -> dict | None:
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


def _check_login_status(page, channel: str) -> dict:
    """检查指定渠道的登录状态。"""
    config = CHANNEL_CONFIG.get(channel)
    if not config:
        return {"status": "unknown", "reason": f"未知渠道：{channel}"}

    # 先检查失效信号
    fail_result = _detect_signal(page, config["fail_signals"])
    if fail_result["matched"]:
        return {"status": "expired", "reason": f"检测到失效信号：{fail_result['signal']}"}

    # 再检查成功信号
    success_result = _detect_signal(page, config["success_signals"])
    if success_result["matched"]:
        return {"status": "ok", "reason": f"登录态有效（{success_result['signal']}）"}

    return {"status": "unknown", "reason": "无法判断登录状态"}


def cmd_login(args):
    """启动浏览器让用户手动登录，然后保存登录态。"""
    channel = args.channel
    if channel not in CHANNEL_CONFIG:
        sys.exit(f"错误：未知渠道 '{channel}'。支持的渠道：{', '.join(CHANNEL_CONFIG.keys())}")

    config = CHANNEL_CONFIG[channel]
    timeout = args.timeout or DEFAULT_TIMEOUT
    state_path = _session_path(channel)

    print(f"🌐 即将打开 {config['name']} 登录页...")
    print(f"⏰ 请在 {timeout} 秒内完成登录（扫码/账号密码）")
    print(f"💾 登录成功后将自动保存状态到：{state_path}")

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
        while time.time() < deadline:
            checked += 1
            time.sleep(3)

            status = _check_login_status(page, channel)
            remaining = max(0, int(deadline - time.time()))

            if status["status"] == "ok":
                # 登录成功，保存状态
                saved = _save_storage_state(browser, channel)
                print(f"\n✅ 登录成功！{config['name']}登录态已保存到：{saved}")
                print(f"   保存时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

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

                browser.close()
                print(f"💡 下次使用时将自动复用此登录态，无需重新登录。")
                return
            else:
                if checked % 5 == 0:
                    print(f"   ⏳ 等待登录中... ({remaining}秒剩余)")

        # 超时
        browser.close()
        print(f"\n⏰ 登录等待超时（{timeout}秒）。")
        print(f"💡 如果已完成登录但未保存，请使用 --timeout 参数增加等待时间，或重新执行登录。")


def cmd_check(args):
    """检查指定渠道的登录态是否有效。"""
    channel = args.channel
    if channel not in CHANNEL_CONFIG:
        sys.exit(f"错误：未知渠道 '{channel}'。支持的渠道：{', '.join(CHANNEL_CONFIG.keys())}")

    config = CHANNEL_CONFIG[channel]
    check_url = args.url or config.get("check_url", config["login_url"])
    state_path = _session_path(channel)

    state = _load_storage_state(channel)
    if state is None:
        print(f"❌ 未找到 {config['name']} 的登录态，请先执行 login 命令。")
        return

    # 显示保存时间
    meta = state.get("_meta", {})
    saved_at = meta.get("saved_at", "未知")
    print(f"📋 检查 {config['name']} 登录态...")
    print(f"   存储时间：{saved_at}")

    with sync_playwright() as p:
        profile_dir = SESSION_DIR / f"{channel}_profile"
        page = None

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
            if state.get("cookies"):
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
        elif status["status"] == "expired":
            print(f"❌ {config['name']} 登录态已失效！")
            print(f"   原因：{status['reason']}")
            print(f"   请重新执行：python login_manager.py login {channel}")
        else:
            print(f"⚠️  无法判断 {config['name']} 的登录状态。")
            print(f"   原因：{status['reason']}")
            print(f"   当前页面：{page.url}")

        if profile_dir.exists():
            context.close()
        else:
            browser.close()


def cmd_check_and_login(args):
    """检查登录态，失效则自动打开浏览器跳转到登录页。"""
    channel = args.channel
    if channel not in CHANNEL_CONFIG:
        sys.exit(f"错误：未知渠道 '{channel}'。支持的渠道：{', '.join(CHANNEL_CONFIG.keys())}")

    config = CHANNEL_CONFIG[channel]
    timeout = args.timeout or DEFAULT_TIMEOUT
    state_path = _session_path(channel)

    state = _load_storage_state(channel)
    profile_dir = SESSION_DIR / f"{channel}_profile"

    if state is None and not profile_dir.exists():
        print(f"❌ 未找到 {config['name']} 登录态，即将打开浏览器跳转到登录页...")
        cmd_login(args)
        return

    print(f"📋 检查 {config['name']} 登录态...")
    with sync_playwright() as p:
        page = None
        context = None

        if profile_dir.exists():
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=True,
            )
            page = context.pages[0] if context.pages else context.new_page()
        else:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=str(state_path) if state.get("cookies") else None)
            page = context.new_page()

        try:
            page.goto(config["check_url"], wait_until="domcontentloaded", timeout=CHECK_TIMEOUT)
        except PlaywrightTimeout:
            pass

        status = _check_login_status(page, channel)

        if status["status"] == "ok":
            print(f"✅ {config['name']} 登录态有效，可直接使用！")
            if context:
                context.close()
            return

        print(f"⚠️  {config['name']} 登录态已失效或无法判断（{status['reason']}）")
        print(f"🌐 即将打开 {config['name']} 登录页，请在浏览器中完成登录...")

        if context:
            context.close()

    # 自动跳转登录
    cmd_login(args)


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