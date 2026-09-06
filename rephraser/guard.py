# -*- coding: utf-8 -*-
"""
guard.py —— 访问口令与用量护栏

【为什么需要这个文件】
一旦把 DeepSeek 的 API Key 放进服务器环境变量，你的网址就变成了一个
"任何人都能调用、但花你的钱"的接口。这个模块做两件事来保护你的余额：

  1. 访问口令：没有口令的人调不了改写接口。
  2. 每日用量上限：即使口令泄露了，一天最多也只会花掉你设定的次数。

【重要：这是"门锁"，不是"保险柜"】
口令是明文比对的，拿到口令的人可以无限次转发给别人；
真正兜底的是第 2 条——每日上限，它保证最坏情况下损失可控。
对"发给导师和几位同学试用"这个场景，这个强度是够的；
如果将来要正式公开发布，应该换成真正的用户系统。

【全部通过环境变量配置，不写进代码，因此不会上传到 GitHub】
  ACCESS_CODE          访问口令。留空 = 不设口令，任何人可用
  DAILY_LIMIT          全站每天最多调用大模型多少次（默认 100）
  PER_IP_DAILY_LIMIT   单个访客每天最多多少次（默认 20）
"""

import os
import threading
from datetime import date

# 计数器是多个请求共用的，加把锁避免同时读写出错
_lock = threading.Lock()

# 内存中的当日计数。结构：{"day": "2026-09-05", "total": 7, "ips": {"1.2.3.4": 3}}
_state = {"day": None, "total": 0, "ips": {}}


# ---------------------------------------------------------------------------
# 读取配置
# ---------------------------------------------------------------------------
def _clean(s: str) -> str:
    """
    清洗口令字符串，专门对付复制粘贴带来的各种看不见的问题。

    实践中最常见的三类错误：
      1. 在 Render 的 Value 栏里写成了 "口令"（带引号）—— 引号会变成口令的一部分
      2. 从聊天软件或网页复制时带上了零宽空格、不换行空格
      3. 把整行 ACCESS_CODE=xxx 粘进了 Value 栏
    这些都不是使用者的错，程序应该容错，而不是让人对着"口令不对"发呆。
    """
    s = str(s or "")

    # 去掉零宽字符和 BOM（复制粘贴时最容易混进来、且完全看不见）
    for ch in ("​", "‌", "‍", "﻿"):
        s = s.replace(ch, "")
    # 不换行空格换成普通空格，再统一去首尾空白
    s = s.replace(" ", " ").strip()

    # 有人会把整行都粘进 Value 栏
    if s.upper().startswith("ACCESS_CODE="):
        s = s.split("=", 1)[1].strip()

    # 去掉成对的引号（Render 的 Value 栏不需要引号）
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1].strip()

    return s


def access_code() -> str:
    """访问口令；返回空字符串表示不启用口令。"""
    return _clean(os.getenv("ACCESS_CODE"))


def _int_env(name: str, default: int) -> int:
    """读取一个整数型环境变量，填错了就用默认值，不让服务崩掉。"""
    try:
        v = int((os.getenv(name) or "").strip())
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


def daily_limit() -> int:
    """全站每日大模型调用上限。"""
    return _int_env("DAILY_LIMIT", 100)


def per_ip_daily_limit() -> int:
    """单个访客每日调用上限，防止一个人把当天额度用光。"""
    return _int_env("PER_IP_DAILY_LIMIT", 20)


# ---------------------------------------------------------------------------
# 口令校验
# ---------------------------------------------------------------------------
def code_required() -> bool:
    """当前是否启用了访问口令。"""
    return bool(access_code())


def code_ok(supplied: str) -> bool:
    """
    校验访客提交的口令。
    没设口令时一律放行；设了口令时，两边都先做同样的清洗再比对。
    """
    real = access_code()
    if not real:
        return True
    return _clean(supplied) == real


def describe(supplied: str = None) -> str:
    """
    生成一行只写进服务器日志的诊断信息。

    【为什么只给长度和首尾字符，不给完整口令】
    Render 的日志只有你自己能看，但把口令原文写进日志仍然是个坏习惯
    （日志会被导出、截图、分享）。长度和首尾字符已经足够定位
    "引号没去掉""多了个空格""粘错了变量名"这几类问题。
    """
    real = access_code()
    def sketch(s):
        if not s:
            return "空"
        return f"长度{len(s)}，首字符 {s[0]!r}，末字符 {s[-1]!r}"

    if supplied is None:
        return f"服务器口令：{sketch(real)}"
    return (f"口令比对失败 —— 服务器端：{sketch(real)}；"
            f"访客提交（清洗后）：{sketch(_clean(supplied))}")


# ---------------------------------------------------------------------------
# 用量计数
# ---------------------------------------------------------------------------
def _roll_over_if_new_day():
    """跨天了就把计数清零。调用前必须已经持有锁。"""
    today = date.today().isoformat()
    if _state["day"] != today:
        _state["day"] = today
        _state["total"] = 0
        _state["ips"] = {}


def snapshot() -> dict:
    """
    读取当前用量状态，只读不计数，用于 /api/config 显示"今日剩余"。
    """
    with _lock:
        _roll_over_if_new_day()
        return {
            "day": _state["day"],
            "used": _state["total"],
            "limit": daily_limit(),
            "remaining": max(0, daily_limit() - _state["total"]),
        }


def take(ip: str):
    """
    尝试占用一次大模型调用额度。

    参数:
        ip: 访客 IP，用于单人限额
    返回:
        (allowed, reason, remaining)
          allowed   —— True 表示可以调用大模型
          reason    —— 被拒绝时给用户看的中文说明；允许时为空字符串
          remaining —— 本次之后全站还剩多少次
    """
    with _lock:
        _roll_over_if_new_day()

        total_cap = daily_limit()
        ip_cap = per_ip_daily_limit()
        used_by_ip = _state["ips"].get(ip, 0)

        # 先看全站额度
        if _state["total"] >= total_cap:
            return (False,
                    f"今天的大模型额度已用完（每日上限 {total_cap} 次），"
                    f"已自动切换到离线模板模式。明天 0 点自动重置。",
                    0)

        # 再看单人额度
        if used_by_ip >= ip_cap:
            return (False,
                    f"你今天的调用次数已达上限（单人每日 {ip_cap} 次），"
                    f"已自动切换到离线模板模式。明天 0 点自动重置。",
                    max(0, total_cap - _state["total"]))

        # 两个额度都没满，占用一次
        _state["total"] += 1
        _state["ips"][ip] = used_by_ip + 1
        return (True, "", max(0, total_cap - _state["total"]))


def refund(ip: str):
    """
    把刚刚占用的额度退回去。
    用在大模型调用失败的时候——用户没得到结果，不该扣他的次数。
    """
    with _lock:
        _roll_over_if_new_day()
        if _state["total"] > 0:
            _state["total"] -= 1
        if _state["ips"].get(ip, 0) > 0:
            _state["ips"][ip] -= 1


def client_ip(request) -> str:
    """
    取访客的真实 IP。

    【为什么不能直接用 request.remote_addr？】
    Render 会在你的应用前面放一层反向代理，所以 remote_addr 拿到的
    是代理的 IP（所有人都一样）。真实 IP 在 X-Forwarded-For 头里，
    格式是 "真实IP, 代理1, 代理2"，取第一个。
    """
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "unknown"
