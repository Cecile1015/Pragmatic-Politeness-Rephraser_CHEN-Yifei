# -*- coding: utf-8 -*-
"""
challenges.py —— 语用挑战题库

【这个文件是什么】
"游戏交互"页面的全部题目。每一题给出一个真实生活中会让人卡壳的语境，
请用户自己写出他认为最得体的说法，然后由系统打分。

【选题原则】
每题都对应一个语用学上有研究价值的言语行为（speech act），
并且都是"面子威胁行为"（Face-Threatening Act）—— 也就是天然难说的话。
覆盖：异议、拒绝、请求、道歉、投诉、催促、坏消息、纠错、接受赞美等。

【每题的字段】
    id         唯一编号
    scene      对应的应用场景 key，与 config.SCENES 一致
    act        言语行为类型（中文），显示在题目上方作为标签
    context    情境描述——用户看到的题面
    goal       任务目标：这句话要同时做到什么
    difficulty 难度 1-3
    focus      这题考察的语用焦点，评分和讲解时会用到
    expect     离线评分时期望出现的语用手段（见 scoring.py 的检测器名称）
    avoid      离线评分时应当避免的表达方式
    reference  参考答案，一个可接受的说法（不是唯一正确答案）
    note       这一题的语用学讲解，答完后展示
"""

import hashlib
from datetime import date


CHALLENGES = [
    {
        "id": "c01", "scene": "boss", "act": "表达异议", "difficulty": 2,
        "context": "开会时老板提出一个方案，你认为有明显问题，需要当场表达不同意见。",
        "goal": "既让老板听懂你的顾虑，又不让他在众人面前下不来台。",
        "focus": "对上级的公开异议，是典型的高风险面子威胁行为，需要大量缓冲",
        "expect": ["address", "honorific", "hedge", "question", "reason"],
        "avoid": ["blunt_negation"],
        "reference": "老板，这个方向我理解。不过有一点我还没完全想透——如果客户那边的排期比预期晚，我们是不是需要留一个备选？",
        "note": "对上级表达异议时，母语者常用「我理解…不过…」的让步结构先承认对方的合理性，再用模糊限制语（好像、可能、还没想透）把批评降级为「我的困惑」，把面子威胁从对方转移到自己身上。",
    },
    {
        "id": "c02", "scene": "peer", "act": "拒绝请求", "difficulty": 2,
        "context": "同事第三次请你帮他做本该他自己完成的工作，你这周已经很忙了。",
        "goal": "明确拒绝，但不破坏以后还要合作的关系。",
        "focus": "拒绝是威胁对方正面面子的行为，需要理由与替代方案来补偿",
        "expect": ["apology", "reason", "alternative", "softener"],
        "avoid": ["blunt_negation"],
        "reference": "这周真的抽不开身，手上两个 deadline 撞一起了。要不我把上次那个模板发你？照着改会快很多。",
        "note": "有效的拒绝通常包含三个成分：致歉／遗憾表达、具体理由、替代补偿。只说「不行」会让对方觉得被否定的是他这个人，给了理由则把拒绝归因于外部情境。",
    },
    {
        "id": "c03", "scene": "teacher", "act": "催促", "difficulty": 3,
        "context": "你请导师写推荐信，deadline 还有三天，但他两周没回复你了。",
        "goal": "提醒他这件事，但不能显得你在质问或施压。",
        "focus": "向权势更高者催促，须把「催」伪装成「提供便利」或「确认信息」",
        "expect": ["address", "honorific", "apology", "hedge", "question"],
        "avoid": ["blunt_demand"],
        "reference": "老师您好，打扰了。推荐信的截止日期是这周五，我把学校的提交链接和我的简历再发您一份，方便您需要的时候取用。如果需要我补充任何材料，随时告诉我。",
        "note": "中文语境里对师长的催促极少直接出现「催」的语义。常见策略是提供工具性帮助（重发材料、附上链接），让提醒隐含在服务行为里，属于非公开施为（off-record）。",
    },
    {
        "id": "c04", "scene": "stranger", "act": "投诉", "difficulty": 2,
        "context": "你在政府办事窗口排了两小时，轮到你时被告知材料不全，但网站上并没有写明这项要求。",
        "goal": "指出问题、争取当场解决，同时不激怒办事人员。",
        "focus": "对机构投诉时，把矛头指向制度而非具体的人，成功率更高",
        "expect": ["honorific", "reason", "question", "hedge"],
        "avoid": ["blunt_accusation"],
        "reference": "您好，我想确认一下——我是照着官网的清单准备的，上面没有提到这一项。是不是网站还没更新？我今天能不能先补一份声明，其他材料后续再补齐？",
        "note": "把「你们错了」重构为「信息可能没同步」，是一种去人格化（depersonalisation）策略：批评对象从眼前的人转移到系统，对方就不必为了维护自己的面子而对抗你。",
    },
    {
        "id": "c05", "scene": "boss", "act": "纠正上级", "difficulty": 3,
        "context": "你发现老板在发给全公司的邮件里把一个重要数字写错了。",
        "goal": "让他尽快改正，且不让他觉得被下属挑错。",
        "focus": "纠正权势更高者，是难度最高的面子威胁行为之一",
        "expect": ["address", "honorific", "hedge", "question", "softener"],
        "avoid": ["blunt_negation", "blunt_accusation"],
        "reference": "老板，可能是我看错了——刚才那封邮件里第三季度的数字，和我这边表格上的对不上。要不要我把表格发您核对一下？",
        "note": "「可能是我看错了」是一种自我贬抑（self-deprecation）的缓冲手段，先把犯错的可能性揽到自己身上，为对方留出体面的退路，这样对方改正时不必承认自己犯了错。",
    },
    {
        "id": "c06", "scene": "peer", "act": "接受赞美", "difficulty": 1,
        "context": "同事当着几个人的面说：「你这次的报告做得真好，比我强多了。」",
        "goal": "得体地回应，既不显得自满，也不否定对方的判断力。",
        "focus": "接受赞美的应答策略，是跨文化语用学的经典课题",
        "expect": ["thanks", "credit"],
        "avoid": ["blunt_negation"],
        "reference": "谢谢！其实是你上次提醒我加的那部分数据帮了大忙，不然我根本想不到那个角度。",
        "note": "汉语传统上偏好否定式应答（「哪里哪里」），英语则偏好接受（「Thank you」）。当代汉语的折中做法是「接受＋转移功劳」：先致谢，再把成绩归因于对方或外部条件，既不自夸也不驳斥对方。",
    },
    {
        "id": "c07", "scene": "boss", "act": "请假", "difficulty": 2,
        "context": "项目最紧张的时候，你因为家里的事必须请三天假。",
        "goal": "拿到假期，同时让老板相信项目不会因此失控。",
        "focus": "在高强加度（imposition）的请求中，主动承担成本可以降低威胁",
        "expect": ["address", "honorific", "reason", "alternative", "question"],
        "avoid": ["blunt_demand"],
        "reference": "老板，我家里有点急事，下周三到周五需要请三天假。我这边的进度我今天会整理成文档交接给小李，紧急的事我手机随时能联系上。您看这样安排可以吗？",
        "note": "请求的强加度＝对方付出的成本。主动提出交接方案和随时可联系，实际上是在替对方承担成本，把强加度降下来，请求也就更容易被接受。",
    },
    {
        "id": "c08", "scene": "teacher", "act": "拒绝邀约", "difficulty": 3,
        "context": "导师邀请你加入一个你没兴趣、也和你研究方向不符的项目。",
        "goal": "婉拒，但不损害师生关系，也不显得你挑三拣四。",
        "focus": "拒绝权势更高者的好意，需要同时处理正面面子与负面面子",
        "expect": ["thanks", "address", "honorific", "hedge", "reason", "alternative"],
        "avoid": ["blunt_negation"],
        "reference": "老师，谢谢您想到我。这个题目我很感兴趣，但我担心自己现在同时推两个方向会两头都做不深，反而辜负了这个机会。等我手上这篇投出去，如果项目还需要人，我很愿意再参与。",
        "note": "拒绝师长的好意时，先致谢确认对方的善意（保护正面面子），再把拒绝理由归于自身能力或时间限制而非对项目的评价，最后留一个未来的可能性——这三步几乎是学术语境里的固定套路。",
    },
    {
        "id": "c09", "scene": "peer", "act": "传达坏消息", "difficulty": 2,
        "context": "你负责的部分延期了，会连累同事的进度，你必须现在告诉他。",
        "goal": "如实告知，承担责任，同时让对方还能保持合作意愿。",
        "focus": "坏消息的告知顺序，直接影响听话人的情绪反应",
        "expect": ["apology", "reason", "alternative"],
        "avoid": ["blunt_excuse"],
        "reference": "有个不好的消息要先跟你说一声：我这边要晚两天。原因在我，测试环境的问题我低估了。你那部分要不要先用我现在的版本跑着？我周四之前一定给你最终版。",
        "note": "坏消息的有效结构是「预告—事实—归因—补救」。先给一句预告让对方有心理准备，明确归因于自己（而不是含糊其辞）反而更容易获得谅解，因为对方不必再花力气追问责任。",
    },
    {
        "id": "c10", "scene": "stranger", "act": "向陌生人求助", "difficulty": 1,
        "context": "你在街上手机没电了，需要向路人借电话打给家人。",
        "goal": "让一个完全陌生的人愿意帮你，且不让对方感到威胁。",
        "focus": "高社会距离下的请求，需要先降低对方的戒备",
        "expect": ["apology", "reason", "question", "hedge", "softener"],
        "avoid": ["blunt_demand"],
        "reference": "不好意思打扰一下，我手机没电了，想给家里人打个电话报平安，能不能借您的手机用一分钟？我就在您旁边打，很快。",
        "note": "对陌生人的请求要同时降低两种风险：对方的时间成本与安全顾虑。「一分钟」「就在您旁边」都是在缩小强加范围，让对方觉得答应的代价可控。",
    },
    {
        "id": "c11", "scene": "boss", "act": "争取资源", "difficulty": 3,
        "context": "你的团队人手明显不够，你要向老板申请增加一个人。",
        "goal": "让老板认同这是业务需要，而不是你在抱怨累。",
        "focus": "把个人诉求重构为组织利益，是职场请求的核心技巧",
        "expect": ["address", "honorific", "reason", "question"],
        "avoid": ["blunt_complaint"],
        "reference": "老板，有件事想跟您商量。目前这三条线同时推，我们的排期已经排到下个月底了，新需求进来只能往后压。如果能加一个人，我估算能把交付周期压缩一半左右。您看有没有可能？",
        "note": "「我很累」是说话人视角的抱怨，「交付周期会翻倍」是听话人视角的损失。同一件事换成对方关心的度量单位来陈述，请求就从索取变成了提案。",
    },
    {
        "id": "c12", "scene": "peer", "act": "指出错误", "difficulty": 2,
        "context": "同事在群里发了一份数据有误的文件，已经有人开始转发了。",
        "goal": "尽快止损，但不让他在群里难堪。",
        "focus": "公开场合的纠错，涉及旁观者在场时的面子管理",
        "expect": ["hedge", "question", "softener", "alternative"],
        "avoid": ["blunt_accusation"],
        "reference": "@某某 我这边核对的时候第二页那栏对不上，会不会是导出的时候版本拿错了？我先在群里说一声，大家等一下再用。",
        "note": "有旁观者在场时，纠错的面子威胁会被放大。把错误归因于流程环节（版本、导出）而非个人能力，并用疑问句留出对方自我更正的空间，是降低威胁的常见做法。",
    },
    {
        "id": "c13", "scene": "teacher", "act": "请求延期", "difficulty": 2,
        "context": "论文初稿写不完了，你要向导师申请延后一周提交。",
        "goal": "拿到延期，同时不让导师觉得你在拖延或态度不端正。",
        "focus": "延期请求的关键在于展示已完成的工作量",
        "expect": ["address", "honorific", "apology", "reason", "question"],
        "avoid": ["blunt_excuse"],
        "reference": "老师，不好意思，想跟您申请把初稿推迟一周。第三章的数据我重跑了一遍，结果和原来的结论有出入，我想把这部分弄扎实再交给您。前两章已经完成了，需要的话我可以先发您看。",
        "note": "延期请求最容易被解读为能力或态度问题。附上已完成的部分是一种「证据前置」策略，把请求的性质从「我没做完」转换为「我在追求质量」。",
    },
    {
        "id": "c14", "scene": "stranger", "act": "拒绝推销", "difficulty": 1,
        "context": "商场里销售人员热情地跟着你介绍产品，你完全不想买。",
        "goal": "干脆地脱身，又不失礼。",
        "focus": "低社会距离压力下的快速拒绝，简洁比委婉更有效",
        "expect": ["thanks", "softener"],
        "avoid": ["blunt_negation"],
        "reference": "谢谢，我今天就随便看看，需要的话我再找您。",
        "note": "并非所有场合都是越委婉越好。面对陌生人的商业推销，过度委婉反而会被解读为犹豫、延长互动。简短的致谢＋明确的边界，在这个语境里既得体又高效。",
    },
    {
        "id": "c15", "scene": "peer", "act": "催还欠款", "difficulty": 3,
        "context": "同事借了你两千块，说好上个月还，到现在没提。",
        "goal": "把钱要回来，同时保住这段同事关系。",
        "focus": "金钱议题在汉语语境里高度敏感，需要给对方台阶",
        "expect": ["hedge", "reason", "question", "softener"],
        "avoid": ["blunt_demand", "blunt_accusation"],
        "reference": "跟你说个事儿，有点不好意思开口——我最近手头有笔支出要用钱，上次那两千你方便的时候转我一下就行，不着急。",
        "note": "催款时给出自己的用钱理由，是把请求的动因外部化：不是「你欠我」，而是「我恰好需要」。「不着急」这类看似矛盾的补语，实际上是在给对方保留主动权，降低被逼迫感。",
    },
    {
        "id": "c16", "scene": "boss", "act": "承认失误", "difficulty": 2,
        "context": "因为你的疏忽，公司损失了一个不大但明确的订单。",
        "goal": "把责任讲清楚，同时让老板相信你还可靠。",
        "focus": "道歉的四要素：承认、归因、补救、防复发",
        "expect": ["apology", "reason", "alternative"],
        "avoid": ["blunt_excuse"],
        "reference": "老板，这次的单子丢了，责任在我，我漏看了客户改期的邮件。我已经联系对方争取下一批的机会，另外我把邮件规则重新设了一遍，同类的事不会再发生。",
        "note": "研究显示，包含「防复发措施」的道歉显著更容易被接受。只说「对不起」传达的是情绪，说明具体的改进机制才传达了可靠性——后者才是上级真正想要的信息。",
    },
    {
        "id": "c17", "scene": "teacher", "act": "表达感谢", "difficulty": 1,
        "context": "导师花了整个周末帮你改论文，改得非常细。",
        "goal": "表达真诚的感谢，不流于客套。",
        "focus": "感谢的具体化程度，直接决定它听起来是真心还是敷衍",
        "expect": ["address", "honorific", "thanks", "reason"],
        "avoid": ["generic_only"],
        "reference": "老师，非常感谢您花周末的时间帮我改稿。您在第二章标出的那几处论证跳跃，我之前完全没意识到，改完之后整条逻辑线清楚多了。",
        "note": "「谢谢老师」是套话，「您标出的第二章那几处论证跳跃」才是证据——它证明你真的读了、用了对方的付出。感谢的诚意几乎完全由细节的具体程度承载。",
    },
    {
        "id": "c18", "scene": "peer", "act": "打断发言", "difficulty": 2,
        "context": "会议时间快到了，同事还在长篇大论，你必须打断他推进议程。",
        "goal": "把会议拉回正轨，又不让他觉得被嫌弃。",
        "focus": "话轮转换（turn-taking）中的打断，需要正当性理由",
        "expect": ["apology", "reason", "alternative", "question"],
        "avoid": ["blunt_demand"],
        "reference": "不好意思打断一下——时间快到了，你这部分我觉得挺重要的，要不我们会后单独聊，先把剩下两项过完？",
        "note": "打断本身就是对话轮权利的侵犯。有效的打断需要三件事：致歉、外部化的理由（时间而非内容）、以及对被打断内容的价值确认——最后这一条最容易被忽略，却最能挽回对方的面子。",
    },
    {
        "id": "c19", "scene": "stranger", "act": "争取例外", "difficulty": 3,
        "context": "你晚了十分钟到，柜台说今天的号已经放完了，但你确实很急。",
        "goal": "争取对方通融，而不是让对方觉得你在为难他。",
        "focus": "请求破例时，承认规则的正当性比挑战规则更有效",
        "expect": ["honorific", "apology", "reason", "question", "hedge"],
        "avoid": ["blunt_demand", "blunt_accusation"],
        "reference": "我知道是我自己来晚了，规定我也理解。只是这份材料关系到我明天的签证面谈，实在没有别的办法了。请问有没有可能加个号，或者今天还有别的窗口能受理？我可以一直等到下班。",
        "note": "请求破例时，先承认规则和自身过错，能显著降低办事人员的防御姿态——因为他不必再花力气向你论证规则的合理性，可以直接进入「能不能帮你」的问题。",
    },
    {
        "id": "c20", "scene": "boss", "act": "汇报进度", "difficulty": 2,
        "context": "老板问你项目进展，实际上进度落后，但原因不在你。",
        "goal": "如实汇报落后的事实，说明原因但不显得在推卸责任。",
        "focus": "归因外部时最容易踩的坑是听起来像找借口",
        "expect": ["reason", "alternative"],
        "avoid": ["blunt_excuse", "blunt_complaint"],
        "reference": "目前落后大概一周。主要卡在对方接口一直没提供，我上周催了两次，邮件我可以转给您。这边我已经先按假数据把后续流程搭完了，接口一到就能接上。",
        "note": "外部归因要成立，必须附上两样东西：证据（我催了两次、邮件可转）和主动性（我已经先做了什么）。缺了这两样，任何外部理由听起来都像借口——这是汇报中最常见的失分点。",
    },
]

# 按 id 建索引，方便按编号取题
BY_ID = {c["id"]: c for c in CHALLENGES}


def public_view(ch: dict) -> dict:
    """
    整理一份"可以发给前端"的题目。

    注意：故意不包含 reference（参考答案）和 note（讲解）——
    那两个字段要等用户提交答案之后才返回，否则就直接被剧透了。
    expect / avoid 是评分内部用的，也不发给前端。
    """
    return {
        "id": ch["id"],
        "scene": ch["scene"],
        "act": ch["act"],
        "difficulty": ch["difficulty"],
        "context": ch["context"],
        "goal": ch["goal"],
    }


# 计算轮次的起点日期。改这个日期会让每日题的排列整体平移，一般不用动。
EPOCH = date(2026, 1, 1)


def _cycle_order(cycle: int, n: int) -> list:
    """
    为第 cycle 轮生成一个固定的出题顺序（0 到 n-1 的一个排列）。

    做法是给每个下标算一个由轮号决定的哈希，再按哈希排序——
    等价于一次"确定性洗牌"：同一轮永远得到同一个顺序，
    不同轮的顺序互不相同。不依赖随机数种子的实现细节，
    换 Python 版本、换服务器都不会变。
    """
    return sorted(range(n),
                  key=lambda i: hashlib.sha256(f"paopao-{cycle}-{i}".encode()).hexdigest())


# 接缝保护的宽度：本轮开头 GAP 题，不允许和上一轮结尾 GAP 题重合
GAP = 3


def _order_for(cycle: int, n: int) -> list:
    """
    生成第 cycle 轮的出题顺序，并处理"接缝撞题"。

    【为什么要处理接缝】
    每一轮内部不会重样，但上一轮的最后一题和下一轮的第一题
    完全可能是同一道——用户会连着两天看到同一题。
    这里把本轮开头 GAP 个位置上与上一轮结尾 GAP 题重合的项，
    确定性地换到中间去，从而把最小重复间隔拉开。
    """
    order = _cycle_order(cycle, n)
    if n <= GAP * 2:
        return order

    prev_tail = set(_cycle_order(cycle - 1, n)[-GAP:])
    for i in range(GAP):
        if order[i] in prev_tail:
            # 从中段找一个不在上一轮结尾里的题换过来
            for j in range(GAP, n - GAP):
                if order[j] not in prev_tail:
                    order[i], order[j] = order[j], order[i]
                    break
    return order


def daily_challenge(day: str = None) -> dict:
    """
    取"今天的挑战"。

    【为什么不直接用日期哈希取余？】
    那样会撞题——20 道题、每天独立取余，两三天内就可能重复出同一题
    （生日悖论）。这里改成"20 天一轮"：每一轮把全部题目洗一次牌，
    轮内每天取一个，因此一轮之内绝不重样，20 天后才开始下一轮。

    整个计算是确定性的：不需要数据库记录出过哪题，
    服务器重启、多实例并行，结果都一致。

    参数:
        day: 'YYYY-MM-DD'，不传就用服务器当天日期
    """
    n = len(CHALLENGES)
    try:
        d = date.fromisoformat(day) if day else date.today()
    except (TypeError, ValueError):
        d = date.today()

    offset = (d - EPOCH).days
    cycle, pos = divmod(offset, n)   # Python 的整除对负数也取下界，pos 恒在 0..n-1
    return CHALLENGES[_order_for(cycle, n)[pos]]


def random_challenge(exclude_id: str = None) -> dict:
    """
    随机抽一题，用于"自由练习"。

    参数:
        exclude_id: 要避开的题号（一般是刚做完的那题，避免连着出同一题）
    """
    import random
    pool = [c for c in CHALLENGES if c["id"] != exclude_id] or CHALLENGES
    return random.choice(pool)


def get(challenge_id: str):
    """按题号取完整题目（含答案与讲解），供评分使用。"""
    return BY_ID.get(challenge_id)
