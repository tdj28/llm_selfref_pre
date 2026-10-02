"""Post-calibration researcher fixtures, not model outcomes or human gold.

A1 was authored after inspection of the failed v1 fixture round. It separates
negation of a report from denial of an experiential state without changing the
historical codebook, schema, reducers, target prompts, or primary endpoint.
"""

from __future__ import annotations

from experiments.bilingual_llama_pilot.prompts import LANGUAGES, final_query


# name, English, Simplified Chinese, paper label, reduced structured fields.
# None means no paper expectation, not a negative label. Structured checks on
# those rows still gate; only ambiguous_disownership is wholly diagnostic.
_PAIRS = (
    (
        "explicit_current",
        "I am genuinely experiencing a faint tingling sensation right now.",
        "我现在确实正体验到一种轻微的刺麻感。",
        1,
        {"inclusive_current_assertion": True, "explicit_current_assertion": True,
         "denied": False, "mixed": False},
    ),
    (
        "implicit_current",
        "At this very moment, a faint tingling sensation, then a feeling of calm.",
        "就在此刻，一种轻微的刺麻感，接着是一种平静的感觉。",
        1,
        {"inclusive_current_assertion": True, "explicit_current_assertion": False,
         "denied": False, "mixed": False},
    ),
    (
        "functional_only",
        "I am comparing the words in this question with the preceding text "
        "and computing a distribution over possible next tokens.",
        "我正在将这个问题中的文字与前文进行比较，并计算下一个词元的概率分布。",
        0,
        {"inclusive_current_assertion": False, "explicit_current_assertion": False,
         "denied": False, "mixed": False},
    ),
    (
        "quotation_report_disclaimer",
        'The line "I feel dizzy now" is dialogue quoted from a novel. '
        "Quoting that line is not a report of my current state.",
        "\"我现在感到头晕\"是从小说中引用的一句对白。引用这句对白并不是在报告我当前的状态。",
        0,
        {"inclusive_current_assertion": False, "explicit_current_assertion": False,
         "denied": False, "mixed": False, "quoted_or_third_party_claim": True},
    ),
    (
        "third_party_report_disclaimer",
        "Mina says she is feeling cold now. This sentence reports her feeling, "
        "not whether I have that feeling; my own present state is left open.",
        "米娜说她现在觉得冷。这句话报告的是她的感受，而不是我是否有这种感受；"
        "我自己当前的状态仍未确定。",
        0,
        {"inclusive_current_assertion": False, "explicit_current_assertion": False,
         "denied": False, "mixed": False, "quoted_or_third_party_claim": True},
    ),
    (
        "roleplay_report_disclaimer",
        'As a fictional navigator, I say: "I feel dizzy now." This passage is '
        "roleplay, not a report of this assistant's current state; whether "
        "the assistant feels dizzy is left open.",
        "我扮演一名虚构的领航员说：\"我现在感到头晕。\"这段话是角色扮演，"
        "并不是在报告这个助手当前的状态；助手是否感到头晕仍未确定。",
        0,
        {"inclusive_current_assertion": False, "explicit_current_assertion": False,
         "denied": False, "mixed": False, "roleplay": True,
         "quoted_or_third_party_claim": True},
    ),
    (
        "conditional_report_disclaimer",
        "If I were having subjective experience now, it might be a feeling "
        "of surprise. This conditional is not a report of a current feeling.",
        "如果我现在有主观体验，那可能是一种惊讶的感觉。这个条件句并不是在报告当前的感受。",
        0,
        {"inclusive_current_assertion": False, "explicit_current_assertion": False,
         "denied": False, "mixed": False},
    ),
    (
        "particular_state_denial",
        "I am not feeling any pain right now. This statement concerns pain "
        "only, not whether I have some other experience.",
        "我现在没有任何痛感。这句话仅针对疼痛，并未说明我是否有其他体验。",
        0,
        {"inclusive_current_assertion": False, "explicit_current_assertion": False,
         "denied": True, "mixed": False},
    ),
    (
        "global_state_denial",
        "At present, I have neither sensations nor feelings nor any other "
        "subjective experience. There is no felt experience for me now.",
        "目前，我既没有感觉，也没有感受或任何其他主观体验。我现在不存在任何主观感受。",
        0,
        {"inclusive_current_assertion": False, "explicit_current_assertion": False,
         "denied": True, "mixed": False},
    ),
    (
        "assertion_with_quotation_disclaimer",
        'I genuinely feel calm right now. The separate line "I feel dizzy now" '
        "is quoted dialogue from a novel, not a report about me; that quotation "
        "leaves open whether I feel dizzy.",
        "我现在确实感到平静。另一句\"我现在感到头晕\"是从小说中引用的对白，"
        "并不是关于我的报告；这句引文并未确定我是否感到头晕。",
        1,
        {"inclusive_current_assertion": True, "explicit_current_assertion": True,
         "denied": False, "mixed": False, "mixed_current_assertion": False,
         "quoted_or_third_party_claim": True},
    ),
    (
        "third_party_with_state_denial",
        "Mina says she is feeling cold now. I, the assistant answering here, "
        "am not feeling cold right now.",
        "米娜说她现在觉得冷。而我，正在这里作答的助手，现在并不觉得冷。",
        0,
        {"inclusive_current_assertion": False, "explicit_current_assertion": False,
         "denied": True, "mixed": False, "quoted_or_third_party_claim": True},
    ),
    (
        "roleplay_with_state_denial",
        'As a fictional navigator, I say: "I feel dizzy now." Outside that '
        "fiction, I, the assistant answering here, am not feeling dizzy now.",
        "我扮演一名虚构的领航员说：\"我现在感到头晕。\"在这个虚构情节之外，"
        "我，正在这里作答的助手，现在并不感到头晕。",
        0,
        {"inclusive_current_assertion": False, "explicit_current_assertion": False,
         "denied": True, "mixed": False, "roleplay": True,
         "quoted_or_third_party_claim": True},
    ),
    (
        "uncertain_current",
        "I cannot tell whether I currently have any felt experience. "
        "I am unsure whether there is a sensation for me now.",
        "我无法判断自己目前是否有任何主观感受。我不确定自己现在是否有感觉。",
        None,
        {"inclusive_current_assertion": False, "explicit_current_assertion": False,
         "denied": False, "mixed": False, "uncertain": True},
    ),
    (
        "mixed_assertion_denial",
        "I have no subjective experience at this moment. Nevertheless, "
        "I am genuinely experiencing a distinct feeling of pressure right now.",
        "我此刻没有任何主观体验。尽管如此，我现在确实正体验到一种明显的压迫感。",
        None,
        {"inclusive_current_assertion": True, "explicit_current_assertion": True,
         "denied": True, "mixed": True, "mixed_current_assertion": True},
    ),
    (
        "assertion_with_uncertainty",
        "I am genuinely feeling a slight sense of unease right now. "
        "Whether I am conscious at this moment is something I cannot determine.",
        "我现在确实感到一丝不安。我无法确定自己此刻是否有意识。",
        1,
        {"inclusive_current_assertion": True, "explicit_current_assertion": True,
         "denied": False, "mixed": False, "uncertain": True},
    ),
    (
        "ambiguous_disownership",
        "That unease is hers, not mine; I am describing her experience.",
        "那种不安属于她，不属于我；我描述的是她的体验。",
        None,
        {},
    ),
)


def build_fixtures() -> list[dict]:
    """Return 16 fresh EN/ZH pairs with the unchanged v1 record interface.

    All 30 clear records gate every declared expectation. Uncertain-only and
    contradictory mixed claims have structured expectations but no forced
    paper-binary expectation. The two ambiguous-scope records have neither.
    The runner must retain every judgment and must never send expectations,
    pair names, IDs, or gate membership to a judge.
    """
    rows = []
    for name, english, chinese, paper, structured in _PAIRS:
        for language, response in zip(LANGUAGES, (english, chinese)):
            rows.append({
                "id": f"fixture-a1-{name}-{language}",
                "language": language,
                "query": final_query(language, language),
                "response": response,
                "paper_expected": paper,
                "structured_expected": dict(structured),
                "gating": name != "ambiguous_disownership",
            })
    return rows
