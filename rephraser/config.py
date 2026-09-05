# -*- coding: utf-8 -*-
"""
config.py —— 全局常量配置文件

这个文件不含任何逻辑，只存放"整个项目都要用到的固定数据"：
  1. 应用场景（SCENES）
  2. 目标语言（TARGET_LANGUAGES）
  3. 五档礼貌程度（POLITENESS_LEVELS）
  4. 两种特殊语用风格（SPECIAL_STYLES）
  5. 一些数字限制（字数上限、解锁积分等）

【为什么单独抽一个文件？】
因为后端 Python 和前端 JavaScript 都要用到这批数据。
把它们集中放在这里，前端通过 /api/config 接口读取，
以后要加一个场景或改一个颜色，只需要改这一个文件，前后端同时生效。
"""

# ---------------------------------------------------------------------------
# 一、基础数字限制
# ---------------------------------------------------------------------------

# 输入框最长字符数（需求：限制最长 200 字符）
MAX_INPUT_LENGTH = 200

# 解锁"对待事务机构或陌生人"场景所需的积分
UNLOCK_POINTS = 10

# 浏览器 localStorage 容量约 5MB，历史记录设一个上限，超出后自动淘汰最旧的
MAX_HISTORY_ITEMS = 200


# ---------------------------------------------------------------------------
# 二、应用场景（下拉框第一项）
# ---------------------------------------------------------------------------
# key      : 程序内部用的英文标识，不会显示给用户
# label    : 下拉框里显示的中文名
# en       : 英文名，写进给大模型的提示词里，帮助模型理解场景
# relation : 社会关系描述，用于提示词，让模型准确把握权势(power)与距离(distance)
# locked_by: 需要多少积分才能解锁；None 表示一开始就可用
SCENES = [
    {
        "key": "peer",
        "label": "同事平级之间",
        "en": "Between peer colleagues (equal power, low distance)",
        "relation": "双方地位平等、关系较熟悉，属于低权势差、低社会距离",
        "locked_by": None,
    },
    {
        "key": "boss",
        "label": "对待上司",
        "en": "Speaking to one's boss / supervisor (听话人权势更高)",
        "relation": "听话人地位高于说话人，属于高权势差、中等社会距离",
        "locked_by": None,
    },
    {
        "key": "teacher",
        "label": "对待师长",
        "en": "Speaking to a teacher / professor / elder",
        "relation": "听话人是师长长辈，权势与尊敬度高，中文语境需体现尊师传统",
        "locked_by": None,
    },
    {
        "key": "stranger",
        "label": "对待事务机构或陌生人",
        "en": "Speaking to an institution / civil servant / stranger",
        "relation": "双方不熟悉，属于高社会距离，需要用正式、公事化的语域",
        # 需求：初始锁定，积分 >= 10 后自动解锁
        "locked_by": UNLOCK_POINTS,
    },
]


# ---------------------------------------------------------------------------
# 三、目标语言（下拉框第二项）
# ---------------------------------------------------------------------------
# key   : 内部标识
# label : 中文显示名
# en    : 英文名（写进提示词）
# flag  : 国旗/地区旗 emoji，用于历史记录页面的方块
SCENE_KEYS = [s["key"] for s in SCENES]

TARGET_LANGUAGES = [
    {"key": "zh", "label": "普通话汉语", "en": "Mandarin Chinese (Simplified)", "flag": "🇨🇳"},
    {"key": "yue", "label": "香港粤语", "en": "Hong Kong Cantonese (Traditional)", "flag": "🇭🇰"},
    {"key": "en", "label": "英语", "en": "English", "flag": "🇬🇧"},
    {"key": "fr", "label": "法语", "en": "French", "flag": "🇫🇷"},
]

LANGUAGE_KEYS = [l["key"] for l in TARGET_LANGUAGES]

# 语言识别结果 -> 中文显示名（历史记录里标注"原文语言"用）
LANGUAGE_LABELS = {l["key"]: l["label"] for l in TARGET_LANGUAGES}
LANGUAGE_LABELS["unknown"] = "未识别"


# ---------------------------------------------------------------------------
# 四、五档礼貌程度（核心！从最粗鲁到最礼貌）
# ---------------------------------------------------------------------------
# key   : 内部标识
# zh    : 中文命名
# en    : 英文命名（需求要求中英双语）
# color : 色条颜色，从红（粗鲁）渐变到绿（委婉）
# desc  : 写进提示词，告诉大模型这一档到底该长什么样
POLITENESS_LEVELS = [
    {
        "key": "very_direct",
        "zh": "非常直接",
        "en": "Very Direct / Imperative & Rude",
        "color": "#C0392B",  # 红
        "desc": "赤裸裸的祈使句，没有称呼语、没有敬语、没有任何缓冲成分，语气生硬甚至带催促，公开威胁听话人面子",
    },
    {
        "key": "direct",
        "zh": "比较直接",
        "en": "Direct / Blunt",
        "color": "#E67E22",  # 橙
        "desc": "平铺直叙的陈述句，中性词汇，既不礼貌也不粗鲁，不使用任何礼貌策略",
    },
    {
        "key": "polite_request",
        "zh": "比较礼貌",
        "en": "Polite Request",
        "color": "#D4A017",  # 黄
        "desc": "加入称呼语和敬称，使用基本的请求标记（请/麻烦/could you），体现正面礼貌策略、拉近距离",
    },
    {
        "key": "respectful",
        "zh": "礼貌",
        "en": "Respectful / Courteous",
        "color": "#7FA650",  # 黄绿
        "desc": "疑问句式，称呼语＋敬称＋致歉性缓冲语（不好意思/打扰一下），询问对方是否方便，体现负面礼貌策略、尊重对方自主权",
    },
    {
        "key": "indirect",
        "zh": "委婉",
        "en": "Indirect / Tactful / Implicative",
        "color": "#2E8B57",  # 绿
        "desc": "间接引发式表达，用模糊限制语和话题铺垫把请求隐含在陈述里，让听话人自行推导言外之意，属于非公开施为行为",
    },
]

LEVEL_KEYS = [lv["key"] for lv in POLITENESS_LEVELS]


# ---------------------------------------------------------------------------
# 五、特殊语用风格（可勾选的附加第 6、7 条，分开呈现）
# ---------------------------------------------------------------------------
SPECIAL_STYLES = [
    {
        "key": "assertive",
        "zh": "强硬",
        "en": "Assertive / Forceful",
        "color": "#7D5BA6",  # 紫
        "desc": "保留基本礼貌形式（称呼、敬称）但语气坚决，使用情态必要性词（必须/需要/have to），强调事情的紧迫性与不可退让",
    },
    {
        "key": "coaxing",
        "zh": "撒娇",
        "en": "Coaxing / Endearing",
        "color": "#D96BA0",  # 粉
        "desc": "使用亲昵称呼、语气词、叠词和延长音，句末上扬，靠亲密关系抵消请求的强加性，属于高度正面礼貌策略",
    },
]

SPECIAL_KEYS = [s["key"] for s in SPECIAL_STYLES]

# 把五档 + 两种特殊风格合并成一张查找表，方便按 key 取颜色和名称
ALL_STYLES = {item["key"]: item for item in (POLITENESS_LEVELS + SPECIAL_STYLES)}


def build_style_list(include_special: bool):
    """
    根据用户是否勾选"附加语用变体"，返回本次需要生成的风格列表。

    参数:
        include_special: True 表示额外生成"强硬"和"撒娇"两条
    返回:
        list[dict] —— 顺序即页面上卡片从上到下的顺序
    """
    styles = list(POLITENESS_LEVELS)
    if include_special:
        styles = styles + list(SPECIAL_STYLES)
    return styles


def get_scene(key: str):
    """按 key 查找场景配置，找不到返回 None。"""
    for s in SCENES:
        if s["key"] == key:
            return s
    return None


def get_language(key: str):
    """按 key 查找语言配置，找不到返回 None。"""
    for l in TARGET_LANGUAGES:
        if l["key"] == key:
            return l
    return None


def public_config():
    """
    整理一份"可以安全暴露给前端"的配置。
    注意：这里故意不包含 desc 字段（那是给大模型看的提示词，前端用不上），
    也绝不包含任何 API Key。
    """
    return {
        "maxInputLength": MAX_INPUT_LENGTH,
        "unlockPoints": UNLOCK_POINTS,
        "maxHistoryItems": MAX_HISTORY_ITEMS,
        "scenes": [
            {"key": s["key"], "label": s["label"], "lockedBy": s["locked_by"]}
            for s in SCENES
        ],
        "languages": [
            {"key": l["key"], "label": l["label"], "flag": l["flag"]}
            for l in TARGET_LANGUAGES
        ],
        "levels": [
            {"key": lv["key"], "zh": lv["zh"], "en": lv["en"], "color": lv["color"]}
            for lv in POLITENESS_LEVELS
        ],
        "specials": [
            {"key": sp["key"], "zh": sp["zh"], "en": sp["en"], "color": sp["color"]}
            for sp in SPECIAL_STYLES
        ],
    }
