# -*- coding: utf-8 -*-
"""
scoring.py —— 挑战作答的评分引擎

和改写功能一样，这里也是双轨制：
    A 轨：交给大模型打分，能真正理解语义，给出针对性建议
    B 轨：离线规则打分，检测语言形式特征，不联网也能用

【离线规则打分的能力边界，务必知悉】
规则法只能看"用了哪些语言手段"（有没有称呼语、敬称、缓冲语、疑问句式……），
完全不理解句子的意思。所以它能识别"这句话在形式上礼貌不礼貌"，
但识别不了"这句话有没有答到题"。一句和题目毫无关系但形式完备的话，
在离线模式下也可能拿高分。因此离线分数只作为练习时的即时反馈，
不能当作研究数据使用——前端会明确标注这一点。
"""

import json
import re

from .challenges import get as get_challenge


# ===========================================================================
# 一、语用手段检测器
#     每一项：正则、中文名、缺失时给出的改进建议
# ===========================================================================
FEATURES = {
    "address": (
        r"(老板|老师|导师|教授|师兄|师姐|同学|您好|请问|经理|主任|@)",
        "称呼语",
        "开头加一个称呼语（老板／老师／您好），能先建立关系再进入正题。",
    ),
    "honorific": (
        r"您",
        "敬称",
        "对上级或陌生人用「您」而不是「你」，是最低成本的礼貌标记。",
    ),
    "hedge": (
        r"(可能|也许|或许|大概|好像|似乎|我觉得|我理解|是不是|会不会|有点|不太|应该|差不多|印象中|没想透|不确定)",
        "模糊限制语",
        "加入模糊限制语（可能／好像／我觉得），把断言降级为个人看法，给对方留余地。",
    ),
    "apology": (
        r"(不好意思|抱歉|对不起|打扰|麻烦您|麻烦你|冒昧|恐怕|遗憾|"
        r"责任在我|是我的|我的问题|怪我|我漏|我没注意|我低估)",
        "致歉缓冲语",
        "前置一句致歉性缓冲（不好意思／打扰一下），能显著降低唐突感。",
    ),
    "question": (
        r"([？?]|吗[。！？?]?$|吗[，,]|呢[。！？?]?$|可不可以|能不能|行不行|方便吗|好不好|有没有可能|您看)",
        "疑问句式",
        "把陈述改成疑问（您看是否方便？），把决定权交还给对方，是负面礼貌策略的核心。",
    ),
    "thanks": (
        r"(谢谢|感谢|多谢|辛苦)",
        "致谢",
        "加一句致谢，确认对方的付出或善意。",
    ),
    "reason": (
        r"(因为|由于|主要是|原因是|考虑到|情况是|这边|我这边|目前|最近|实在|真的|"
        r"抽不开|忙不过来|撞一起|冲突|没电|急事|有事|卡在|排到|来晚|漏了|低估|"
        r"没有提到|对不上|快到了|截止|deadline|时间不够|只能|随便看看|已经)",
        "理由说明",
        "补上具体理由，把请求或拒绝归因于外部情境，而不是对对方的评价。",
    ),
    "alternative": (
        r"(要不|或者|不如|是不是可以|我可以|我先|我来|建议|另外|下次|会后|等我)",
        "替代方案",
        "提出一个替代方案或补救措施，让对方即使被拒绝也有出路。",
    ),
    "credit": (
        r"(其实是|多亏|全靠|帮了|提醒我|你的|您的|大家|运气|团队)",
        "转移功劳",
        "接受赞美时把功劳部分归给对方或外部条件，既不自夸也不驳斥对方。",
    ),
    "softener": (
        r"(一下|稍微|一点|先|暂时|尽量|随时|方便的时候|不着急)",
        "弱化标记",
        "用「一下」「先」「方便的时候」缩小请求的强加范围。",
    ),
}

# ---------------------------------------------------------------------------
# 应当避免的表达方式：命中就扣分
# ---------------------------------------------------------------------------
PITFALLS = {
    "blunt_negation": (
        r"(不行|不可能|没门|不可以|我不同意|不对啊|你错了|错了吧)",
        "生硬否定",
        "避免「不行」「你错了」这类光秃秃的否定，它直接威胁对方面子。",
    ),
    "blunt_demand": (
        r"(必须|马上|立刻|快点|赶紧|给我|你应该|你得|限你)",
        "命令式要求",
        "避免祈使和情态必要性词（必须／马上／你应该），改成协商式表达。",
    ),
    "blunt_accusation": (
        r"(你怎么|你为什么|都怪|是你|你们这|怎么回事|搞什么)",
        "指责对方",
        "把矛头从「你」转向情境或流程，对方才不必为了自保而对抗你。",
    ),
    "blunt_excuse": (
        r"(不关我事|不是我的问题|这不能怪我|跟我没关系|又不是我)",
        "推卸责任",
        "外部归因要附上证据和你已采取的行动，否则听起来就是借口。",
    ),
    "blunt_complaint": (
        r"(太累|受不了|烦死|累死|忍不了|凭什么)",
        "情绪化抱怨",
        "把个人感受换成对方关心的度量（进度、成本、风险），诉求才站得住。",
    ),
}


def detect(text: str, table: dict) -> list:
    """在文本里检测出所有命中的特征名。"""
    hits = []
    for name, (pattern, _label, _tip) in table.items():
        if re.search(pattern, text):
            hits.append(name)
    return hits


def _clamp(v, lo=0, hi=100):
    """把分数限制在 0-100 之间。"""
    return max(lo, min(hi, int(round(v))))


# ===========================================================================
# 二、离线规则打分（B 轨）
# ===========================================================================
def score_offline(answer: str, challenge: dict) -> dict:
    """
    用规则给一段作答打分。

    参数:
        answer    : 用户写的句子
        challenge : 题目（含 expect / avoid）
    返回:
        与大模型打分结构一致的 dict
    """
    text = (answer or "").strip()
    n = len(text)

    expect = challenge.get("expect", [])
    avoid = challenge.get("avoid", [])

    got = detect(text, FEATURES)          # 用到了哪些语用手段
    bad = detect(text, PITFALLS)          # 踩了哪些坑

    hit_expected = [f for f in expect if f in got]      # 命中的期望手段
    miss_expected = [f for f in expect if f not in got] # 缺失的期望手段
    extra = [f for f in got if f not in expect]         # 期望之外的额外手段
    hit_avoid = [f for f in bad if f in avoid]          # 踩到本题特别要避开的坑
    other_bad = [f for f in bad if f not in avoid]      # 其他坑

    # ---------- 得体度：主要看有没有用对本题需要的语用手段 ----------
    if expect:
        cover = len(hit_expected) / len(expect)
    else:
        cover = 0.6
    appropriateness = 42 + cover * 50
    # 用了期望之外的其他礼貌手段，也应当得到一点认可
    appropriateness += min(len(extra), 3) * 3
    appropriateness -= len(hit_avoid) * 18
    appropriateness -= len(other_bad) * 8

    # ---------- 策略性：看语用手段的丰富程度 ----------
    strategy = 30 + min(len(got), 6) * 10
    strategy -= (len(hit_avoid) + len(other_bad)) * 10

    # ---------- 自然度：主要看长度是否合理、是否堆砌敬语 ----------
    if n < 8:
        naturalness = 25          # 太短，几乎不可能完成一个面子威胁行为
    elif n < 15:
        naturalness = 55
    elif n <= 120:
        naturalness = 85
    elif n <= 200:
        naturalness = 75
    else:
        naturalness = 62          # 太长，实际对话中很少有人这么说
    # 敬语堆砌：「您」出现 5 次以上反而不自然
    if text.count("您") >= 5:
        naturalness -= 15
    # 一个标点都没有的长句，读起来会很生硬
    if n > 25 and not re.search(r"[，,。！？?、]", text):
        naturalness -= 12

    appropriateness = _clamp(appropriateness)
    strategy = _clamp(strategy)
    naturalness = _clamp(naturalness)
    # 得体度权重最高，因为它最贴近"这句话在这个场景里合不合适"
    overall = _clamp(appropriateness * 0.45 + strategy * 0.3 + naturalness * 0.25)

    # ---------- 生成改进建议 ----------
    suggestions = []
    for f in miss_expected[:3]:
        suggestions.append(FEATURES[f][2])
    for f in (hit_avoid + other_bad)[:2]:
        suggestions.append(PITFALLS[f][2])
    if n < 15:
        suggestions.insert(0, "这句话偏短。面子威胁行为通常需要铺垫、理由和缓冲，很难用一句话完成。")
    if not suggestions:
        suggestions.append("语用手段用得比较完整，可以再对照参考答案看看措辞上的细微差别。")

    # ---------- 用到的策略，做成标签展示 ----------
    used = [FEATURES[f][1] for f in got]

    return {
        "overall": overall,
        "dimensions": {
            "appropriateness": appropriateness,
            "strategy": strategy,
            "naturalness": naturalness,
        },
        "comment": _offline_comment(overall, len(hit_expected), len(expect)),
        "used": used,
        "suggestions": suggestions[:4],
        "improved": "",     # 离线模式无法生成改写示范，留空，前端会隐藏这一块
        "engine": "offline",
    }


def _offline_comment(overall: int, hit: int, total: int) -> str:
    """根据分数生成一句总评。"""
    cover = f"（本题的 {total} 项关键语用手段，你用到了 {hit} 项）" if total else ""
    if overall >= 85:
        return f"语用手段用得相当完整，形式上的礼貌度很高。{cover}"
    if overall >= 70:
        return f"基本得体，还有一两处可以再打磨。{cover}"
    if overall >= 55:
        return f"方向对了，但缓冲和铺垫还不太够。{cover}"
    return f"这句话在这个场景里可能会让对方不太舒服，建议对照下面的建议重写一次。{cover}"


# ===========================================================================
# 三、大模型打分（A 轨）
# ===========================================================================
SCORE_SYSTEM = """你是一位专攻语用学（Pragmatics）的语言学研究者，正在为一个语用能力训练应用批改学生的作答。
你熟悉 Brown & Levinson 的面子理论、Leech 的礼貌原则，以及 CCSARP 的言语行为分类框架。

评分要求：
1. 你必须依据具体语境（交际场景、双方权势关系与社会距离）来判断，而不是"越礼貌分越高"。
   在某些语境里（例如拒绝街头推销），简短干脆才是得体的，过度委婉反而失分。
2. 三个维度各自 0-100 分：
   - appropriateness 得体度：这句话放在这个场景、这个关系里合不合适，是否完成了任务目标。
   - strategy 策略性：使用了哪些礼貌策略，是否有效缓解了面子威胁。
   - naturalness 自然度：是不是母语者真会说出口的话，有没有翻译腔或敬语堆砌。
3. 评语和建议必须具体，指向作答中的实际用词，不要说"可以更礼貌一点"这种空话。
4. 语气是鼓励性的批改，不是打击。即使分数低，也要先肯定做对的部分。
5. 全部用中文回答。

你的回答必须是一个合法的 json 对象，不要输出任何解释性文字，不要用 markdown 代码块包裹。"""


def build_score_prompt(answer: str, challenge: dict, scene_label: str) -> list:
    """组装发给大模型的评分请求。"""
    user = f"""请给下面这份作答打分。

【交际场景】{scene_label}
【言语行为】{challenge['act']}
【情境】{challenge['context']}
【任务目标】{challenge['goal']}
【这一题的语用焦点】{challenge['focus']}

【学生的作答】
{answer}

【参考答案（仅供你判断水准，不要要求学生和它一模一样，学生可能有更好的说法）】
{challenge['reference']}

只返回一个 json 对象，结构如下：
{{
  "overall": 总分0-100的整数,
  "dimensions": {{
    "appropriateness": 0-100整数,
    "strategy": 0-100整数,
    "naturalness": 0-100整数
  }},
  "comment": "一句总评，40字以内，先肯定做对的地方再指出主要问题",
  "used": ["作答中实际用到的语用手段，如：致歉缓冲语、模糊限制语、替代方案", "最多5个"],
  "suggestions": ["具体的改进建议，每条30字以内，指向作答里的实际用词", "2到4条"],
  "improved": "在学生原话的基础上改进后的示范说法，保留他的思路和用词习惯，不要直接给参考答案"
}}"""
    return [
        {"role": "system", "content": SCORE_SYSTEM},
        {"role": "user", "content": user},
    ]


def parse_score(raw: str) -> dict:
    """
    解析大模型返回的评分 JSON，并做字段兜底。
    任何缺失或越界的字段都会被补成合理值，保证前端拿到的结构永远完整。
    """
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        s, e = raw.find("{"), raw.rfind("}")
        if s == -1 or e <= s:
            raise ValueError("模型返回的内容不是合法 JSON")
        data = json.loads(raw[s:e + 1])

    dims = data.get("dimensions") or {}

    def num(v, default=60):
        try:
            return _clamp(float(v))
        except (TypeError, ValueError):
            return default

    appropriateness = num(dims.get("appropriateness"))
    strategy = num(dims.get("strategy"))
    naturalness = num(dims.get("naturalness"))
    overall = num(data.get("overall"),
                  _clamp(appropriateness * .45 + strategy * .3 + naturalness * .25))

    def strlist(v, cap):
        if not isinstance(v, list):
            return []
        return [str(x).strip() for x in v if str(x).strip()][:cap]

    return {
        "overall": overall,
        "dimensions": {
            "appropriateness": appropriateness,
            "strategy": strategy,
            "naturalness": naturalness,
        },
        "comment": str(data.get("comment", "")).strip() or "已完成评分。",
        "used": strlist(data.get("used"), 5),
        "suggestions": strlist(data.get("suggestions"), 4) or ["继续保持，可以对照参考答案再体会措辞差异。"],
        "improved": str(data.get("improved", "")).strip(),
        "engine": "llm",
    }


# ===========================================================================
# 四、积分换算
# ===========================================================================
def points_for(overall: int, streak: int) -> dict:
    """
    把得分换算成积分。

    规则（与用户确认过的档位制）：
        80 分以上   -> 5 分
        60-79 分    -> 3 分
        60 分以下   -> 1 分（参与就有分，不打击人）
    连续打卡加成：
        连续 7 天及以上 -> 额外 +2
        连续 3 天及以上 -> 额外 +1

    返回:
        {"base": 基础分, "bonus": 打卡加成, "total": 合计, "reason": 说明文字}
    """
    if overall >= 80:
        base, tier = 5, "优秀"
    elif overall >= 60:
        base, tier = 3, "良好"
    else:
        base, tier = 1, "参与"

    if streak >= 7:
        bonus, btext = 2, "连续打卡 7 天以上 +2"
    elif streak >= 3:
        bonus, btext = 1, "连续打卡 3 天以上 +1"
    else:
        bonus, btext = 0, ""

    reason = f"{tier}（{overall} 分）+{base}"
    if btext:
        reason += f"，{btext}"

    return {"base": base, "bonus": bonus, "total": base + bonus, "reason": reason}
