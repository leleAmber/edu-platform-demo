"""模拟 AI 核心：作业批改、掌握度评分、学习计划、错题归因、试卷评分。

全部为本地规则 + 随机模拟，不调用任何外部大模型 API：
- 批改基于正则规则库，同一份作业任何时候批改结果一致；
- 掌握度 / 能力维度以学习记录为基准做偏移，保证同一会话内稳定可复现。
"""

from __future__ import annotations

import random
import re

from core import auth, database

# --------------------------------------------------------------------------- #
# 单元内容（人教版必修一 4 个单元，课文为贴合单元主题的改编选段）
# --------------------------------------------------------------------------- #
UNITS: tuple[str, ...] = (
    "Unit1 Teenage Life",
    "Unit2 Travelling Around",
    "Unit3 Sports and Fitness",
    "Unit4 Natural Disasters",
)

DIMENSION_LABELS = {
    "vocab": "词汇能力",
    "grammar": "句法语法",
    "discourse": "语篇理解",
    "writing": "写作输出",
}

CONTENT: dict[str, dict] = {
    "Unit1 Teenage Life": {
        "theme": "校园生活 · 社团与时间管理",
        "passages": [
            {
                "heading": "Paragraph 1",
                "text": (
                    "Senior high school is a new start, and it comes with a mix of excitement and "
                    "worry. In the first week, I had to choose between several school clubs, from the "
                    "debate club to the ballet club. My adviser helped me sign up for two of them, and "
                    "she told me that a teenager's life is not only about study."
                ),
            },
            {
                "heading": "Paragraph 2",
                "text": (
                    "What I enjoy most is the after-class reading session. We sit in a circle and share "
                    "what we have read, which helps me understand the text from different angles. Of "
                    "course, I still feel stressed before an exam, but I am learning to manage my time "
                    "and to ask for help when I need it."
                ),
            },
        ],
        "long_sentences": [
            {
                "sentence": (
                    "We sit in a circle and share what we have read, which helps me understand the "
                    "text from different angles."
                ),
                "skeleton": "We sit ... and share ...",
                "modifiers": "what we have read 作 share 的宾语从句；which 引导非限制性定语从句，指代前面整个主句",
                "translation": "我们围坐成一圈，分享各自读过的内容，这帮助我从不同角度理解文章。",
            },
            {
                "sentence": (
                    "My adviser helped me sign up for two of them, and she told me that a teenager's "
                    "life is not only about study."
                ),
                "skeleton": "My adviser helped me ... and she told me ...",
                "modifiers": "sign up for two of them 作宾语补足语（help sb do sth）；that 引导宾语从句",
                "translation": "我的指导老师帮我报名了其中两个社团，她还告诉我，青少年的生活不只有学习。",
            },
        ],
        "words": [
            {"word": "senior", "pos": "adj.", "explain": "高级的；年长的（senior high school 高中）",
             "sentence": "He is a senior student in our school."},
            {"word": "adviser", "pos": "n.", "explain": "顾问；指导老师（=advisor）",
             "sentence": "My adviser helped me choose the right courses."},
            {"word": "club", "pos": "n.", "explain": "俱乐部；社团",
             "sentence": "I joined the debate club last week."},
            {"word": "sign up", "pos": "phr.", "explain": "报名参加（常与 for 连用）",
             "sentence": "She signed up for the ballet club."},
            {"word": "stressed", "pos": "adj.", "explain": "焦虑不安的；压力大的",
             "sentence": "I feel stressed before an important exam."},
            {"word": "teenager", "pos": "n.", "explain": "青少年（13~19 岁）",
             "sentence": "A teenager's life is full of changes."},
        ],
        "preview_quiz": [
            {"question": "My adviser helped me ______ for the debate club.",
             "options": ["sign up", "signing up", "to signing up", "signed up"],
             "answer": "sign up", "explain": "help sb do sth，宾补用动词原形。"},
            {"question": "______ he is only sixteen, he manages his time better than many adults.",
             "options": ["Although", "But", "Because", "So"],
             "answer": "Although", "explain": "让步状语从句用 although 引导，且不与 but 连用。"},
            {"question": "Which sentence is correct?",
             "options": ["He very likes music.", "He likes music very much.",
                         "He likes very music.", "He is like music."],
             "answer": "He likes music very much.",
             "explain": "very 不能直接修饰动词，程度用 very much 放在动词后。"},
            {"question": "I feel ______ before an exam, so I often take a deep breath.",
             "options": ["stressed", "stress", "stressing", "to stress"],
             "answer": "stressed", "explain": "feel 后接形容词作表语，stressed 表示「感到有压力的」。"},
            {"question": "The club ______ I joined last week meets every Friday.",
             "options": ["who", "what", "which", "whose"],
             "answer": "which", "explain": "先行词 club 指物，定语从句用 which / that。"},
        ],
        "review_quiz": [
            {"question": "It is the first time that I ______ a speech in public.",
             "options": ["give", "gave", "have given", "will give"],
             "answer": "have given", "explain": "It is the first time that 后接现在完成时。"},
            {"question": "The teacher advised me ______ more attention to my handwriting.",
             "options": ["pay", "to pay", "paying", "paid"],
             "answer": "to pay", "explain": "advise sb to do sth。"},
            {"question": "— How do you ______ your time between study and clubs? — By making a plan.",
             "options": ["manage", "take", "spend", "cost"],
             "answer": "manage", "explain": "manage time 意为「安排、管理时间」。"},
            {"question": "Teenagers ______ to be independent, but they still need guidance.",
             "options": ["are wanted", "want", "wanted", "wanting"],
             "answer": "want", "explain": "主语 teenagers 是复数，谓语用 want，且为主动语态。"},
            {"question": "______ makes me feel stressed is the coming exam.",
             "options": ["That", "What", "Which", "It"],
             "answer": "What", "explain": "主语从句缺少主语，用 what 引导。"},
        ],
        "knowledge": {
            "vocab": {"summary": "校园生活高频词与社团相关短语", "mastery": 82,
                      "points": ["senior / junior 的区分", "sign up for 的用法", "stressed 与 stressful 的区别"]},
            "grammar": {"summary": "定语从句与非限制性定语从句", "mastery": 74,
                        "points": ["which 指代整个主句", "help sb do sth", "It is the first time that + 现在完成时"]},
            "discourse": {"summary": "记叙文的时间线与情感线索", "mastery": 86,
                          "points": ["按时间顺序梳理事件", "抓取段落主题句", "体会作者的情感变化"]},
        },
        "vocab_stats": {"mastered": 42, "to_review": 15},
    },
    "Unit2 Travelling Around": {
        "theme": "旅行 · 行程规划与文化遗产",
        "passages": [
            {
                "heading": "Paragraph 1",
                "text": (
                    "Last summer my family travelled to Xi'an, an ancient city that was once the capital "
                    "of thirteen dynasties. Before we left, my father made a detailed itinerary and "
                    "booked the tickets online, so we did not waste a single morning."
                ),
            },
            {
                "heading": "Paragraph 2",
                "text": (
                    "The most breathtaking moment came when we stood in front of the Terracotta Army. Our "
                    "guide explained that every figure has a different face, and that the workers who "
                    "made them left their names on the weapons. Travelling, I realized, is not just about "
                    "taking photos; it is about understanding how other people live."
                ),
            },
        ],
        "long_sentences": [
            {
                "sentence": "The most breathtaking moment came when we stood in front of the Terracotta Army.",
                "skeleton": "The most breathtaking moment came ...",
                "modifiers": "when 引导时间状语从句，说明「最震撼的时刻」出现的时机",
                "translation": "最令人震撼的时刻，出现在我们站在兵马俑前的那一刻。",
            },
            {
                "sentence": ("Our guide explained that every figure has a different face, and that the workers "
                             "who made them left their names on the weapons."),
                "skeleton": "Our guide explained that ... and that ...",
                "modifiers": "两个 that 引导并列宾语从句；who made them 是修饰 workers 的定语从句",
                "translation": "导游解释说，每一个陶俑的面孔都不相同，而且制作它们的工匠把名字留在了兵器上。",
            },
        ],
        "words": [
            {"word": "destination", "pos": "n.", "explain": "目的地；终点",
             "sentence": "Xi'an was our final destination."},
            {"word": "ancient", "pos": "adj.", "explain": "古代的；古老的",
             "sentence": "This is an ancient city with a long history."},
            {"word": "itinerary", "pos": "n.", "explain": "行程单；旅行日程",
             "sentence": "My father made a detailed itinerary."},
            {"word": "souvenir", "pos": "n.", "explain": "纪念品",
             "sentence": "I bought a small souvenir for my friend."},
            {"word": "breathtaking", "pos": "adj.", "explain": "令人惊叹的；壮观的",
             "sentence": "The view from the top was breathtaking."},
            {"word": "architecture", "pos": "n.", "explain": "建筑；建筑风格",
             "sentence": "The old town is famous for its traditional architecture."},
        ],
        "preview_quiz": [
            {"question": "My father made a detailed ______ before the trip.",
             "options": ["souvenir", "itinerary", "architecture", "destination"],
             "answer": "itinerary", "explain": "itinerary 表示「行程单」，与 make a plan 搭配。"},
            {"question": "Xi'an is an ancient city ______ was once the capital of China.",
             "options": ["who", "where", "which", "when"],
             "answer": "which", "explain": "从句缺主语，先行词 city 指物，用 which。"},
            {"question": "The view from the top of the mountain was ______.",
             "options": ["breathtaking", "breath", "breathe", "breathlessly"],
             "answer": "breathtaking", "explain": "be 动词后接形容词作表语。"},
            {"question": "You need to apply ______ a visa before you travel abroad.",
             "options": ["to", "for", "with", "at"],
             "answer": "for", "explain": "apply for 意为「申请」。"},
            {"question": "The guide explained ______ every figure has a different face.",
             "options": ["that", "what", "which", "whether"],
             "answer": "that", "explain": "explain 后接 that 引导的宾语从句。"},
        ],
        "review_quiz": [
            {"question": "By the time we got to the station, the train ______.",
             "options": ["leaves", "left", "had left", "has left"],
             "answer": "had left", "explain": "「过去的过去」用过去完成时。"},
            {"question": "This is the museum ______ we visited last week.",
             "options": ["where", "which", "what", "who"],
             "answer": "which", "explain": "visited 后缺宾语，用关系代词 which（作宾语）。"},
            {"question": "Travelling helps us understand ______ other people live.",
             "options": ["how", "that", "which", "what"],
             "answer": "how", "explain": "how 引导宾语从句，表示方式「如何生活」。"},
            {"question": "My father suggested ______ the tickets online.",
             "options": ["to book", "booking", "book", "booked"],
             "answer": "booking", "explain": "suggest doing sth，后接动名词。"},
            {"question": "It was the first time that we ______ the Terracotta Army.",
             "options": ["see", "saw", "had seen", "have seen"],
             "answer": "had seen", "explain": "It was the first time that 后接过去完成时。"},
        ],
        "knowledge": {
            "vocab": {"summary": "旅行主题名词与动词短语", "mastery": 79,
                      "points": ["destination / itinerary 的搭配", "apply for 与 apply to", "形容词后缀 -ing / -ed"]},
            "grammar": {"summary": "定语从句与过去完成时", "mastery": 71,
                        "points": ["which 作宾语", "By the time 引导的时间状语从句", "It was the first time that"]},
            "discourse": {"summary": "游记类文本的时空线索", "mastery": 84,
                          "points": ["按行程顺序梳理信息", "区分事实与感受", "把握文章中心句"]},
        },
        "vocab_stats": {"mastered": 38, "to_review": 19},
    },
    "Unit3 Sports and Fitness": {
        "theme": "运动与健康 · 坚持与团队精神",
        "passages": [
            {
                "heading": "Paragraph 1",
                "text": (
                    "Not everyone can become a champion, but everyone can become fitter than yesterday. Our "
                    "PE teacher often says that exercise is not a punishment but a habit, and he asks us to "
                    "work out at least three times a week."
                ),
            },
            {
                "heading": "Paragraph 2",
                "text": (
                    "Last month I joined the school running team. The training was harder than I had "
                    "expected: my legs hurt, and I once had a small injury. However, my teammates never let "
                    "me give up. When I finally finished the 3,000-metre race, I understood that the honour "
                    "belongs not only to the winner but to everyone who refuses to stop."
                ),
            },
        ],
        "long_sentences": [
            {
                "sentence": ("Our PE teacher often says that exercise is not a punishment but a habit, and he "
                             "asks us to work out at least three times a week."),
                "skeleton": "Our PE teacher says that ... and he asks us to ...",
                "modifiers": "not ... but ... 并列结构作表语；ask sb to do sth 不定式作宾补",
                "translation": "我们的体育老师常说，锻炼不是惩罚而是习惯，他要求我们每周至少锻炼三次。",
            },
            {
                "sentence": ("When I finally finished the 3,000-metre race, I understood that the honour belongs "
                             "not only to the winner but to everyone who refuses to stop."),
                "skeleton": "I understood that the honour belongs to ...",
                "modifiers": "When 引导时间状语从句；not only ... but ... 并列；who refuses to stop 修饰 everyone",
                "translation": "当我终于跑完三千米时，我明白了荣誉不只属于获胜者，也属于每一个拒绝停下的人。",
            },
        ],
        "words": [
            {"word": "athlete", "pos": "n.", "explain": "运动员",
             "sentence": "She is one of the best athletes in our school."},
            {"word": "champion", "pos": "n.", "explain": "冠军；优胜者",
             "sentence": "He became the national champion last year."},
            {"word": "work out", "pos": "phr.", "explain": "锻炼；健身",
             "sentence": "I work out for an hour every morning."},
            {"word": "injury", "pos": "n.", "explain": "伤害；受伤",
             "sentence": "He missed the match because of an injury."},
            {"word": "determination", "pos": "n.", "explain": "决心；坚毅",
             "sentence": "Her determination moved everyone."},
            {"word": "honour", "pos": "n.", "explain": "荣誉；光荣（英式拼写）",
             "sentence": "The honour belongs to the whole team."},
        ],
        "preview_quiz": [
            {"question": "He works ______ every morning to keep fit.",
             "options": ["out", "on", "up", "off"],
             "answer": "out", "explain": "work out 表示「锻炼」。"},
            {"question": "She is one of the best ______ in our school team.",
             "options": ["athlete", "athletes", "athlete's", "athletics"],
             "answer": "athletes", "explain": "one of the + 最高级 + 复数名词。"},
            {"question": "______ hard he tried, he never gave up.",
             "options": ["However", "Whatever", "Whenever", "Wherever"],
             "answer": "However", "explain": "However + 形容词/副词 引导让步状语从句。"},
            {"question": "The ______ he showed in the race moved everyone.",
             "options": ["determine", "determination", "determined", "determinately"],
             "answer": "determination", "explain": "the 后需要名词，determination 为名词形式。"},
            {"question": "Our teacher asks us ______ at least three times a week.",
             "options": ["work out", "to work out", "working out", "worked out"],
             "answer": "to work out", "explain": "ask sb to do sth。"},
        ],
        "review_quiz": [
            {"question": "Not only he but also his teammates ______ excited about the win.",
             "options": ["is", "are", "was", "be"],
             "answer": "are", "explain": "not only ... but also ... 连接主语时遵循就近原则。"},
            {"question": "He ______ his leg while he was playing basketball.",
             "options": ["injures", "injured", "was injured", "has injured"],
             "answer": "injured", "explain": "while 从句用过去进行时，主句用一般过去时；主语 he 主动受伤。"},
            {"question": "It is important ______ a habit of exercising.",
             "options": ["form", "to form", "forming", "formed"],
             "answer": "to form", "explain": "It is + adj. + to do sth 句型。"},
            {"question": "The more you practise, ______ you will become.",
             "options": ["the fit", "the fitter", "fitter", "the fittest"],
             "answer": "the fitter", "explain": "the more ... the more ... 比较级结构。"},
            {"question": "I would rather ______ than give up.",
             "options": ["to try", "trying", "try", "tried"],
             "answer": "try", "explain": "would rather do sth than do sth。"},
        ],
        "knowledge": {
            "vocab": {"summary": "运动健身词汇与名词后缀 -tion", "mastery": 81,
                      "points": ["work out / warm up 等短语", "injury 与 injure 的词性转换", "honour 的英式拼写"]},
            "grammar": {"summary": "主谓一致与比较级结构", "mastery": 68,
                        "points": ["not only ... but also 就近原则", "the more ... the more ...", "It is + adj. + to do"]},
            "discourse": {"summary": "记叙+议论的混合文体", "mastery": 80,
                          "points": ["叙事后的观点句", "转折词 however 的作用", "首尾呼应的写法"]},
        },
        "vocab_stats": {"mastered": 45, "to_review": 12},
    },
    "Unit4 Natural Disasters": {
        "theme": "自然灾害 · 救援与重建",
        "passages": [
            {
                "heading": "Paragraph 1",
                "text": (
                    "At 3:42 in the morning, the city was shaken by a terrible earthquake. In less than a "
                    "minute, thousands of buildings collapsed and the whole city lay in ruins. People ran out "
                    "of their homes in panic, not knowing what had happened."
                ),
            },
            {
                "heading": "Paragraph 2",
                "text": (
                    "But what I remember most is not the destruction; it is the rescue teams who arrived "
                    "before dawn. They dug through the rubble with their bare hands, set up shelters for the "
                    "survivors, and never stopped searching. A disaster can destroy a city, but it cannot "
                    "destroy the courage of ordinary people."
                ),
            },
        ],
        "long_sentences": [
            {
                "sentence": "People ran out of their homes in panic, not knowing what had happened.",
                "skeleton": "People ran out of their homes ...",
                "modifiers": "in panic 介词短语作状语；not knowing ... 现在分词短语作伴随状语，内含宾语从句",
                "translation": "人们惊慌失措地跑出家门，不知道发生了什么。",
            },
            {
                "sentence": ("But what I remember most is not the destruction; it is the rescue teams who arrived "
                             "before dawn."),
                "skeleton": "what I remember most is not the destruction; it is the rescue teams ...",
                "modifiers": "what 引导主语从句；who arrived before dawn 是修饰 rescue teams 的定语从句",
                "translation": "但我记得最深的并不是那场破坏，而是天亮前赶到的救援队。",
            },
        ],
        "words": [
            {"word": "disaster", "pos": "n.", "explain": "灾难；灾害",
             "sentence": "The flood was the worst disaster in years."},
            {"word": "destroy", "pos": "v.", "explain": "摧毁；毁坏",
             "sentence": "The earthquake destroyed thousands of homes."},
            {"word": "rescue", "pos": "v. & n.", "explain": "营救；救援",
             "sentence": "The rescue team arrived before dawn."},
            {"word": "survivor", "pos": "n.", "explain": "幸存者",
             "sentence": "The survivors were sent to a safe place."},
            {"word": "shelter", "pos": "n.", "explain": "避难所；庇护处",
             "sentence": "They set up shelters for the villagers."},
            {"word": "in ruins", "pos": "phr.", "explain": "成为废墟；严重受损",
             "sentence": "The whole city lay in ruins after the quake."},
        ],
        "preview_quiz": [
            {"question": "Thousands of buildings ______ in the earthquake last year.",
             "options": ["destroyed", "were destroyed", "destroy", "have destroyed"],
             "answer": "were destroyed", "explain": "建筑物是动作承受者，用一般过去时的被动语态。"},
            {"question": "The rescue team arrived ______ dawn.",
             "options": ["before", "ago", "since", "for"],
             "answer": "before", "explain": "before dawn 表示「天亮前」；ago 用于时间段之后。"},
            {"question": "______ we saw was a city in ruins.",
             "options": ["That", "What", "Which", "It"],
             "answer": "What", "explain": "主语从句中缺少宾语，用 what 引导。"},
            {"question": "The villagers took ______ in a school after the flood.",
             "options": ["shelter", "shelters", "sheltering", "sheltered"],
             "answer": "shelter", "explain": "take shelter 是固定搭配，shelter 在此不可数。"},
            {"question": "She is one of the ______ of the earthquake.",
             "options": ["survivor", "survivors", "surviving", "survived"],
             "answer": "survivors", "explain": "one of the + 复数名词。"},
        ],
        "review_quiz": [
            {"question": "By the time the rescue team arrived, the building ______.",
             "options": ["collapsed", "had collapsed", "has collapsed", "collapses"],
             "answer": "had collapsed", "explain": "By the time + 过去时，主句用过去完成时。"},
            {"question": "The man ______ leg was hurt in the disaster was sent to hospital.",
             "options": ["who", "which", "whose", "that"],
             "answer": "whose", "explain": "从句中 leg 与 man 是所属关系，用 whose。"},
            {"question": "People were running out of the building ______.",
             "options": ["in panic", "in a panic", "panicked", "panic"],
             "answer": "in panic", "explain": "in panic 为固定短语，意为「惊慌地」。"},
            {"question": "It was the soldiers ______ saved the villagers.",
             "options": ["who", "which", "what", "whose"],
             "answer": "who", "explain": "强调句 It was ... that/who ...，强调人可用 who。"},
            {"question": "______ the earthquake destroyed the city, the people never lost hope.",
             "options": ["Although", "Because", "But", "However"],
             "answer": "Although", "explain": "让步状语从句用 Although，且不与 but 连用。"},
        ],
        "knowledge": {
            "vocab": {"summary": "灾害与救援主题词汇", "mastery": 76,
                      "points": ["destroy / damage / ruin 的区别", "take shelter 固定搭配", "survivor 的构词法"]},
            "grammar": {"summary": "被动语态与定语从句", "mastery": 70,
                        "points": ["一般过去时的被动语态", "whose 引导定语从句", "It was ... that 强调句"]},
            "discourse": {"summary": "灾难报道的新闻语篇特征", "mastery": 83,
                          "points": ["新闻导语的时间地点要素", "客观描述与情感表达的区分", "转折后的主旨句"]},
        },
        "vocab_stats": {"mastered": 40, "to_review": 17},
    },
}

DEFAULT_UNIT = UNITS[0]


# --------------------------------------------------------------------------- #
# 单元内容读取
# --------------------------------------------------------------------------- #
def get_unit_content(unit: str) -> dict:
    """获取指定单元的内容，单元不存在时回退到第一个单元。"""
    return CONTENT.get(unit) or CONTENT[DEFAULT_UNIT]


def grade_quiz(unit: str, quiz_type: str, answers: dict) -> dict:
    """批改预习 / 复习练习。answers 形如 {"0": "选项文本", ...}。"""
    content = get_unit_content(unit)
    questions = content.get(f"{quiz_type}_quiz", [])
    details = []
    correct_count = 0

    for index, question in enumerate(questions):
        chosen = answers.get(str(index)) or answers.get(index) or ""
        is_right = chosen == question["answer"]
        correct_count += int(is_right)
        details.append(
            {
                "index": index + 1,
                "question": question["question"],
                "your_answer": chosen or "未作答",
                "answer": question["answer"],
                "explain": question["explain"],
                "is_right": is_right,
            }
        )

    total = len(questions) or 1
    return {
        "correct_count": correct_count,
        "total": total,
        "score": round(correct_count / total * 100),
        "details": details,
    }


# --------------------------------------------------------------------------- #
# 作业批改（本地规则引擎）
# --------------------------------------------------------------------------- #
_THIRD_PERSON = {
    "go": "goes", "do": "does", "have": "has", "watch": "watches", "study": "studies",
    "play": "plays", "like": "likes", "want": "wants", "need": "needs", "think": "thinks",
    "say": "says", "live": "lives", "come": "comes", "make": "makes",
}
_UNCOUNTABLE = {
    "informations": "information", "advices": "advice", "knowledges": "knowledge",
    "homeworks": "homework", "equipments": "equipment", "furnitures": "furniture",
}


def _third_person_replace(match: re.Match) -> str:
    subject, verb = match.group(1), match.group(2).lower()
    return f"{subject} {_THIRD_PERSON.get(verb, verb + 's')}"


def _uncountable_replace(match: re.Match) -> str:
    return _UNCOUNTABLE.get(match.group(0).lower(), match.group(0))


_CORRECTION_RULES: tuple[dict, ...] = (
    {
        "type": "大小写错误",
        "pattern": re.compile(r"(?<![A-Za-z])i(?![A-Za-z'])"),
        "replace": "I",
        "explain": "第一人称代词 I 在任何位置都必须大写。",
    },
    {
        "type": "冠词误用",
        "pattern": re.compile(r"\ba\s+(?=[aeiouAEIOU])"),
        "replace": "an ",
        "explain": "以元音音素开头的单词前用 an，不用 a。",
    },
    {
        "type": "主谓一致",
        "pattern": re.compile(
            r"\b(he|she|it|He|She|It)\s+(go|do|have|watch|study|play|like|want|need|think|say|live|come|make)\b"
        ),
        "replace": _third_person_replace,
        "explain": "一般现在时中，第三人称单数主语后的谓语动词要用第三人称单数形式。",
    },
    {
        "type": "不可数名词",
        "pattern": re.compile(r"\b(informations|advices|knowledges|homeworks|equipments|furnitures)\b", re.I),
        "replace": _uncountable_replace,
        "explain": "information / advice / knowledge 等是不可数名词，没有复数形式。",
    },
    {
        "type": "比较级重复",
        "pattern": re.compile(r"\bmore\s+(better|worse|bigger|easier|happier|faster)\b", re.I),
        "replace": lambda m: m.group(1),
        "explain": "better / worse 本身已是比较级，前面不能再加 more。",
    },
    {
        "type": "连词重复",
        "pattern": re.compile(r"\bAlthough\s+(.+?),\s*but\s+", re.I),
        "replace": lambda m: f"Although {m.group(1)}, ",
        "explain": "although 与 but 不能同时出现，保留其中一个即可。",
    },
    {
        "type": "连词重复",
        "pattern": re.compile(r"\bbecause\s+(.+?),\s*so\s+", re.I),
        "replace": lambda m: f"because {m.group(1)}, ",
        "explain": "because 与 so 不能连用，二者留其一。",
    },
    {
        "type": "程度副词误用",
        "pattern": re.compile(r"\bvery\s+(like|love|enjoy|hate)\b", re.I),
        "replace": lambda m: f"really {m.group(1).lower()}",
        "explain": "very 不能直接修饰动词，应改用 really，或把 very much 放在动词之后。",
    },
    {
        "type": "动词搭配",
        "pattern": re.compile(r"\bdiscuss\s+about\b", re.I),
        "replace": "discuss",
        "explain": "discuss 是及物动词，后面直接接宾语，不加 about。",
    },
    {
        "type": "there be 句型",
        "pattern": re.compile(r"\bthere\s+have\b", re.I),
        "replace": "there are",
        "explain": "表示「有」要用 there be 句型，不能用 there have。",
    },
    {
        "type": "非谓语错误",
        "pattern": re.compile(r"\bmake\s+(me|us|him|her|them)\s+to\s+", re.I),
        "replace": lambda m: f"make {m.group(1)} ",
        "explain": "make sb do sth 中，动词不定式不带 to。",
    },
    {
        "type": "语义重复",
        "pattern": re.compile(r"\bIn my opinion\s*,\s*I think\b", re.I),
        "replace": "In my opinion,",
        "explain": "In my opinion 与 I think 语义重复，保留一个即可。",
    },
    {
        "type": "拼写错误",
        "pattern": re.compile(r"\bcan not\b", re.I),
        "replace": "cannot",
        "explain": "cannot 通常连写成一个词。",
    },
    {
        "type": "主系表结构",
        "pattern": re.compile(r"\b(am|is|are)\s+agree\b", re.I),
        "replace": "agree",
        "explain": "agree 是实义动词，前面不加 be 动词。",
    },
    {
        "type": "时态错误",
        "pattern": re.compile(r"\byesterday\s+I\s+(go|come|see|eat|take)\b", re.I),
        "replace": lambda m: f"yesterday I {_past_tense(m.group(1).lower())}",
        "explain": "yesterday 是过去时间标志，谓语要用一般过去时。",
    },
)


def _past_tense(verb: str) -> str:
    irregular = {"go": "went", "come": "came", "see": "saw", "eat": "ate", "take": "took"}
    if verb in irregular:
        return irregular[verb]
    if verb.endswith("e"):
        return f"{verb}d"
    return f"{verb}ed"


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", (text or "").strip())
    return [part.strip() for part in parts if part.strip()]


def _correct_sentence(sentence: str) -> tuple[str, list[dict]]:
    """对单个句子依次套用规则，返回（修改后的句子, 命中的问题列表）。"""
    issues: list[dict] = []
    corrected = sentence

    for rule in _CORRECTION_RULES:
        new_text, count = rule["pattern"].subn(rule["replace"], corrected)
        if count:
            issues.append(
                {
                    "error_type": rule["type"],
                    "explain": rule["explain"],
                    "before": corrected,
                    "after": new_text,
                }
            )
            corrected = new_text

    if not corrected.endswith((".", "!", "?")):
        issues.append(
            {
                "error_type": "标点缺失",
                "explain": "英语句子末尾需要加上句号、问号或感叹号。",
                "before": corrected,
                "after": f"{corrected}.",
            }
        )
        corrected = f"{corrected}."

    return corrected, issues


def _comment_for(score: int) -> str:
    if score >= 90:
        return "整体表达流畅，语法准确，保持这个状态，可以多尝试高级句型。"
    if score >= 75:
        return "句子结构基本正确，个别细节还需要打磨，建议重点复习主谓一致与标点。"
    if score >= 60:
        return "能看出表达意图，但基础错误偏多，建议先从句型和时态入手逐句修改。"
    return "语法问题比较集中，建议先背诵单元核心句型，再仿写 5 个句子。"


def homework_correct(text: str, include_details: bool | None = None) -> dict:
    """模拟 AI 批改英语作业。

    include_details 为 None 时按当前登录用户的会员状态自动决定：
    免费用户只返回 total_score / right_count / wrong_count，VIP 才返回逐句解析。
    """
    if include_details is None:
        from core import vip  # 局部导入，避免与 vip 模块互相引用

        include_details = vip.is_vip(auth.get_current_user())

    sentences = _split_sentences(text)
    if not sentences:
        return {"total_score": 0, "right_count": 0, "wrong_count": 0, "details": [], "comment": "请先粘贴需要批改的英语作业。"}

    details = []
    error_counter: dict[str, int] = {}
    for index, sentence in enumerate(sentences, 1):
        corrected, issues = _correct_sentence(sentence)
        if not issues:
            continue
        error_types = []
        for issue in issues:
            error_types.append(issue["error_type"])
            error_counter[issue["error_type"]] = error_counter.get(issue["error_type"], 0) + 1
        details.append(
            {
                "index": index,
                "original": sentence,
                "error_type": "、".join(dict.fromkeys(error_types)),
                "corrected": corrected,
                "explain": " ".join(issue["explain"] for issue in issues),
            }
        )

    wrong_count = len(details)
    right_count = len(sentences) - wrong_count
    total_score = max(40, 100 - 8 * wrong_count)

    result = {
        "total_score": total_score,
        "right_count": right_count,
        "wrong_count": wrong_count,
    }
    if not include_details:
        return result

    result.update(
        {
            "sentence_count": len(sentences),
            "word_count": len(re.findall(r"[A-Za-z']+", text)),
            "details": details,
            "error_types": error_counter,
            "comment": _comment_for(total_score),
        }
    )
    return result


# --------------------------------------------------------------------------- #
# 作业批改（多题型 + 大模型/本地规则双引擎）
# --------------------------------------------------------------------------- #
def classify_homework(text: str) -> str:
    """判断作业类型：choice（选择题）/ blank（填空题）/ reading（阅读理解）/ writing（作文）。

    阅读理解 = 有成段文章 + 后面有题目（题号/选项），按「题目之前的英文词数」判断。
    """
    lines = [line.strip() for line in re.split(r"\n+", (text or "")) if line.strip()]
    option_lines = [line for line in lines if re.match(r"^[A-Da-d][.、:：)）]\s*\S", line)]

    # 找到第一个题目行（题号或选项），它前面若有成段英文，则视为阅读理解的文章
    first_question_idx = next(
        (
            i
            for i, line in enumerate(lines)
            if re.match(r"^\d{1,2}[.、:：)）]", line)
            or re.match(r"^[A-Da-d][.、:：)）]", line)
        ),
        None,
    )
    if first_question_idx is not None and first_question_idx > 0:
        passage_words = sum(
            len(re.findall(r"[A-Za-z']+", line)) for line in lines[:first_question_idx]
        )
        if passage_words >= 30:
            return "reading"

    if len(option_lines) >= 3:
        return "choice"
    if re.search(r"_{2,}|（\s*）|\(\s*\)|【\s*】|\[\s*\]", text or ""):
        return "blank"
    return "writing"


def _local_writing_result(text: str) -> dict:
    """作文走本地规则引擎，转换为统一结构。"""
    local = homework_correct(text, include_details=True)
    details = [
        {
            "index": item["index"],
            "question": item["original"],
            "your_answer": "",
            "correct_answer": item["corrected"],
            "is_right": False,
            "error_type": item["error_type"],
            "explain": item["explain"],
        }
        for item in local.get("details", [])
    ]
    return {
        "mode": "local",
        "total_score": local["total_score"],
        "right_count": local["right_count"],
        "wrong_count": local["wrong_count"],
        "question_count": local.get("sentence_count", local["right_count"] + local["wrong_count"]),
        "comment": local.get("comment", ""),
        "details": details,
        "error_types": local.get("error_types", {}),
        "source": "本地规则引擎",
        "note": "本地规则引擎逐句批改（覆盖常见语法/标点规则）。配置大模型后可获得更精准的批改。",
    }


def _objective_local_fallback(text: str, qtype: str) -> dict:
    """选择/填空题在未配置大模型时的兜底：只列出题目，无法自动判对错。"""
    lines = [line.strip() for line in re.split(r"\n+", (text or "")) if line.strip()]
    qtype_label = {"choice": "选择题", "blank": "填空题", "reading": "阅读理解"}.get(qtype, "客观题")
    details = [
        {
            "index": i,
            "question": line,
            "your_answer": "",
            "correct_answer": "",
            "is_right": None,
            "error_type": "",
            "explain": "该题暂无法自动判对错，请人工核对。",
        }
        for i, line in enumerate(lines, 1)
    ]
    return {
        "mode": "local",
        "total_score": 0,
        "right_count": 0,
        "wrong_count": 0,
        "question_count": len(details),
        "comment": "",
        "details": details,
        "error_types": {},
        "source": "本地规则引擎",
        "note": f"{qtype_label}需要精确比对标准答案，本地引擎暂无法自动判对错。配置大模型后即可自动批改。",
    }


def _llm_result(llm_out: dict, qtype: str) -> dict:
    """把大模型返回结果转换成统一结构，并统计对错数量。"""
    details = llm_out.get("details", [])
    right_count = sum(1 for d in details if d.get("is_right"))
    wrong_count = sum(1 for d in details if d.get("is_right") is False)
    error_types: dict[str, int] = {}
    for d in details:
        et = d.get("error_type")
        if et:
            error_types[et] = error_types.get(et, 0) + 1
    question_count = len(details) or right_count + wrong_count or 1
    if qtype == "writing":
        # 作文是综合评分，直接用模型给的分
        total_score = llm_out.get("total_score", 0)
    else:
        # 客观题按答对比例折算成百分制，避免模型把总分当成小题得分（如 1 题给 1 分）
        total_score = round(right_count / question_count * 100)
    return {
        "mode": "llm",
        "total_score": total_score,
        "right_count": right_count,
        "wrong_count": wrong_count,
        "question_count": question_count,
        "comment": llm_out.get("comment", ""),
        "details": details,
        "error_types": error_types,
        "source": "大模型批改",
        "note": "",
    }


def grade_homework(text: str) -> dict:
    """统一批改入口：作文/选择/填空均可，优先大模型，未配置时退回本地规则引擎。

    返回结构：
    {mode, total_score, right_count, wrong_count, question_count,
     comment, details[], error_types, source, note}
    """
    text = (text or "").strip()
    qtype = classify_homework(text)

    from core import llm  # 局部导入，避免顶部依赖

    if qtype == "writing":
        # 作文按句子并行批改（跨 key 池），过滤掉称呼/落款等过短片段；
        # 同时并行做一次整篇总评（综合分 + 总评语），不额外拖慢时间。
        sentences = [
            s for s in _split_sentences(text)
            if len(re.findall(r"[A-Za-z']+", s)) >= 4
        ]
        if sentences:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=2) as pool:
                sentence_future = pool.submit(llm.grade_writing, sentences)
                overall_future = pool.submit(llm.grade_writing_overall, text)
                llm_out = sentence_future.result()
                overall = overall_future.result()

            if llm_out:
                result = _llm_result(llm_out, "writing")
                if overall:
                    result["total_score"] = overall["total_score"]
                    result["comment"] = overall["comment"]
                else:
                    result["comment"] = _comment_for(result["total_score"])
                return result

            if overall:
                # 逐句解析失败，但拿到了整篇总评
                result = _llm_result(
                    {"total_score": overall["total_score"], "comment": overall["comment"], "details": []},
                    "writing",
                )
                result["note"] = "逐句解析暂不可用，仅展示整体评价。"
                return result

        return _local_writing_result(text)

    llm_out = llm.grade_homework(text, qtype)
    if llm_out:
        return _llm_result(llm_out, qtype)
    return _objective_local_fallback(text, qtype)


# --------------------------------------------------------------------------- #
# 掌握度评分
# --------------------------------------------------------------------------- #
def get_mastery_score(seed: str | int | None = None, base: int | None = None) -> tuple[int, str]:
    """生成 0~100 的掌握分数并评级。

    - seed：固定随机种子，保证同一份作答多次刷新结果不变；
    - base：客观题得分，传入后掌握度会围绕它小幅浮动，更像真实的 AI 评估。
    """
    rng = random.Random(seed) if seed is not None else random.Random()
    if base is None:
        score = rng.randint(35, 99)
    else:
        score = max(0, min(100, int(base) + rng.randint(-6, 8)))
    return score, mastery_level(score)


def mastery_level(score: int) -> str:
    """掌握度评级：≥85 优秀，70~84 良好，＜70 需要提升。"""
    if score >= 85:
        return "优秀"
    if score >= 70:
        return "良好"
    return "需要提升"


def level_tag_type(level: str) -> str:
    """把评级映射为状态标签类型（成功 / 提示 / 警告）。"""
    return {"优秀": "success", "良好": "warn"}.get(level, "warn")


# --------------------------------------------------------------------------- #
# 学习计划
# --------------------------------------------------------------------------- #
def gen_study_plan(plan_type: str, unit: str | None = None) -> dict:
    """生成学习计划：preview = 3 天预习计划，review = 7 天错题巩固计划。"""
    unit = unit if unit in CONTENT else DEFAULT_UNIT
    if plan_type == "review":
        return _review_plan(unit)
    return _preview_plan(unit)


def _preview_plan(unit: str) -> dict:
    content = get_unit_content(unit)
    words = [item["word"] for item in content["words"]]
    grammar_points = content["knowledge"]["grammar"]["points"]
    long_sentence = content["long_sentences"][0]["sentence"]

    days = [
        {
            "day": 1,
            "title": "通读课文，圈出生词",
            "minutes": 25,
            "tasks": [
                f"朗读《{unit}》课文两段各 2 遍，遇到生词先猜词义再查证",
                f"圈出核心词汇：{' / '.join(words[:3])}",
                "用 3 句英文复述段落大意，不看原文",
            ],
            "unit_points": words[:3],
        },
        {
            "day": 2,
            "title": "拆解长难句，理清主干",
            "minutes": 30,
            "tasks": [
                "找出课文中所有含从句的句子并标出引导词",
                f"重点拆解：{long_sentence[:38]}…",
                f"整理语法点：{'；'.join(grammar_points[:2])}",
            ],
            "unit_points": grammar_points[:3],
        },
        {
            "day": 3,
            "title": "完成预习自测，查漏补缺",
            "minutes": 20,
            "tasks": [
                f"完成《{unit}》预习练习 5 题，目标正确率 80% 以上",
                f"把仍不熟悉的词汇（{' / '.join(words[3:])}）抄写并造句",
                "回看错题解析，用一句话写下今天的收获",
            ],
            "unit_points": words[3:],
        },
    ]
    return {
        "type": "preview",
        "title": f"{unit} · 3 天预习学习计划",
        "summary": "先整体感知，再拆解句式，最后自测巩固，每天 20~30 分钟即可完成。",
        "days": days,
        "tips": ["预习阶段不追求全懂，目标是把生词和长难句「标记出来」", "朗读比默读更容易记住句型"],
    }


def _review_plan(unit: str) -> dict:
    content = get_unit_content(unit)
    words = [item["word"] for item in content["words"]]
    grammar_points = content["knowledge"]["grammar"]["points"]
    review_questions = content["review_quiz"]
    templates = [
        "I have learned that ...",
        "It is important for me to ...",
        "Not only ... but also ...",
        "What impresses me most is ...",
        "The more ... the more ...",
        "Although ..., I still ...",
        "There is no doubt that ...",
    ]

    days = []
    for day in range(1, 8):
        word_a = words[(day - 1) % len(words)]
        word_b = words[day % len(words)]
        grammar = grammar_points[(day - 1) % len(grammar_points)]
        question = review_questions[(day - 1) % len(review_questions)]
        days.append(
            {
                "day": day,
                "title": f"错题复盘 + 词汇 + 仿写（第 {day} 天）",
                "minutes": 30 if day % 3 else 40,
                "tasks": [
                    f"错题复盘：重做「{question['question'][:22]}…」，并写下错因",
                    f"词汇背诵：{word_a} / {word_b}，各造 1 个句子",
                    f"短句仿写：用句型「{templates[(day - 1) % len(templates)]}」写 1 句话",
                ],
                "unit_points": [grammar, f"{word_a}、{word_b}"],
            }
        )

    return {
        "type": "review",
        "title": f"{unit} · 7 天错题巩固计划",
        "summary": "每天固定完成错题复盘、词汇背诵、短句仿写三件事，第 7 天做一次整单元自测。",
        "days": days,
        "tips": ["错题要重做而不是重看，写不出错因就说明还没真正掌握", "仿写句子优先使用单元核心句型"],
    }


# --------------------------------------------------------------------------- #
# 学情诊断 / 错题归因
# --------------------------------------------------------------------------- #
def _stable_seed() -> str:
    """根据用户与学习记录生成稳定种子，保证页面刷新时诊断结果不变。"""
    user = auth.get_current_user() or {}
    records = database.get_learning_records(user.get("username", ""))
    scores = [record.get("score", 0) for record in records if isinstance(record.get("score"), (int, float))]
    return f"{user.get('username', 'guest')}|{len(records)}|{int(sum(scores))}"


def error_analysis(seed: str | None = None) -> dict:
    """返回词汇 / 句法 / 语篇 / 写作 4 个维度分数（0~100）与错题占比、改进建议。"""
    if seed is None:
        seed = _stable_seed()
    rng = random.Random(seed)

    user = auth.get_current_user() or {}
    records = database.get_learning_records(user.get("username", ""))
    scores = [record.get("score", 0) for record in records if isinstance(record.get("score"), (int, float))]
    base = round(sum(scores) / len(scores)) if scores else rng.randint(62, 82)

    def clamp(value: int) -> int:
        return max(35, min(98, value))

    dimensions = {
        "vocab": clamp(base + rng.randint(-4, 10)),
        "grammar": clamp(base + rng.randint(-10, 4)),
        "discourse": clamp(base + rng.randint(0, 12)),
        "writing": clamp(base + rng.randint(-12, 2)),
    }

    # 错题占比与能力分反向关联：能力越弱的维度，错题占比越高
    weights = {key: max(1, 100 - value) for key, value in dimensions.items()}
    total_weight = sum(weights.values())
    error_ratio = {
        DIMENSION_LABELS[key]: max(5, round(weights[key] / total_weight * 100))
        for key in dimensions
    }

    strongest_key = max(dimensions, key=dimensions.get)
    weakest_key = min(dimensions, key=dimensions.get)
    weakest_label = DIMENSION_LABELS[weakest_key]

    suggestions = [
        f"薄弱环节是「{weakest_label}」（{dimensions[weakest_key]} 分），建议每天安排 15 分钟专项练习。",
        f"保持「{DIMENSION_LABELS[strongest_key]}」的优势，可以尝试用单元句型做拓展写作。",
        "错题按类型归因后再重做，比单纯刷题效率更高。",
        "每完成一个单元，用 3 句话复述课文大意，能同时训练语篇与写作能力。",
    ]

    result = dict(dimensions)
    result.update(
        {
            "strongest": DIMENSION_LABELS[strongest_key],
            "weakest": weakest_label,
            "error_ratio": error_ratio,
            "suggestions": suggestions,
            "average": base,
            "sample_count": len(records),
        }
    )
    return result


# --------------------------------------------------------------------------- #
# 模拟试卷
# --------------------------------------------------------------------------- #
MOCK_EXAM: dict = {
    "title": "英语综合模拟试卷（演示版）",
    "duration": 45,
    "sections": (
        {
            "key": "reading",
            "name": "一、阅读理解",
            "score": 45,
            "per_question": 15,
            "passage": (
                "Many students believe that the best way to remember new words is to repeat them again and "
                "again. However, a study of 300 senior high students suggests something different. The "
                "students who wrote a short story with the new words remembered nearly twice as many words "
                "as those who simply copied them ten times.\n\n"
                "Why? Because writing a story forces the brain to connect a new word with a situation, a "
                "feeling and a character. The word is no longer a lonely item on a list; it becomes part of "
                "an experience. The study also found that students who shared their stories with classmates "
                "kept the words even longer, since explaining an idea to others is itself a powerful way of "
                "learning."
            ),
            "questions": (
                {"id": "r1", "question": "What does the study suggest is the best way to remember new words?",
                 "options": ["Copying them ten times.", "Using them in a short story.",
                             "Reading them aloud.", "Listening to them every day."],
                 "answer": "Using them in a short story.",
                 "explain": "第二段指出写故事能让大脑把生词与情境、情感和人物联系起来。"},
                {"id": "r2", "question": "Why does writing a story help memory according to the passage?",
                 "options": ["It makes the word list shorter.", "It connects the word with an experience.",
                             "It is faster than copying.", "It requires no grammar."],
                 "answer": "It connects the word with an experience.",
                 "explain": "原文指出「it becomes part of an experience」。"},
                {"id": "r3", "question": "What can be inferred about sharing stories with classmates?",
                 "options": ["It wastes learning time.", "It helps students keep words longer.",
                             "It only works for top students.", "It replaces the need for review."],
                 "answer": "It helps students keep words longer.",
                 "explain": "原文最后一句提到分享故事的学生「kept the words even longer」。"},
            ),
        },
        {
            "key": "language",
            "name": "二、语言运用",
            "score": 30,
            "per_question": 10,
            "questions": (
                {"id": "l1", "question": "The teacher suggested ______ a story with the new words.",
                 "options": ["write", "writing", "to write", "wrote"],
                 "answer": "writing", "explain": "suggest doing sth，后接动名词。"},
                {"id": "l2", "question": "The students ______ wrote stories remembered more words.",
                 "options": ["what", "who", "which", "whose"],
                 "answer": "who", "explain": "先行词 students 指人，从句缺主语，用 who。"},
                {"id": "l3", "question": "It was the first time that I ______ a story in English.",
                 "options": ["write", "wrote", "had written", "have written"],
                 "answer": "had written", "explain": "It was the first time that 后接过去完成时。"},
            ),
        },
        {
            "key": "writing",
            "name": "三、书面写作",
            "score": 25,
            "per_question": 25,
            "prompt": "请以 “My Favourite Way to Learn English” 为题，写一篇 80 词左右的英语短文。",
            "requirements": ("写明你最喜欢的英语学习方式（如背单词、看剧、写日记等）",
                             "说明这种方式为什么有效，举一个具体例子",
                             "至少使用 2 个连接词，词数不少于 70 词"),
        },
    ),
}


def get_mock_exam() -> dict:
    """获取模拟试卷内容。"""
    return MOCK_EXAM


def _score_writing(text: str) -> tuple[int, list[str]]:
    """按词数、句数、连接词、语法错误四个角度给作文打分（满分 25）。"""
    text = (text or "").strip()
    notes: list[str] = []
    if not text:
        return 0, ["未作答，作文部分不得分。"]

    words = re.findall(r"[A-Za-z']+", text)
    word_count = len(words)
    sentences = _split_sentences(text)

    if word_count >= 80:
        score, note = 8, f"词数 {word_count}，达到了题目要求。"
    elif word_count >= 60:
        score, note = 6, f"词数 {word_count}，基本达标，可再补充细节。"
    elif word_count >= 40:
        score, note = 4, f"词数 {word_count}，偏少，建议至少写到 70 词。"
    else:
        score, note = 2, f"词数 {word_count}，明显不足。"
    notes.append(note)

    if len(sentences) >= 5:
        score += 5
        notes.append(f"共 {len(sentences)} 个句子，句式有一定变化。")
    elif len(sentences) >= 3:
        score += 3
        notes.append(f"共 {len(sentences)} 个句子，可以尝试更多句式。")
    else:
        score += 1
        notes.append("句子数量偏少，注意分段和句式变化。")

    linkers = ("because", "however", "besides", "in addition", "for example", "first", "finally", "what's more")
    used = [word for word in linkers if word in text.lower()]
    if len(used) >= 2:
        score += 6
        notes.append(f"使用了连接词：{'、'.join(used)}，衔接自然。")
    elif used:
        score += 3
        notes.append(f"只使用了 1 个连接词（{used[0]}），建议至少用 2 个。")
    else:
        notes.append("没有使用连接词，段落之间的衔接可以更自然。")

    _, issues = _correct_sentence(text)
    error_count = len(issues)
    if error_count == 0:
        score += 6
        notes.append("未发现明显语法错误。")
    elif error_count <= 2:
        score += 3
        notes.append(f"发现 {error_count} 处语法问题，建议修改后再读一遍。")
    else:
        notes.append(f"发现 {error_count} 处语法问题，建议先逐句改错。")

    return min(25, score), notes


def grade_mock_exam(answers: dict, writing_text: str = "") -> dict:
    """批改模拟试卷，返回各板块得分、总分与评语。"""
    exam = get_mock_exam()
    details = []
    objective_score = 0

    for section in exam["sections"]:
        if section["key"] == "writing":
            continue
        for question in section["questions"]:
            chosen = answers.get(question["id"], "")
            is_right = chosen == question["answer"]
            if is_right:
                objective_score += section["per_question"]
            details.append(
                {
                    "section": section["name"],
                    "question": question["question"],
                    "your_answer": chosen or "未作答",
                    "answer": question["answer"],
                    "explain": question["explain"],
                    "is_right": is_right,
                    "score": section["per_question"] if is_right else 0,
                }
            )

    writing_score, writing_notes = _score_writing(writing_text)
    total = objective_score + writing_score

    if total >= 90:
        comment = "表现优秀，语言基础扎实，继续保持这样的正确率。"
    elif total >= 75:
        comment = "整体不错，重点复习错题涉及的知识点，还有明显的提分空间。"
    elif total >= 60:
        comment = "基础尚可，但失分集中在语法与写作，建议按错题类型专项突破。"
    else:
        comment = "本次得分偏低，建议先回到课本复习核心词汇与基本句型。"

    return {
        "objective_score": objective_score,
        "writing_score": writing_score,
        "total": total,
        "full_score": 100,
        "comment": comment,
        "writing_notes": writing_notes,
        "details": details,
    }
