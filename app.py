# -*- coding: utf-8 -*-
"""
app.py —— 泡泡改写 2P Rephraser 的 Flask 后端主程序

【整体流程】
    浏览器 ──POST /api/rephrase──> 这个文件
                                      │
                                      ├─ 1. 校验参数（文本非空、不超 200 字、场景与语言合法）
                                      ├─ 2. 自动识别输入文本的语言
                                      ├─ 3. 选择引擎：
                                      │      有 API Key -> llm_client（大模型）
                                      │      失败或无 Key -> offline_engine（离线模板）
                                      └─ 4. 返回 JSON 给浏览器渲染

【怎么运行】
    pip install -r requirements.txt
    python app.py
    浏览器打开 http://127.0.0.1:5000
"""

import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from rephraser import __app_name__, __version__
from rephraser import guard, llm_client, offline_engine
from rephraser.config import (
    LANGUAGE_KEYS,
    LANGUAGE_LABELS,
    MAX_INPUT_LENGTH,
    SCENE_KEYS,
    build_style_list,
    public_config,
)
from rephraser.lang_detect import detect_language

# 读取项目根目录下的 .env 文件，把里面的 LLM_API_KEY 等写入环境变量
# （.env 不存在也不会报错，程序会自动走离线模式）
load_dotenv()

app = Flask(__name__)
# 让 jsonify 直接输出中文而不是 \uXXXX 转义，方便调试时肉眼查看
app.config["JSON_AS_ASCII"] = False
app.json.ensure_ascii = False


# ---------------------------------------------------------------------------
# 页面路由：返回单页应用的 HTML 骨架
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """首页。三个页面都在这一个 HTML 里，通过底部导航切换。"""
    return render_template(
        "index.html",
        app_name=__app_name__,
        version=__version__,
    )


# ---------------------------------------------------------------------------
# 接口 1：把配置发给前端（下拉框选项、颜色、字数上限等）
# ---------------------------------------------------------------------------
@app.route("/api/config")
def api_config():
    """
    前端启动时调用一次，拿到所有下拉框选项和样式配置。
    这样以后新增一个场景，只需要改 config.py，前端自动跟着变。
    """
    cfg = public_config()
    # 顺带告诉前端当前用的是哪个引擎，页面上会显示不同的提示条
    cfg["engineAvailable"] = llm_client.is_available()
    cfg["engineModel"] = llm_client.model_name() if llm_client.is_available() else None
    cfg["appName"] = __app_name__
    cfg["version"] = __version__

    # 是否需要访问口令（注意：这里只告诉前端"要不要问"，绝不返回口令本身）
    cfg["codeRequired"] = guard.code_required()
    # 今日额度情况，显示在页面上让你随时知道余量
    cfg["quota"] = guard.snapshot() if llm_client.is_available() else None
    return jsonify(cfg)


# ---------------------------------------------------------------------------
# 接口 1.5：校验访问口令
# ---------------------------------------------------------------------------
@app.route("/api/unlock", methods=["POST"])
def api_unlock():
    """
    前端把访客输入的口令发过来校验一次。
    正确就返回 ok:true，前端会把口令记在浏览器里，之后每次请求自动带上。
    """
    data = request.get_json(silent=True) or {}
    supplied = str(data.get("code", ""))
    if guard.code_ok(supplied):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "口令不对，请再确认一下。"}), 401


# ---------------------------------------------------------------------------
# 接口 2：核心改写接口
# ---------------------------------------------------------------------------
@app.route("/api/rephrase", methods=["POST"])
def api_rephrase():
    """
    接收前端的改写请求。

    请求体 (JSON):
        {
          "text": "我现在需要你的帮助",
          "scene": "boss",
          "target_lang": "zh",
          "include_special": false      # 是否额外生成"强硬"和"撒娇"两条
        }

    返回 (JSON):
        {
          "ok": true,
          "engine": "llm" | "offline",
          "note": "提示文字（可能为空）",
          "input_lang": "zh",
          "input_lang_label": "普通话汉语",
          "results": [ {key, zh, en, color, text, feature, strategy}, ... ]
        }
    """
    # ---------- 第 0 步：访问口令校验 ----------
    # 口令由前端放在 X-Access-Code 请求头里带上来
    if not guard.code_ok(request.headers.get("X-Access-Code", "")):
        return jsonify({"ok": False, "needCode": True,
                        "error": "需要访问口令才能使用改写功能。"}), 401

    data = request.get_json(silent=True) or {}

    text = str(data.get("text", "")).strip()
    scene = str(data.get("scene", "")).strip()
    target_lang = str(data.get("target_lang", "")).strip()
    include_special = bool(data.get("include_special", False))

    # ---------- 第 1 步：参数校验 ----------
    if not text:
        return jsonify({"ok": False, "error": "请输入需要改写的文本。"}), 400

    if len(text) > MAX_INPUT_LENGTH:
        return jsonify({
            "ok": False,
            "error": f"输入文本超过 {MAX_INPUT_LENGTH} 字符上限（当前 {len(text)} 字符）。"
        }), 400

    if scene not in SCENE_KEYS:
        return jsonify({"ok": False, "error": "应用场景参数不合法。"}), 400

    if target_lang not in LANGUAGE_KEYS:
        return jsonify({"ok": False, "error": "目标语言参数不合法。"}), 400

    # ---------- 第 2 步：自动识别输入语言（用于历史记录标注） ----------
    input_lang = detect_language(text)

    # ---------- 第 3 步：决定这次要生成哪几档 ----------
    styles = build_style_list(include_special)

    engine = "offline"
    note = ""
    results = None
    remaining = None

    # ---------- 第 3.5 步：用量护栏 ----------
    # 先向护栏"申请"一次大模型额度；额度用完就直接走离线模板，
    # 网站依然可用，只是自然度下降——这比直接报错友好得多。
    ip = guard.client_ip(request)
    allowed, deny_reason, remaining = (True, "", None)
    if llm_client.is_available():
        allowed, deny_reason, remaining = guard.take(ip)
        if not allowed:
            note = deny_reason

    # ---------- 第 4 步：优先走大模型（A 轨） ----------
    if llm_client.is_available() and allowed:
        try:
            llm_out = llm_client.rephrase(text, scene, target_lang, styles)
            results = llm_out["results"]
            engine = "llm"

            # 如果模型漏掉了某几档，用离线模板把缺口补上，保证卡片数量完整
            if llm_out["missing"]:
                fallback = offline_engine.rephrase_map(text, scene, target_lang, styles)
                filled = {item["key"]: item for item in results}
                for key in llm_out["missing"]:
                    if key in fallback:
                        filled[key] = fallback[key]
                # 按 styles 的原始顺序重新排列
                results = [filled[s["key"]] for s in styles if s["key"] in filled]
                note = "部分档位由大模型返回不完整，已用内置模板补齐。"

        except Exception as exc:  # noqa: BLE001 —— 这里要捕获所有异常做降级
            # 任何网络错误、超时、余额不足、JSON 解析失败，都自动降级
            app.logger.warning("大模型调用失败，降级到离线引擎：%s", exc)
            # 用户没拿到大模型结果，把刚才占用的额度退回去，不能白扣
            guard.refund(ip)
            results = None
            note = f"大模型调用失败（{type(exc).__name__}），已自动切换到离线模板模式。"

    # ---------- 第 5 步：离线兜底（B 轨） ----------
    if results is None:
        results = offline_engine.rephrase(text, scene, target_lang, styles)
        engine = "offline"
        # 把降级原因和离线说明拼在一起
        note = (note + " " if note else "") + \
               offline_engine.offline_note(target_lang, llm_client.is_available())

    return jsonify({
        "ok": True,
        "engine": engine,
        "engineModel": llm_client.model_name() if engine == "llm" else None,
        "note": note,
        "input_lang": input_lang,
        "input_lang_label": LANGUAGE_LABELS.get(input_lang, "未识别"),
        "results": results,
        # 今日额度快照，前端显示在提示条上
        "quota": guard.snapshot() if llm_client.is_available() else None,
    })


# ---------------------------------------------------------------------------
# 接口 3：健康检查（部署到服务器后可以用它确认服务是否活着）
# ---------------------------------------------------------------------------
@app.route("/api/health")
def api_health():
    return jsonify({
        "ok": True,
        "app": __app_name__,
        "version": __version__,
        "engine": "llm" if llm_client.is_available() else "offline",
        "codeRequired": guard.code_required(),
        "quota": guard.snapshot() if llm_client.is_available() else None,
    })


# ---------------------------------------------------------------------------
# 启动入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # PORT 可以通过环境变量覆盖，部署到 Render 等平台时会用到
    port = int(os.getenv("PORT", "5000"))
    # debug=True 会在你改代码后自动重启，方便开发；正式部署请改成 False
    app.run(host="0.0.0.0", port=port, debug=True)
