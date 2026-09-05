# -*- coding: utf-8 -*-
"""
rephraser 包 —— 泡泡改写的核心逻辑层

把 Python 逻辑集中放在这个包里，app.py 只负责"接收请求、调用逻辑、返回结果"，
这样代码结构清晰，以后想换 Web 框架也不用重写逻辑。

包内各模块职责：
    config.py         常量配置（场景、语言、七档风格、颜色）
    lang_detect.py    输入文本的语言自动识别
    prompts.py        给大模型的提示词模板
    llm_client.py     A 轨引擎：调用 DeepSeek 等大模型
    offline_engine.py B 轨引擎：内置语用模板，无需联网
"""

__version__ = "1.0.0"
__app_name__ = "泡泡改写 2P Rephraser"
