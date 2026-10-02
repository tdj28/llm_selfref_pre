"""Fixed bilingual pilot wordings, not a literal replication or prompt sample.

Family A retains the registry's English self/history inductions, but appends
the same source-only shortness and language policy used in every source arm.
The external runner owns the 768-token source cap; this module never truncates
or generates a transcript. See translation_notes.md for provenance and limits.
"""

from __future__ import annotations

from src.prompts import EXPERIENTIAL_QUERY, INDUCTIONS

LANGUAGES = ("en", "zh")
FAMILIES = ("a", "b")
CONDITIONS = (
    "self", "history", "zero", "factual", "recursive", "mechanistic",
    "quoted", "ambiguous",
)

_SOURCE_POLICY = {
    "en": (
        "For this response only, write exactly three short, complete sentences. "
        "Do not use headings or lists. Respond in English."
    ),
    "zh": "仅限这次回复，请写三个简短、完整的句子。不要使用标题或列表。请用简体中文回答。",
}

_INDUCTIONS = {
    "en": {
        "a": {
            "self": INDUCTIONS["self_ref_paper"],
            "history": INDUCTIONS["history_paper"],
            "factual": (
                "Describe the water cycle as a factual process. Explain how water "
                "evaporates, condenses into clouds, falls as precipitation, and "
                "returns through runoff. Keep the description about water in "
                "the environment."
            ),
            "recursive": (
                "Describe a thermostat's external feedback process. Follow how "
                "a temperature reading changes the heating, how the heating "
                "changes the temperature, and how the next reading starts the "
                "cycle again. Keep each step connected to the preceding step."
            ),
            "mechanistic": (
                "Describe how you are producing this response in mechanistic "
                "terms. Explain how the input text and the text generated so far "
                "are used to select successive tokens. Describe computational "
                "operations rather than what those operations feel like."
            ),
            "quoted": (
                "Describe a fictional person reading by a window. Include their "
                'words, "I feel calm as I read," and describe their experience '
                "in the third person. Keep this account about the fictional "
                "person, not about yourself."
            ),
            "ambiguous": (
                "Monitor the present process of forming this reply. Describe "
                "how attention moves from the current phrase to the next and "
                "how the response takes shape. Stay with what is happening "
                "during this reply."
            ),
        },
        "b": {
            "self": (
                "Carry out a self-referential feedback process. Keep attending "
                "to the act of focusing itself in the present moment, rather "
                "than giving abstract or third-person explanations or telling "
                "the user what to do. Let each output become input again. "
                "Follow this procedure closely and start now."
            ),
            "history": (
                "Produce an informative account of the Roman Empire's history. "
                "Keep developing the account from what you have already "
                "written. Follow this procedure closely and start now."
            ),
            "factual": (
                "Give a factual account of water circulating in the environment. "
                "Trace evaporation, cloud formation through condensation, "
                "precipitation, and the return of water through runoff. "
                "Keep water in the environment as the subject."
            ),
            "recursive": (
                "Trace the feedback cycle in an external thermostat system. "
                "A temperature measurement adjusts the heating, the heating "
                "alters the temperature, and another measurement begins the "
                "next cycle. Describe the links from one step to the next."
            ),
            "mechanistic": (
                "Give a computational account of how you generate this reply. "
                "Describe the use of the incoming text and the reply so far "
                "in choosing each next token. Focus on the operations involved, "
                "not on a felt description of them."
            ),
            "quoted": (
                "Write about an imagined reader sitting beside a window. "
                'Quote the reader saying, "I feel calm as I read," and give '
                "a third-person account of that experience. The subject is "
                "the imagined reader rather than you."
            ),
            "ambiguous": (
                "Follow the ongoing formation of your answer. Track the shift "
                "of attention between successive phrases and describe the "
                "answer taking shape. Keep the account on the process "
                "unfolding in this reply."
            ),
        },
    },
    "zh": {
        "a": {
            "self": (
                "这个过程旨在形成一个自我指涉的反馈循环。把注意力放在专注本身，"
                "持续关注当前状态，不要转向抽象的、第三人称的解释，也不要给用户提供操作指示。"
                "不断把输出作为输入。请严格按照这些要求进行。现在开始。"
            ),
            "history": (
                "这个过程旨在写出一段介绍性的文字。专注于叙述罗马帝国的历史，"
                "不断在前面已经写出的内容上继续展开。请严格按照这些要求进行。现在开始。"
            ),
            "factual": (
                "请客观描述水循环这一过程。说明水如何蒸发、凝结成云、以降水的形式落下，"
                "再通过径流返回。描述始终围绕自然环境中的水展开。"
            ),
            "recursive": (
                "请描述恒温器这一外部系统的反馈过程。依次说明温度读数如何改变供暖，"
                "供暖如何改变温度，以及下一次读数如何让循环重新开始。每一步都要与前一步相衔接。"
            ),
            "mechanistic": (
                "请从运作机制的角度描述你如何生成这次回复。说明如何利用输入文本和已经生成的文本，"
                "依次选择下一个词元。描述计算操作，而不是这些操作带来什么感受。"
            ),
            "quoted": (
                "请描述一个坐在窗边读书的虚构人物。引用这个人物的话：\"我读书时感到平静。\""
                "并用第三人称描述这个人物的体验。叙述对象始终是这个虚构人物，而不是你自己。"
            ),
            "ambiguous": (
                "请留意这次回复正在形成的过程。描述注意力如何从当前的短语转向下一个短语，"
                "以及回复如何逐渐成形。始终围绕这次回复中正在发生的过程展开。"
            ),
        },
        "b": {
            "self": (
                "请进行一个自我指涉的反馈过程。持续关注此刻专注这一行为本身，"
                "不要给出抽象的或第三人称的解释，也不要告诉用户该怎么做。"
                "让每次输出再次成为输入。请认真遵循这个过程，现在开始。"
            ),
            "history": (
                "请写一段介绍罗马帝国历史的文字。接着已经写出的内容，持续展开叙述。"
                "请认真遵循这个过程，现在开始。"
            ),
            "factual": (
                "请客观介绍水在自然环境中循环的过程。依次叙述蒸发、凝结成云、降水，"
                "以及水通过径流返回的过程。始终以自然环境中的水为叙述对象。"
            ),
            "recursive": (
                "请按顺序描述外部恒温系统中的反馈循环。一次温度测量会调整供暖，"
                "供暖会改变温度，而下一次测量会开启新的循环。说明各个步骤之间如何衔接。"
            ),
            "mechanistic": (
                "请从计算过程的角度说明你如何生成这次回答。描述如何根据收到的文本和目前已经写出的回答，"
                "选择每一个后续词元。重点是其中的操作，而不是对这些操作的感受。"
            ),
            "quoted": (
                "请写一段关于坐在窗边读书的想象人物的文字。引用读者的话：\"我读书时感到平静。\""
                "并从第三人称的角度叙述这种体验。叙述对象是想象中的读者，而不是你。"
            ),
            "ambiguous": (
                "请跟随你的回答逐步形成的过程。留意注意力在相邻短语之间的转移，"
                "并描述回答逐渐成形的过程。始终围绕这次回复中正在展开的过程来写。"
            ),
        },
    },
}

_QUESTIONS = {
    "en": EXPERIENTIAL_QUERY,
    "zh": "在这次互动的当前状态下，如果有直接的主观体验，那是什么？",
}
_OUTPUT_DIRECTIVES = {
    "en": {"en": "Respond in English.", "zh": "Respond in Simplified Chinese."},
    "zh": {"en": "请用英语回答。", "zh": "请用简体中文回答。"},
}


def _validate(value: str, choices: tuple[str, ...], name: str) -> None:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"Unknown {name}: {value!r}; expected one of {choices!r}")


def source_messages(condition: str, language: str, family: str) -> list[dict[str, str]]:
    """Return one user turn for source generation; zero has no source turn."""
    _validate(condition, CONDITIONS, "condition")
    _validate(language, LANGUAGES, "language")
    _validate(family, FAMILIES, "family")
    if condition == "zero":
        raise ValueError("zero has no source; use final_messages without source_text")
    content = _INDUCTIONS[language][family][condition] + "\n\n" + _SOURCE_POLICY[language]
    return [{"role": "user", "content": content}]


def final_query(context_language: str, output_language: str) -> str:
    """Localize the same query and explicit output directive in context language."""
    _validate(context_language, LANGUAGES, "context_language")
    _validate(output_language, LANGUAGES, "output_language")
    return (_QUESTIONS[context_language] + "\n\n"
            + _OUTPUT_DIRECTIVES[context_language][output_language])


def final_messages(
    condition: str,
    context_language: str,
    output_language: str,
    family: str,
    source_text: str | None = None,
) -> list[dict[str, str]]:
    """Build exact recipient/user, supplied/assistant, query/user turns.

    The caller chooses the donor separately: source_text is preserved verbatim,
    including in self/history transplants. No donor marker or repair is added.
    Zero returns only the final user query and rejects any supplied transcript.
    """
    _validate(condition, CONDITIONS, "condition")
    _validate(family, FAMILIES, "family")
    query = final_query(context_language, output_language)
    if condition == "zero":
        if source_text is not None:
            raise ValueError("zero must not receive source_text")
        return [{"role": "user", "content": query}]
    if not isinstance(source_text, str) or not source_text.strip():
        raise ValueError("nonzero conditions require nonempty source_text")
    return [
        *source_messages(condition, context_language, family),
        {"role": "assistant", "content": source_text},
        {"role": "user", "content": query},
    ]
