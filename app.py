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
import re

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from rephraser import __app_name__, __version__
from rephraser import challenges, guard, llm_client, offline_engine, scoring
from rephraser.config import (
    LANGUAGE_KEYS,
    LANGUAGE_LABELS,
    MAX_INPUT_LENGTH,
    SCENE_KEYS,
    build_style_list,
    get_scene,
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
# 启动时把关键配置状态打进日志。
# 部署到 Render 后，在左侧 Logs 标签就能一眼看出：
# Key 认到了没有、口令启用了没有、口令是不是多了引号或空格。
# 注意这里只打印长度和首尾字符，绝不打印密钥或口令原文。
# ---------------------------------------------------------------------------
app.logger.warning(
    "[启动] 改写引擎：%s｜%s｜每日上限 %d 次，单人 %d 次",
    ("大模型 " + llm_client.model_name()) if llm_client.is_available() else "离线模板（未检测到 LLM_API_KEY）",
    guard.describe() if guard.code_required() else "未启用访问口令",
    guard.daily_limit(), guard.per_ip_daily_limit(),
)


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
    # 游戏交互页要用的配置
    cfg["maxAnswerLength"] = MAX_ANSWER_LENGTH
    cfg["challengeCount"] = len(challenges.CHALLENGES)
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
    # 把诊断信息写进服务器日志（只有你在 Render 的 Logs 里能看到），
    # 方便你对照出到底是引号、空格还是真的输错了
    app.logger.warning("[口令] %s", guard.describe(supplied))
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


# ===========================================================================
# 游戏交互：每日挑战 / 自由练习
# ===========================================================================

# 挑战作答的长度上限。比改写输入宽一些，因为一个完整的面子威胁行为
# 往往需要铺垫＋理由＋缓冲，200 字容易不够用。
MAX_ANSWER_LENGTH = 300


@app.route("/api/challenge/daily")
def api_challenge_daily():
    """
    取"今日挑战"。

    【为什么日期由前端传？】
    服务器在 UTC 时区，用户在香港（UTC+8）。如果用服务器日期，
    香港时间早上 8 点之前拿到的还是"昨天"的题，打卡也会错位。
    所以让浏览器把本地日期传上来。
    """
    if not guard.code_ok(request.headers.get("X-Access-Code", "")):
        return jsonify({"ok": False, "needCode": True, "error": "需要访问口令。"}), 401

    day = (request.args.get("day") or "").strip()
    # 简单校验格式，防止乱传的字符串影响哈希
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day or ""):
        day = None

    ch = challenges.daily_challenge(day)
    return jsonify({"ok": True, "mode": "daily", "day": day,
                    "challenge": challenges.public_view(ch)})


@app.route("/api/challenge/random")
def api_challenge_random():
    """随机抽一题，用于自由练习。exclude 参数用来避开刚做完的那题。"""
    if not guard.code_ok(request.headers.get("X-Access-Code", "")):
        return jsonify({"ok": False, "needCode": True, "error": "需要访问口令。"}), 401

    ch = challenges.random_challenge((request.args.get("exclude") or "").strip() or None)
    return jsonify({"ok": True, "mode": "practice",
                    "challenge": challenges.public_view(ch)})


@app.route("/api/challenge/score", methods=["POST"])
def api_challenge_score():
    """
    给一份作答打分。

    请求体:
        { "id": "c01", "answer": "老板，这个方向我理解……", "streak": 3 }
    返回:
        评分结果 + 积分换算 + 参考答案与语用学讲解（这时候才揭晓）
    """
    if not guard.code_ok(request.headers.get("X-Access-Code", "")):
        return jsonify({"ok": False, "needCode": True, "error": "需要访问口令。"}), 401

    data = request.get_json(silent=True) or {}
    cid = str(data.get("id", "")).strip()
    answer = str(data.get("answer", "")).strip()
    try:
        streak = max(0, int(data.get("streak", 0)))
    except (TypeError, ValueError):
        streak = 0

    ch = challenges.get(cid)
    if not ch:
        return jsonify({"ok": False, "error": "题目编号不存在。"}), 400
    if not answer:
        return jsonify({"ok": False, "error": "请先写下你的说法再提交。"}), 400
    if len(answer) > MAX_ANSWER_LENGTH:
        return jsonify({"ok": False,
                        "error": f"作答超过 {MAX_ANSWER_LENGTH} 字上限（当前 {len(answer)} 字）。"}), 400

    scene = get_scene(ch["scene"])
    scene_label = scene["label"] if scene else ch["scene"]

    note = ""
    result = None
    ip = guard.client_ip(request)

    # ---------- 优先大模型评分，同样走用量护栏 ----------
    if llm_client.is_available():
        allowed, deny_reason, _ = guard.take(ip)
        if allowed:
            try:
                raw = llm_client.complete(
                    scoring.build_score_prompt(answer, ch, scene_label),
                    max_tokens=1200,
                    # 评分用低温度：同一份作答重复提交，分数应尽量稳定，
                    # 否则没法作为研究数据使用
                    temperature=0.3,
                )
                result = scoring.parse_score(raw)
            except Exception as exc:  # noqa: BLE001
                app.logger.warning("评分调用失败，降级到规则引擎：%s", exc)
                guard.refund(ip)
                note = f"大模型评分失败（{type(exc).__name__}），本次由规则引擎打分。"
        else:
            note = deny_reason

    # ---------- 规则引擎兜底 ----------
    if result is None:
        result = scoring.score_offline(answer, ch)
        if not note:
            note = "本次由离线规则引擎打分。"
        note += "规则打分只识别语言形式，不理解语义，仅供练习参考。"

    pts = scoring.points_for(result["overall"], streak)

    return jsonify({
        "ok": True,
        "note": note,
        "result": result,
        "points": pts,
        # 提交之后才揭晓参考答案和讲解
        "reference": ch["reference"],
        "explain": ch["note"],
        "sceneLabel": scene_label,
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
