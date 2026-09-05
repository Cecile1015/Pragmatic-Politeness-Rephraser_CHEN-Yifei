# -*- coding: utf-8 -*-
"""
offline_engine.py —— 离线模板改写引擎（B 轨引擎）

【它的作用】
当 .env 里没有配置 API Key 时（或大模型调用失败时），由这个模块兜底，
保证任何人 clone 下来这个项目、什么都不配置，也能立刻看到完整效果。

【实现原理】
不是"翻译"，而是"语用要素的组合"：
    称呼语 + 缓冲语 + 句式转换 + 模糊限制语 + 句末标记
按照五档礼貌程度各自的公式，把用户原句包裹进不同的语用框架里。

【必须坦白的能力边界（很重要）】
  · 普通话 (zh)：覆盖最好，能处理任意输入句。
  · 香港粤语 (yue)：先用词汇对照表把普通话转成粤语用词，再套框架。
    对常见句子够用，遇到复杂句会有生硬的地方。
  · 英语 (en) / 法语 (fr)：离线状态下无法真正翻译中文。
    这里采用"意图识别 + 预置语用框架"的方案：先判断输入属于哪一类交际意图
    （求助 / 约见 / 催促 / 通用），再输出该意图下地道的英文/法文五档表达。
    结果在语用学上是准确的示例，但不保证与你的原句逐字对应。
    ==> 要得到真正贴合原句的英/法改写，请配置 API Key 走大模型引擎。
"""

import re

from .config import ALL_STYLES


# ===========================================================================
# 一、各档位的固定语用学解读（中文，两段各 20-30 字）
#     离线模式下解读是预置的，因为规则法无法真正"分析"句子
# ===========================================================================
ANALYSIS = {
    "very_direct": (
        "祈使句式，无称呼语与敬语，缺少任何缓冲成分。",
        "公开威胁听话人消极面子，凸显权势不对等中的强势姿态。",
    ),
    "direct": (
        "直陈句，中性词汇，既无敬称也无软化标记。",
        "未采取明显礼貌策略，属于最直白的公开施为行为。",
    ),
    "polite_request": (
        "加入称呼语与敬称，动词前带明确的请求标记。",
        "正面礼貌策略，通过认同对方身份拉近距离、降低冒犯度。",
    ),
    "respectful": (
        "疑问句式，称呼语＋敬称＋致歉性缓冲语前置。",
        "负面礼貌策略，尊重对方自主权，给足对方拒绝的余地。",
    ),
    "indirect": (
        "间接引发式表达，使用模糊限制语与话题铺垫。",
        "非公开施为，把请求隐含在陈述中，双方面子风险最低。",
    ),
    "assertive": (
        "陈述句＋情态必要性词，保留敬称但语气坚定。",
        "以牺牲部分消极面子换取执行力，强调事务的紧迫性。",
    ),
    "coaxing": (
        "亲昵称呼、语气词与延长音，句末语调上扬。",
        "高度正面礼貌策略，靠亲密关系抵消请求的强加性。",
    ),
}


# ===========================================================================
# 二、普通话（zh）改写
# ===========================================================================

# 不同场景下的称呼语与人称代词
ZH_SCENE = {
    #                称呼语        敬称代词
    "peer":     {"addr": "",       "pron": "你"},
    "boss":     {"addr": "老板",   "pron": "您"},
    "teacher":  {"addr": "老师",   "pron": "您"},
    "stranger": {"addr": "您好",   "pron": "您"},
}


def _strip_end_punct(text: str) -> str:
    """去掉句末的标点，方便我们自己拼接语气。"""
    return re.sub(r"[。！？!?.、，,；;\s]+$", "", text.strip())


def _is_question(text: str) -> bool:
    """
    粗略判断输入是不是一个疑问句。

    【为什么要判断？】
    "帮我拿一下文件"（祈使）和"你什么时候有空"（疑问）需要套用不同的语用框架，
    否则会拼出"麻烦你，你什么时候有空，谢谢"这种不自然的句子。
    """
    if re.search(r"[？?]\s*$", text.strip()):
        return True
    markers = ["吗", "嗎", "呢", "什么", "乜嘢", "怎么", "點樣", "为什么", "點解",
               "哪", "邊", "谁", "邊個", "几时", "幾時", "是否", "多少", "能不能",
               "可不可以", "有没有", "有冇", "係咪", "定係", "得唔得", "好唔好"]
    return any(m in text for m in markers)


def _to_honorific(text: str, pron: str) -> str:
    """
    把句子里的"你"换成"您"（只在需要敬称的场景下调用）。
    注意要先处理"你们"，避免变成"您们"这种不自然的说法。
    """
    if pron != "您":
        return text
    text = text.replace("你们", "大家")
    text = text.replace("你", "您")
    return text


def _rephrase_zh(core: str, scene_key: str) -> dict:
    """生成普通话的七档表达（五档 + 两种特殊风格）。"""
    cfg = ZH_SCENE.get(scene_key, ZH_SCENE["peer"])
    pron = cfg["pron"]

    plain = _strip_end_punct(core)              # 去掉句末标点的原句
    polite = _to_honorific(plain, pron)         # 把"你"换成"您"的版本

    # 各档的称呼语前缀（平级场景没有称呼语，改用"麻烦你"这种请求标记）
    if scene_key == "peer":
        addr3 = "麻烦你"
        addr4 = "不好意思"
        addr5 = "跟你说个事儿"
        addr6 = "说实话"
        addr7 = "欸"
    elif scene_key == "stranger":
        addr3 = "您好，麻烦您"
        addr4 = "您好，不好意思打扰一下"
        addr5 = "您好，我这边有个情况想咨询一下"
        addr6 = "您好，这件事比较紧急"
        addr7 = "您好呀"
    else:
        addr = cfg["addr"]                      # 老板 / 老师
        addr3 = addr
        addr4 = f"{addr}，不好意思打扰您一下"
        addr5 = f"{addr}，我这边有件事想跟您说一下"
        addr6 = f"{addr}，这件事比较紧急"
        addr7 = f"{addr}～"

    # 疑问句和祈使句要套用不同的框架，否则会拼出很别扭的句子
    if _is_question(plain):
        return {
            "very_direct": f"{plain}？快回我。",
            "direct": f"{plain}？",
            "polite_request": f"{addr3}，想问一下，{polite}？",
            "respectful": f"{addr4}，想跟{pron}请教一下，{polite}？",
            "indirect": f"{addr5}——{polite}？{pron}方便的时候回我一声就行。",
            "assertive": f"{addr6}，{polite}？希望今天之内能有个明确答复。",
            "coaxing": f"{addr7}{polite}呀？告诉我嘛～",
        }

    return {
        # 1 非常直接：祈使 + 催促，无任何缓冲
        "very_direct": f"{plain}，快点。",
        # 2 比较直接：原句直陈，中性
        "direct": f"{plain}。",
        # 3 比较礼貌：称呼语 + 敬称 + 致谢
        "polite_request": f"{addr3}，{polite}，谢谢。",
        # 4 礼貌：致歉缓冲 + 疑问句 + 询问是否方便
        "respectful": f"{addr4}，{polite}，不知道{pron}方不方便？",
        # 5 委婉：话题铺垫 + 模糊限制语，把请求隐含在陈述里
        "indirect": f"{addr5}——{polite}，{pron}看什么时候合适？",
        # 6 强硬：保留敬称但用情态必要性词
        "assertive": f"{addr6}，{polite}，希望今天之内能有个结果。",
        # 7 撒娇：语气词 + 延长音 + 亲昵请求
        "coaxing": f"{addr7}{polite}嘛，就帮我这一次，拜托啦～",
    }


# ===========================================================================
# 三、香港粤语（yue）改写
# ===========================================================================

# 普通话 -> 粤语词汇对照表
# 注意顺序：长词必须排在短词前面，否则"你们"会先被"你"替换掉
ZH_TO_YUE = [
    ("为什么", "點解"), ("怎么样", "點樣"), ("怎么", "點樣"),
    ("什么时候", "幾時"), ("什么", "乜嘢"), ("哪里", "邊度"), ("哪个", "邊個"),
    ("我们", "我哋"), ("你们", "你哋"), ("他们", "佢哋"), ("她们", "佢哋"),
    ("这个", "呢個"), ("那个", "嗰個"), ("这里", "呢度"), ("那里", "嗰度"),
    ("这样", "咁"), ("现在", "而家"), ("知道", "知"),
    ("没有", "冇"), ("可以吗", "得唔得"), ("好吗", "好唔好"),
    ("谢谢", "多謝"), ("帮忙", "幫手"), ("时间", "時間"),
    ("一下", "一陣"), ("的", "嘅"), ("是", "係"), ("不", "唔"),
    ("没", "冇"), ("很", "好"), ("在", "喺"), ("和", "同"),
    ("给", "畀"), ("说", "講"), ("看", "睇"), ("来", "嚟"),
    ("帮", "幫"), ("他", "佢"), ("她", "佢"), ("吗", "嗎"),
    ("们", "哋"), ("个", "個"), ("会", "會"), ("对", "對"),
    ("师", "師"), ("间", "間"), ("问", "問"), ("题", "題"),
    ("话", "話"), ("请", "請"), ("边", "邊"), ("处", "處"),
    ("业", "業"), ("务", "務"), ("学", "學"), ("习", "習"),
]

YUE_SCENE = {
    "peer":     "",
    "boss":     "老細",
    "teacher":  "老師",
    "stranger": "唔好意思",
}


# ---------------------------------------------------------------------------
# 简体转繁体：香港粤语必须用繁体字书写
# 优先使用 OpenCC 库（转换质量最好，且用的是香港标准字形 s2hk）；
# 没装这个库也不影响运行，只是上面对照表没覆盖到的字会保持简体。
# ---------------------------------------------------------------------------
try:
    from opencc import OpenCC
    _CC = OpenCC("s2hk")            # s2hk = 简体 -> 香港繁体
except Exception:                    # 库没装、或初始化失败
    _CC = None


def _to_traditional(text: str) -> str:
    """把简体字转成香港繁体字；没有 OpenCC 时原样返回。"""
    if _CC is None:
        return text
    try:
        return _CC.convert(text)
    except Exception:
        return text


def _to_cantonese(text: str) -> str:
    """
    把普通话文本粗略转成粤语书面语。

    分两步：
      1. 用词汇对照表替换普通话特有的词（的->嘅、是->係、现在->而家……）
      2. 再用 OpenCC 把剩下的简体字统一转成香港繁体
    """
    out = text
    for zh, yue in ZH_TO_YUE:
        out = out.replace(zh, yue)
    return _to_traditional(out)


def _rephrase_yue(core: str, scene_key: str) -> dict:
    """生成香港粤语的七档表达。"""
    plain = _to_cantonese(_strip_end_punct(core))
    addr = YUE_SCENE.get(scene_key, "")
    # 有称呼语时加逗号，没有就留空
    a = f"{addr}，" if addr else ""

    # 同样区分疑问句与祈使句
    if _is_question(plain):
        return {
            "very_direct": f"{plain}？快啲覆我。",
            "direct": f"{plain}？",
            "polite_request": f"{a}想問吓，{plain}？",
            "respectful": f"{a}唔好意思，想請教吓，{plain}？",
            "indirect": f"{a}{plain}？你得閒嘅時候覆我一聲就得㗎喇。",
            "assertive": f"{a}{plain}？希望今日之內有個確實嘅答覆。",
            "coaxing": f"{a}{plain}呀？話我知啦～",
        }

    return {
        "very_direct": f"{plain}，快啲。",
        "direct": f"{plain}。",
        "polite_request": f"{a}{plain}，唔該晒。",
        "respectful": f"{a}唔好意思阻你一陣，{plain}，唔知方唔方便呢？",
        "indirect": f"{a}我有件事想同你講吓——{plain}，你睇下幾時得閒？",
        "assertive": f"{a}件事幾急，{plain}，希望今日之內搞掂。",
        "coaxing": f"{a}{plain}啦～幫吓我啦，唔該晒你～",
    }


# ===========================================================================
# 四、英语（en）/ 法语（fr）改写 —— 意图识别 + 预置语用框架
# ===========================================================================

# 四类常见交际意图的关键词
INTENT_KEYWORDS = {
    "help":    ["帮", "幫", "协助", "協助", "支持", "忙", "help", "assist", "aide", "aider"],
    "meeting": ["见面", "見面", "约", "約", "开会", "開會", "见", "見", "时间", "時間",
                "聊", "谈", "談", "meet", "meeting", "appointment", "rendez"],
    "urge":    ["快", "尽快", "盡快", "催", "赶", "趕", "急", "什么时候好", "hurry", "asap",
                "urgent", "vite", "dépêch"],
}


def detect_intent(text: str) -> str:
    """
    粗略判断输入属于哪一类交际意图。
    只用于离线模式下的英语/法语输出，命中不了就返回 'generic'。
    """
    low = text.lower()
    # 注意判断顺序：先催促、再求助、最后约见，避免"帮我快点"被判成 help
    for intent in ("urge", "help", "meeting"):
        for kw in INTENT_KEYWORDS[intent]:
            if kw in low:
                return intent
    return "generic"


# 英语：意图 -> 七档表达
EN_TEMPLATES = {
    "help": {
        "very_direct": "Help me. Now.",
        "direct": "I need your help right now.",
        "polite_request": "Could you help me with something?",
        "respectful": "Sorry to bother you — would you have a moment to give me a hand?",
        "indirect": "I'm still working through this, and your input would really help whenever you have time.",
        "assertive": "I need this sorted today, so I'll have to ask for your help on it.",
        "coaxing": "Pretty please — could you rescue me on this one?",
    },
    "meeting": {
        "very_direct": "Come and see me. Now.",
        "direct": "I need to meet with you.",
        "polite_request": "Could we find a time to meet?",
        "respectful": "Sorry to intrude — would you happen to have a moment this week to meet?",
        "indirect": "There's something I'd like to talk through, whenever your schedule allows.",
        "assertive": "We do need to meet on this today.",
        "coaxing": "Any chance you could squeeze me in? I'd be so grateful!",
    },
    "urge": {
        "very_direct": "Hurry up.",
        "direct": "I need this done soon.",
        "polite_request": "Could you get to this soon, please?",
        "respectful": "Sorry to chase — would it be possible to have this a little sooner?",
        "indirect": "I'm just checking in on the timing, in case anything is holding it up.",
        "assertive": "This is time-critical, and I'll need it by the end of today.",
        "coaxing": "Please please please — could you bump this up the list for me?",
    },
    "generic": {
        "very_direct": "Just do it.",
        "direct": "I'd like this handled.",
        "polite_request": "Could you take care of this, please?",
        "respectful": "Sorry to trouble you — would you mind taking a look at this?",
        "indirect": "I wanted to flag this, in case it's something you'd like to weigh in on.",
        "assertive": "This does need to be dealt with, and I'd like it done today.",
        "coaxing": "Would you be an absolute star and sort this out for me?",
    },
}

# 法语：意图 -> 七档表达
FR_TEMPLATES = {
    "help": {
        "very_direct": "Aide-moi. Tout de suite.",
        "direct": "J'ai besoin de ton aide maintenant.",
        "polite_request": "Pourriez-vous m'aider, s'il vous plaît ?",
        "respectful": "Excusez-moi de vous déranger — auriez-vous un moment pour me donner un coup de main ?",
        "indirect": "J'y réfléchis encore, et votre avis me serait très précieux quand vous aurez le temps.",
        "assertive": "Il faut que ce soit réglé aujourd'hui, j'ai donc besoin de votre aide.",
        "coaxing": "S'il vous plaît, vous seriez vraiment mon sauveur sur ce coup-là !",
    },
    "meeting": {
        "very_direct": "Viens me voir. Tout de suite.",
        "direct": "J'ai besoin de te voir.",
        "polite_request": "Pourrions-nous convenir d'un rendez-vous ?",
        "respectful": "Excusez-moi — auriez-vous un moment cette semaine pour que nous en parlions ?",
        "indirect": "Il y a un point que j'aimerais aborder, quand votre emploi du temps le permettra.",
        "assertive": "Il faut vraiment que nous en parlions aujourd'hui.",
        "coaxing": "Vous pourriez me glisser dans votre agenda ? Ce serait adorable !",
    },
    "urge": {
        "very_direct": "Dépêche-toi.",
        "direct": "J'en ai besoin rapidement.",
        "polite_request": "Pourriez-vous vous en occuper bientôt, s'il vous plaît ?",
        "respectful": "Désolé d'insister — serait-il possible de l'avoir un peu plus tôt ?",
        "indirect": "Je me permets de faire le point sur le calendrier, au cas où quelque chose bloquerait.",
        "assertive": "C'est urgent : il me le faut d'ici la fin de la journée.",
        "coaxing": "S'il vous plaît, vous pourriez le faire passer en priorité pour moi ?",
    },
    "generic": {
        "very_direct": "Fais-le.",
        "direct": "J'aimerais que ce soit traité.",
        "polite_request": "Pourriez-vous vous en charger, s'il vous plaît ?",
        "respectful": "Excusez-moi de vous déranger — verriez-vous un inconvénient à y jeter un œil ?",
        "indirect": "Je voulais vous en informer, au cas où vous souhaiteriez donner votre avis.",
        "assertive": "Cela doit être traité, et j'aimerais que ce soit fait aujourd'hui.",
        "coaxing": "Vous seriez un ange si vous pouviez vous en occuper !",
    },
}

# 场景 -> 西方语言的称呼语前缀
EN_SALUTATION = {"peer": "", "boss": "", "teacher": "Professor, ", "stranger": "Excuse me, "}
FR_SALUTATION = {"peer": "", "boss": "", "teacher": "Professeur, ", "stranger": "Bonjour, "}

# 只有礼貌档（3 及以上）才加称呼语，粗鲁档加了反而不自然
SALUTED_LEVELS = {"polite_request", "respectful", "indirect", "assertive", "coaxing"}


def _apply_salutation(sentence: str, salutation: str) -> str:
    """
    在句子前面加上称呼语，并把原句首字母改成小写，
    避免出现 "Professor, Could you..." 这种句中大写的错误。
    """
    if not salutation:
        return sentence
    if not sentence:
        return salutation
    return salutation + sentence[0].lower() + sentence[1:]


def _rephrase_western(core: str, scene_key: str, lang_key: str) -> dict:
    """生成英语或法语的七档表达。"""
    intent = detect_intent(core)
    templates = EN_TEMPLATES if lang_key == "en" else FR_TEMPLATES
    salutations = EN_SALUTATION if lang_key == "en" else FR_SALUTATION
    salutation = salutations.get(scene_key, "")

    table = templates[intent]
    out = {}
    for key, sentence in table.items():
        if key in SALUTED_LEVELS:
            out[key] = _apply_salutation(sentence, salutation)
        else:
            out[key] = sentence
    return out


# ===========================================================================
# 五、对外统一入口
# ===========================================================================

def rephrase(text: str, scene_key: str, target_lang_key: str, styles: list) -> list:
    """
    离线模板引擎的主函数，接口与 llm_client.rephrase 保持一致。

    参数:
        text            : 原始文本
        scene_key       : 场景 key
        target_lang_key : 目标语言 key
        styles          : 需要生成的风格列表
    返回:
        list[dict] —— 每项含 key / zh / en / color / text / feature / strategy
    """
    core = text.strip()

    # 根据目标语言选用对应的生成函数
    if target_lang_key == "zh":
        table = _rephrase_zh(core, scene_key)
    elif target_lang_key == "yue":
        table = _rephrase_yue(core, scene_key)
    else:  # 'en' 或 'fr'
        table = _rephrase_western(core, scene_key, target_lang_key)

    results = []
    for style in styles:
        key = style["key"]
        feature, strategy = ANALYSIS.get(key, ("—", "—"))
        results.append({
            "key": key,
            "zh": style["zh"],
            "en": style["en"],
            "color": style["color"],
            "text": table.get(key, core),
            "feature": feature,
            "strategy": strategy,
        })
    return results


def rephrase_map(text: str, scene_key: str, target_lang_key: str, styles: list) -> dict:
    """
    和 rephrase 一样，但返回的是 {key: 结果} 的字典。
    app.py 用它来补齐"大模型漏掉的档位"。
    """
    return {item["key"]: item for item in rephrase(text, scene_key, target_lang_key, styles)}


def offline_note(target_lang_key: str) -> str:
    """
    返回离线模式下要显示在页面顶部的提示文字。
    英/法两种语言的局限更大，所以提示更详细。
    """
    if target_lang_key in ("en", "fr"):
        return ("当前为「离线演示模式」：未检测到 API Key。"
                "英语/法语结果是按交际意图匹配的语用框架示例，未对原句逐句翻译，"
                "请勿直接当作研究数据使用。配置 API Key 后即可获得贴合原句的改写。")
    return ("当前为「离线演示模式」：未检测到 API Key，结果由内置语用模板生成，"
            "自然度不及大模型。配置 API Key 后可获得更自然的改写与逐句语用分析。")
