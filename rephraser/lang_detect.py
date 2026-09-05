# -*- coding: utf-8 -*-
"""
lang_detect.py —— 输入文本的语言自动识别

【设计思路】
本项目只需要区分四种语言，而且其中两种（普通话 / 香港粤语）同属汉语，
通用的语言识别库（如 langdetect）反而分不出粤语。
所以这里用"特征词 + 字符范围"的规则法，完全离线、零依赖、速度极快。

【判断优先级】
  1. 先看有没有粤语特征字词  -> 香港粤语 (yue)
  2. 再看有没有大量汉字      -> 普通话汉语 (zh)
  3. 再看有没有法语特征      -> 法语 (fr)
  4. 剩下的拉丁字母文本      -> 英语 (en)

【已知局限（请务必知悉）】
  · 很短的句子（如"你好"）在普通话/粤语之间可能误判；
  · 不带重音符号书写的法语，可能被判成英语。
  因此前端在每条历史记录上提供了"手动修正语言"的小按钮作为补救。
"""

import re

# ---------------------------------------------------------------------------
# 粤语特征字/词表
# 这些字词几乎只出现在粤语书面语中，命中任意一个即可判定为粤语
# ---------------------------------------------------------------------------
CANTONESE_MARKERS = [
    # 高频功能词
    "係", "唔", "咗", "嘅", "喺", "佢", "哋", "冇", "睇", "嗰", "呢個", "乜嘢",
    "點解", "邊個", "邊度", "幾時", "而家", "噉", "嚟", "咁", "啲", "嘢",
    # 语气词
    "㗎", "喇", "囉", "啩", "嘞", "咩", "呀嘛", "嘞喎",
    # 常见搭配
    "唔該", "多謝晒", "得唔得", "有冇", "唔使", "唔好意思", "食飯", "傾偈",
    "唔知", "同你", "畀我", "幫手",
]

# ---------------------------------------------------------------------------
# 法语特征
# ---------------------------------------------------------------------------
# (1) 法语特有的重音字符 —— 命中即强烈提示法语
FRENCH_ACCENTS = set("éèêëàâçùûôîïœÉÈÊËÀÂÇÙÛÔÎÏŒ")

# (2) 法语高频虚词 —— 用于没有重音符号时的兜底判断
FRENCH_WORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "est", "vous",
    "je", "tu", "il", "elle", "nous", "ils", "ne", "pas", "que", "qui", "pour",
    "avec", "dans", "sur", "mais", "aussi", "votre", "vos", "mon", "ma", "mes",
    "s'il", "plait", "plaît", "merci", "bonjour", "pourriez", "auriez", "besoin",
    "aide", "aider", "faire", "peux", "peut", "suis", "sont", "être", "avoir",
}

# (3) 英语高频虚词 —— 与法语做对比投票
ENGLISH_WORDS = {
    "the", "a", "an", "is", "are", "am", "you", "i", "he", "she", "we", "they",
    "to", "of", "and", "in", "on", "for", "with", "but", "not", "do", "does",
    "please", "thanks", "thank", "help", "need", "want", "could", "would",
    "can", "may", "your", "my", "this", "that", "it", "have", "has", "be",
}


def _count_cjk(text: str) -> int:
    """数一数文本里有多少个汉字（CJK 统一表意文字区间）。"""
    return len(re.findall(r"[一-鿿]", text))


def detect_language(text: str) -> str:
    """
    识别输入文本的语言。

    参数:
        text: 用户输入的原始文本
    返回:
        'yue' 香港粤语 / 'zh' 普通话汉语 / 'fr' 法语 / 'en' 英语 / 'unknown' 无法判断
    """
    if not text or not text.strip():
        return "unknown"

    # ---------- 第 1 步：粤语特征检测 ----------
    # 只要命中任意一个粤语标记词，就判定为粤语
    for marker in CANTONESE_MARKERS:
        if marker in text:
            return "yue"

    # ---------- 第 2 步：汉字数量检测 ----------
    cjk_count = _count_cjk(text)
    if cjk_count >= 1:
        # 有汉字但没命中粤语特征 -> 判定为普通话
        # （繁体字本身不能作为粤语依据，因为台湾、香港的书面语也可能是标准汉语）
        return "zh"

    # ---------- 第 3 步：法语重音字符检测 ----------
    if any(ch in FRENCH_ACCENTS for ch in text):
        return "fr"

    # ---------- 第 4 步：英法虚词投票 ----------
    # 把文本切成小写单词，分别统计命中英语词表和法语词表的数量
    words = re.findall(r"[a-zA-Z']+", text.lower())
    if not words:
        return "unknown"

    fr_hits = sum(1 for w in words if w in FRENCH_WORDS)
    en_hits = sum(1 for w in words if w in ENGLISH_WORDS)

    if fr_hits > en_hits:
        return "fr"
    if en_hits > 0 or words:
        # 有拉丁字母但法语特征不明显 -> 默认英语
        return "en"

    return "unknown"


# ---------------------------------------------------------------------------
# 直接运行本文件可以做个小测试： python -m rephraser.lang_detect
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    samples = [
        "我现在需要你的帮助",
        "我而家需要你嘅幫助",
        "I need your help right now",
        "J'ai besoin de votre aide maintenant",
        "Pourriez vous m aider",
    ]
    for s in samples:
        print(f"{detect_language(s):>8}  <-  {s}")
