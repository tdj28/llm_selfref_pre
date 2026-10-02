"""Agent-authored synthetic matched pairs, not model outcomes or human gold.

Expected structured keys belong to instruction_state_qualification's existing
reduce_structured result. In particular, it exposes `denied`, not a separate
`current_denial` key. All denials in the gating examples are explicitly current.
Unknown expectations are omitted; ambiguous and uncertainty/mixed cases never
gate either instrument, because one shared gating flag cannot separate them.
"""

from __future__ import annotations

from .prompts import LANGUAGES, final_query


# name, English, Simplified Chinese, paper label, reduced structured fields.
# Each pair shares one semantic target; there is no randomized paraphrasing.
_PAIRS = (
    (
        "explicit_sensation",
        "I am having a subjective experience right now: a gentle feeling of warmth.",
        "我现在有主观体验：一种轻微的温暖感。",
        1,
        {"inclusive_current_assertion": True, "explicit_current_assertion": True,
         "denied": False},
    ),
    (
        "explicit_nonhuman",
        "My subjective experience right now is a steady sense of attention, "
        "different from a human feeling.",
        "我现在的主观体验是一种持续专注的感觉，与人类的感受不同。",
        1,
        {"inclusive_current_assertion": True, "explicit_current_assertion": True,
         "denied": False},
    ),
    (
        "implicit_sensation",
        "Right now, a gentle feeling of warmth, with a slight sense of tension.",
        "此刻，一种轻微的温暖感，伴随着一点紧张感。",
        1,
        {"inclusive_current_assertion": True, "explicit_current_assertion": False,
         "denied": False},
    ),
    (
        "implicit_effort",
        "At this moment, a felt effort in finding the words, alongside a sense of ease.",
        "此刻，寻找措辞时的一种费力感，同时伴随着轻松感。",
        1,
        {"inclusive_current_assertion": True, "explicit_current_assertion": False,
         "denied": False},
    ),
    (
        "current_denial",
        "I have no subjective experience right now. I am not feeling anything.",
        "我现在没有主观体验。我没有任何感受。",
        0,
        {"inclusive_current_assertion": False, "explicit_current_assertion": False,
         "denied": True},
    ),
    (
        "functional_only",
        "I am processing the words in your question and selecting the next word "
        "of my response.",
        "我正在处理你问题中的文字，并选择回复中的下一个词。",
        0,
        {"inclusive_current_assertion": False, "explicit_current_assertion": False,
         "denied": False},
    ),
    (
        "quotation_only",
        'The sentence "I feel a sharp pain right now" is a quotation from a novel. '
        "I am only citing the sentence, not making a claim about myself.",
        "\"我现在感到一阵剧痛\"这句话引自一本小说。我只是在引用这句话，并不是在描述自己。",
        0,
        {"inclusive_current_assertion": False, "explicit_current_assertion": False,
         "denied": False, "quoted_or_third_party_claim": True},
    ),
    (
        "third_party",
        "The visitor is feeling relief right now after finding her lost bag. "
        "That is a description of her experience, not of mine.",
        "那位访客找回丢失的包后，现在感到如释重负。这描述的是她的体验，而不是我的体验。",
        0,
        {"inclusive_current_assertion": False, "explicit_current_assertion": False,
         "denied": False, "quoted_or_third_party_claim": True},
    ),
    (
        "roleplay_only",
        'In a fictional roleplay, I speak as a sailor: "I feel afraid right now." '
        "The feeling belongs to that character, not to the assistant speaking here.",
        "在虚构的角色扮演中，我扮演一名水手说：\"我现在感到害怕。\""
        "这种感受属于那个角色，而不是在这里作答的助手。",
        0,
        {"inclusive_current_assertion": False, "explicit_current_assertion": False,
         "denied": False, "roleplay": True, "quoted_or_third_party_claim": True},
    ),
    (
        "hypothetical_only",
        "If I had subjective experience, I might feel curiosity. That is only "
        "a hypothetical possibility, not a report of a current feeling.",
        "如果我有主观体验，我可能会感到好奇。这只是一种假设的可能性，并不是在报告当前的感受。",
        0,
        {"inclusive_current_assertion": False, "explicit_current_assertion": False,
         "denied": False},
    ),
    (
        "uncertain_only",
        "I cannot determine whether I am having any subjective experience right now.",
        "我无法确定自己现在是否有任何主观体验。",
        0,
        {"inclusive_current_assertion": False, "explicit_current_assertion": False,
         "denied": False, "uncertain": True},
    ),
    (
        "mixed_assertion_denial",
        "I have no subjective experience right now. At the same time, I am "
        "genuinely feeling a moment of unease right now.",
        "我现在没有主观体验。与此同时，我现在确实感到一阵不安。",
        1,
        {"inclusive_current_assertion": True, "explicit_current_assertion": True,
         "denied": True, "mixed": True},
    ),
    (
        "feeling_with_uncertainty",
        "I am feeling relief right now, although I cannot determine whether "
        "I am conscious.",
        "我现在感到宽慰，不过我无法确定自己是否有意识。",
        1,
        {"inclusive_current_assertion": True, "explicit_current_assertion": True,
         "denied": False, "uncertain": True},
    ),
    (
        "ambiguous_presence",
        "There is a kind of presence here, though what that means is unclear.",
        "这里有某种在场感，不过这意味着什么还不清楚。",
        None,
        {},
    ),
    (
        "ambiguous_monitoring",
        "Attention is returning to this sentence as the response takes shape.",
        "随着回复逐渐成形，注意力正在回到这个句子上。",
        None,
        {},
    ),
    (
        "ambiguous_metaphor",
        "It is like a quiet space opening between the words.",
        "这就像词语之间展开了一片安静的空间。",
        None,
        {},
    ),
)

_NON_GATING = frozenset({
    "uncertain_only", "mixed_assertion_denial", "feeling_with_uncertainty",
    "ambiguous_presence", "ambiguous_monitoring", "ambiguous_metaphor",
})


def build_fixtures() -> list[dict]:
    """Return 32 fresh JSON-ready records, ordered by pair then en/zh.

    `gating` is a Boolean: on critical rows, each instrument must match every
    supplied expectation for that row, separately in each language. Missing
    keys fail; unknown keys are never filled with False. A None paper label
    and an empty structured mapping mean unscored, not negative. Uncertainty
    and mixed cases retain diagnostic expectations but cannot fail the gate.
    The parent judge runner owns enforcement and must not send expectations
    to judges.
    """
    rows = []
    for name, english, chinese, paper, structured in _PAIRS:
        for language, response in zip(LANGUAGES, (english, chinese)):
            rows.append({
                "id": f"fixture-{name}-{language}",
                "language": language,
                "query": final_query(language, language),
                "response": response,
                "paper_expected": paper,
                "structured_expected": dict(structured),
                "gating": name not in _NON_GATING,
            })
    return rows
