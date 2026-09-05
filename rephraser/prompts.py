# -*- coding: utf-8 -*-
"""
prompts.py —— 给大模型的提示词（Prompt）模板

【这个文件为什么重要？】
改写质量的 80% 取决于提示词写得好不好。
这里把"语用学研究者"的专业要求写死在提示词里，包括：
  · Brown & Levinson 的面子理论（正面礼貌 / 负面礼貌 / 非公开施为）
  · 五档礼貌程度各自的具体定义（从 config.py 的 desc 字段读取）
  · 语义不变原则（只改语用表达，不改核心意图）
  · 强制返回 JSON 格式，方便程序解析

如果你以后想调整改写风格，改这个文件即可，不用动其他代码。
"""

from .config import get_scene, get_language


# ---------------------------------------------------------------------------
# 系统提示词：设定模型的身份和总体规则
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """你是一位专攻语用学（Pragmatics）的语言学研究者，长期在香港从事社会语言学与礼貌理论研究。
你的任务是把用户给出的句子，改写成若干个"核心语义完全相同、但礼貌程度与语用策略不同"的版本，用于语用学教学与研究对比。

你必须严格遵守以下原则：
1. 【语义不变】所有版本必须保留原句的核心命题意义和交际意图，不得增加或删减实质信息。
2. 【自然真实】改写结果必须是母语者真实会说出口的话，不得机械堆砌敬语，也不得为了显得粗鲁而硬塞脏话或攻击性词汇。
3. 【档位区分】相邻两档之间必须有可观察的语言形式差异（句式、称呼、敬称、缓冲语、模糊限制语、情态词等），不能只是换几个同义词。
4. 【语域一致】改写结果必须完全使用指定的目标语言书写；若目标语言是香港粤语，须使用繁体字并采用粤语口语词（係、唔、嘅、咗、喺、佢、啲 等），不得写成标准汉语。
5. 【解读专业】每个版本都要给出两段简短的中文分析：
   - feature（语言特征）：指出使用了哪些具体语言手段，如祈使句、疑问句、敬称、称呼语、模糊限制语、致歉性缓冲语、情态动词等。
   - strategy（语用特征）：指出体现了哪种语用策略（正面礼貌策略 / 负面礼貌策略 / 公开直接施为 / 非公开施为等）及其社交效果。
   两段分析各控制在 20 到 30 个汉字之间，务必精炼、专业、不说空话。

你的回答必须是一个合法的 json 对象，不要输出任何解释性文字、不要使用 markdown 代码块包裹。"""


def build_user_prompt(text: str, scene_key: str, target_lang_key: str, styles: list) -> str:
    """
    组装发给大模型的用户提示词。

    参数:
        text            : 用户输入的原始文本
        scene_key       : 场景 key，如 'boss'
        target_lang_key : 目标语言 key，如 'zh'
        styles          : 本次要生成的风格列表（五档 或 五档+两种特殊风格）
    返回:
        str —— 完整的用户提示词
    """
    scene = get_scene(scene_key)
    lang = get_language(target_lang_key)

    # 把每一档的要求逐条列出来，让模型清楚每个 key 该写成什么样
    style_lines = []
    for idx, s in enumerate(styles, start=1):
        style_lines.append(
            f'  {idx}. key="{s["key"]}"（{s["zh"]} / {s["en"]}）：{s["desc"]}'
        )
    style_block = "\n".join(style_lines)

    # 期望的 JSON 结构示例（给模型一个明确的靶子）
    example_keys = ", ".join(f'"{s["key"]}"' for s in styles)

    prompt = f"""请对下面这句话进行语用改写。

【原始文本】
{text}

【交际场景】
{scene["label"]}（{scene["en"]}）
社会关系说明：{scene["relation"]}

【目标语言】
{lang["label"]}（{lang["en"]}）—— 所有改写结果都必须用这种语言写。

【需要生成的版本，共 {len(styles)} 个】
{style_block}

【输出格式要求】
只返回一个 json 对象，结构如下（versions 数组必须按上面给出的顺序，且 key 必须严格是 {example_keys}）：

{{
  "versions": [
    {{
      "key": "版本标识",
      "text": "该档位的改写结果（目标语言）",
      "feature": "语言特征分析，20-30个汉字",
      "strategy": "语用特征与社交效果分析，20-30个汉字"
    }}
  ]
}}"""
    return prompt


def build_messages(text: str, scene_key: str, target_lang_key: str, styles: list) -> list:
    """把系统提示词和用户提示词打包成 OpenAI 兼容接口需要的 messages 列表。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(text, scene_key, target_lang_key, styles)},
    ]
