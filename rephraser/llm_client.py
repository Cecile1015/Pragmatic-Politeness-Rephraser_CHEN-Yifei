# -*- coding: utf-8 -*-
"""
llm_client.py —— 大模型调用模块（A 轨引擎）

【默认适配 DeepSeek】
DeepSeek 提供的是"OpenAI 兼容接口"，所以这里用官方 openai 库调用即可。
只要在 .env 里改两行，同样的代码也能用 OpenAI / 通义千问 / Kimi / 智谱 等厂商：

    LLM_API_KEY  = 你的密钥
    LLM_BASE_URL = https://api.deepseek.com
    LLM_MODEL    = deepseek-chat

【安全提醒】
API Key 只存在于服务器端的 .env 文件里，永远不会发送到浏览器；
.gitignore 已经排除了 .env，所以上传 GitHub 不会泄露密钥。
"""

import json
import os
import re

from .config import ALL_STYLES
from .prompts import build_messages


# ---------------------------------------------------------------------------
# 读取环境变量（.env 由 app.py 里的 load_dotenv() 加载）
# ---------------------------------------------------------------------------
def _env(name: str, default: str = "") -> str:
    """读取环境变量并去掉首尾空格，读不到就返回默认值。"""
    return (os.getenv(name) or default).strip()


def is_available() -> bool:
    """
    判断当前是否具备调用大模型的条件。

    只要 .env 里配了 LLM_API_KEY，就认为可用。
    app.py 会根据这个函数决定走 A 轨（大模型）还是 B 轨（离线模板）。
    """
    return bool(_env("LLM_API_KEY"))


def model_name() -> str:
    """当前使用的模型名，用于在页面上显示"由 xxx 生成"。"""
    return _env("LLM_MODEL", "deepseek-chat")


# ---------------------------------------------------------------------------
# JSON 解析：大模型偶尔会画蛇添足包一层 ```json ```，这里做容错处理
# ---------------------------------------------------------------------------
def _extract_json(raw: str) -> dict:
    """
    从模型返回的字符串里抠出 JSON 对象。

    处理三种常见情况：
      1. 干净的 JSON            -> 直接解析
      2. 被 ```json ``` 包裹    -> 去掉代码块标记
      3. 前后有多余说明文字      -> 用正则截取第一个 { 到最后一个 }
    """
    raw = (raw or "").strip()

    # 情况 2：去掉 markdown 代码块标记
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()

    # 情况 1：直接尝试解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 情况 3：截取第一个 { 到最后一个 }
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        return json.loads(raw[start:end + 1])

    raise ValueError("模型返回的内容不是合法 JSON")


# ---------------------------------------------------------------------------
# 主函数：调用大模型完成改写
# ---------------------------------------------------------------------------
def rephrase(text: str, scene_key: str, target_lang_key: str, styles: list) -> dict:
    """
    调用大模型生成各档改写结果。

    参数:
        text            : 原始文本
        scene_key       : 场景 key
        target_lang_key : 目标语言 key
        styles          : 需要生成的风格列表（来自 config.build_style_list）
    返回:
        dict: { "results": [...], "missing": [缺失的 key] }
              results 里每一项包含 key / zh / en / color / text / feature / strategy
    异常:
        任何网络错误、超时、解析失败都会抛出异常，
        由 app.py 捕获后自动降级到离线模板引擎。
    """
    # 延迟导入：没装 openai 库时，只要不调用本函数就不会报错
    from openai import OpenAI

    client = OpenAI(
        api_key=_env("LLM_API_KEY"),
        base_url=_env("LLM_BASE_URL", "https://api.deepseek.com"),
        timeout=90.0,          # 90 秒超时，生成 7 个版本需要一点时间
        max_retries=1,         # 失败自动重试 1 次
    )

    messages = build_messages(text, scene_key, target_lang_key, styles)

    response = client.chat.completions.create(
        model=model_name(),
        messages=messages,
        # temperature 控制随机性：0.8 让不同档位的表达更有区分度，
        # 又不至于跑题。想要更稳定可以调到 0.5。
        temperature=0.8,
        max_tokens=2000,
        # 强制模型返回 JSON 对象，DeepSeek 与 OpenAI 都支持这个参数
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    data = _extract_json(raw)

    versions = data.get("versions")
    if not isinstance(versions, list) or not versions:
        raise ValueError("模型返回的 JSON 里没有 versions 数组")

    # ---------- 把模型结果按 key 整理成字典，方便后面按顺序取用 ----------
    by_key = {}
    for item in versions:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        content = str(item.get("text", "")).strip()
        if key in ALL_STYLES and content:
            by_key[key] = {
                "text": content,
                "feature": str(item.get("feature", "")).strip() or "—",
                "strategy": str(item.get("strategy", "")).strip() or "—",
            }

    # ---------- 按我们要求的顺序拼装最终结果 ----------
    results = []
    missing = []
    for style in styles:
        key = style["key"]
        if key in by_key:
            results.append({
                "key": key,
                "zh": style["zh"],
                "en": style["en"],
                "color": style["color"],
                "text": by_key[key]["text"],
                "feature": by_key[key]["feature"],
                "strategy": by_key[key]["strategy"],
            })
        else:
            # 某一档模型没给出来，先占个位，交给 app.py 用离线模板补齐
            missing.append(key)

    if not results:
        raise ValueError("模型返回的版本全部无法识别")

    return {"results": results, "missing": missing}
