#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""profile_manager.py 单元测试。

覆盖核心纯函数：_deep_merge / _auto_nickname / _sanitize_nickname / _path。
运行：python -m pytest scripts/test_profile_manager.py -q
（无 pytest 时也可直接 `python scripts/test_profile_manager.py` 跑内置 runner）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import profile_manager as pm  # noqa: E402


def test_deep_merge_dict_recursive():
    base = {"a": {"x": 1}, "b": 2}
    patch = {"a": {"y": 3}, "b": None}
    out = pm._deep_merge(dict(base), patch)
    assert out["a"] == {"x": 1, "y": 3}
    assert "b" not in out  # null 删除键


def test_deep_merge_append_list():
    out = pm._deep_merge({"gift_history": [1]}, {"gift_history": [2, 3]})
    assert out["gift_history"] == [1, 2, 3]


def test_deep_merge_extend_dedup():
    base = {"colors_like": ["红", "蓝"]}
    out = pm._deep_merge(dict(base), {"colors_like": ["蓝", "绿"]})
    assert out["colors_like"] == ["红", "蓝", "绿"]


def test_deep_merge_other_list_replace():
    out = pm._deep_merge({"foo": [1, 2]}, {"foo": [3]})
    assert out["foo"] == [3]


def test_auto_nickname_deterministic():
    p = {"relationship_stage": "stable", "style": "酷"}
    assert pm._auto_nickname(p) == pm._auto_nickname(dict(p))


def test_auto_nickname_stage_prefix():
    n = pm._auto_nickname({"relationship_stage": "honeymoon"})
    assert n.startswith("热恋期")


def test_auto_nickname_fallback_deterministic():
    # 无 stage/风格/爱好/颜色时走兜底，依赖 patch 内容 hash，确定性
    p = {"nickname": "她"}
    assert pm._auto_nickname(p) == pm._auto_nickname(p)


def test_sanitize_illegal_chars():
    assert pm._sanitize_nickname('a/b:c*?"<>|') == "abc"


def test_sanitize_zero_width():
    assert pm._sanitize_nickname("宝\u200b贝﻿") == "宝贝"


def test_sanitize_length_truncate():
    long = "x" * 100
    assert len(pm._sanitize_nickname(long)) == pm.MAX_NICKNAME_LENGTH


def test_path_boundary_rejects():
    import pytest
    for bad in [" a", "a.", "..", ".x"]:
        with pytest.raises(SystemExit):
            pm._path(bad)


def test_path_normal_ok():
    p = pm._path("normal_name")
    assert p.name == "normal_name.json"


def test_path_slash_sanitized():
    p = pm._path("a/b")
    assert p.name == "ab.json"


if __name__ == "__main__":
    # 无 pytest 时的内置 runner
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
