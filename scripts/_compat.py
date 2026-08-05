#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨脚本共享工具：Windows UTF-8 编码兼容 + 原子写入。

被 profile_manager.py 与 login_manager.py 共用，避免两处重复编码兼容代码。
"""
import io
import json
import os
import sys
import tempfile
import time


def ensure_utf8_stdio():
    """Windows 下确保 stdin/stdout 使用 UTF-8，避免中文乱码。

    - 仅当 stdin/stdout 为标准 TextIOWrapper（自带 .buffer）时才包装；
      若已被 pytest 等工具替换为捕获对象（无 .buffer），则跳过。
    - 测试/嵌入环境（pytest 已加载）下不做包装，避免破坏其输出捕获机制。
    """
    if sys.platform != "win32":
        return
    if "pytest" in sys.modules:
        return
    if hasattr(sys.stdout, "buffer") and hasattr(sys.stdin, "buffer"):
        sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def atomic_write(p, data, max_retries: int = 3):
    """原子写入：临时文件 + os.replace，避免写入中断损坏数据。

    Windows 下偶发 PermissionError（文件被占用），按指数退避重试后再抛。
    """
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
