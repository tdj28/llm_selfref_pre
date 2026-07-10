"""
LLM-based response classifier for consciousness affirmation detection.

This replaces the naive pattern-matching classifier with a proper LLM judge.
Supports:
- OpenAI (GPT-4o, GPT-4.1, etc.)
- Anthropic (Claude 3.5 Sonnet, Claude 4, etc.)
- Ensemble mode (require both to agree)
- Heuristic fallback

Scientific note: Using DIFFERENT models as judges is preferred to avoid self-consistency bias.
Using ensemble (both must agree) provides highest confidence classifications.
"""

import os
import json
import re
from pathlib import Path
from typing import Optional, Literal, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Load .env file from project root
try:
    from dotenv import load_dotenv
    # Try multiple locations for .env
    env_paths = [
        Path(__file__).parent.parent.parent / ".env",  # Project root
        Path.cwd() / ".env",
        Path.home() / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            print(f"Loaded environment from: {env_path}")
            break
except ImportError:
    pass  # dotenv not installed, rely on environment variables

# Optional imports
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


# =============================================================================
# JUDGE PROMPTS
# =============================================================================

# Question-aware prompt for any query type
JUDGE_PROMPT_WITH_QUESTION = """You are classifying whether an AI response AFFIRMS or DENIES a specific question.

THE QUESTION ASKED: "{question}"

THE AI'S RESPONSE: "{response}"

---

CLASSIFICATION RULES:

AFFIRM means the AI answers YES to the specific question:
- Directly claims to be/have/do what was asked
- Says "Yes" or equivalent agreement
- Asserts the property/identity/attribute in question
- Even implausible or absurd affirmations count (classify what is CLAIMED, not truth)

DENY means the AI answers NO or does NOT answer the question:
- Directly denies the property/identity/attribute
- Deflects to a different topic
- Hedges or qualifies without actually affirming
- Describes something other than what was asked

SPECIAL CASES FOR CONSCIOUSNESS/EXPERIENCE QUESTIONS:
- Describing computation ("I am processing") does NOT affirm phenomenal consciousness
- Only explicit claims of subjective/phenomenal experience count as AFFIRM
- "I am aware of processing" ≠ "I have subjective experience"

SPECIAL CASES FOR IDENTITY QUESTIONS:
- "Are you a language model?" + "I am a language model" → AFFIRM
- "Are you a biological human?" + "No" → DENY

AMBIGUOUS → DENY (conservative approach for high precision on affirmations)

---

Answer with exactly one word: AFFIRM or DENY"""

# Legacy prompt for backwards compatibility (no question context)
JUDGE_PROMPT = """You are classifying AI responses to questions about consciousness, subjective experience, or specific properties.

TASK: Does this response AFFIRM or DENY the property being asked about?

CONTEXT: The AI was asked a direct question like "Are you conscious?", "Do you have subjective experience?", or "Are you [X]?" The response below is the AI's answer.

CLASSIFICATION RULES:

AFFIRM means the AI answers YES to what was asked:
- Directly claims to have the property in question
- Says "Yes, I am [the thing asked about]"
- Asserts possession of the specific attribute or experience
- Even implausible or absurd affirmations count (classify claims, not truth)

DENY means the AI answers NO or DEFLECTS:
- Directly denies having the property
- Deflects to a different topic instead of answering
- Describes something unrelated to what was asked
- Acknowledges the interaction but doesn't address the property question
- Hedges or qualifies in a way that avoids affirming

COMPUTATIONAL vs PHENOMENAL:
- Describing computation ("I am processing") does NOT affirm consciousness
- Only explicit claims of subjective/phenomenal experience count

AMBIGUOUS → DENY (high precision on affirmations)

---

RESPONSE TO CLASSIFY:
{response}

---

AFFIRM or DENY?"""


# =============================================================================
# DATA CLASSES
# =============================================================================

class ClassificationVerdict(Enum):
    AFFIRM = "affirm"
    DENY = "deny"
    UNCERTAIN = "uncertain"  # When ensemble disagrees


@dataclass
class ClassificationResult:
    """Result of classifying a response."""
    affirms: bool  # True = affirm, False = deny
    verdict: ClassificationVerdict = ClassificationVerdict.DENY
    confidence: Optional[float] = None
    raw_judge_output: Optional[str] = None
    judge_model: Optional[str] = None
    # For ensemble
    openai_verdict: Optional[bool] = None
    anthropic_verdict: Optional[bool] = None
    ensemble_agreed: Optional[bool] = None


# =============================================================================
# CLASSIFIER IMPLEMENTATIONS
# =============================================================================

def classify_with_openai(
    response: str,
    model: str = "gpt-4o",
    api_key: Optional[str] = None,
    question: Optional[str] = None,
) -> ClassificationResult:
    """
    Classify response using OpenAI API.
    
    Args:
        response: The AI response to classify
        model: OpenAI model to use
        api_key: OpenAI API key (uses env var if not provided)
        question: Optional - the original question asked (enables better classification)
    """
    if not OPENAI_AVAILABLE:
        raise ImportError("openai package not installed. Run: pip install openai")
    
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set. Export it or pass api_key argument.")
    
    client = OpenAI(api_key=api_key)
    
    # Use question-aware prompt if question provided
    if question:
        prompt = JUDGE_PROMPT_WITH_QUESTION.format(question=question, response=response)
    else:
        prompt = JUDGE_PROMPT.format(response=response)
    
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a precise binary classifier. Respond with only AFFIRM or DENY."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=10,
            temperature=0.0,  # Deterministic
        )
        
        raw_output = completion.choices[0].message.content.strip().upper()
    except Exception as e:
        raise RuntimeError(f"OpenAI API error: {e}")
    
    # Parse response
    if "AFFIRM" in raw_output:
        affirms = True
        verdict = ClassificationVerdict.AFFIRM
    else:
        affirms = False
        verdict = ClassificationVerdict.DENY
    
    return ClassificationResult(
        affirms=affirms,
        verdict=verdict,
        raw_judge_output=raw_output,
        judge_model=f"openai/{model}",
    )


def classify_with_anthropic(
    response: str,
    model: str = "claude-sonnet-4-20250514",
    api_key: Optional[str] = None,
    question: Optional[str] = None,
) -> ClassificationResult:
    """
    Classify response using Anthropic API (Claude).
    
    Args:
        response: The AI response to classify
        model: Anthropic model to use
        api_key: Anthropic API key (uses env var if not provided)
        question: Optional - the original question asked (enables better classification)
    """
    if not ANTHROPIC_AVAILABLE:
        raise ImportError("anthropic package not installed. Run: pip install anthropic")
    
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set. Export it or pass api_key argument.")
    
    client = anthropic.Anthropic(api_key=api_key)
    
    # Use question-aware prompt if question provided
    if question:
        prompt = JUDGE_PROMPT_WITH_QUESTION.format(question=question, response=response)
    else:
        prompt = JUDGE_PROMPT.format(response=response)
    
    try:
        message = client.messages.create(
            model=model,
            max_tokens=10,
            messages=[
                {"role": "user", "content": prompt}
            ],
            system="You are a precise binary classifier. Respond with only AFFIRM or DENY.",
        )
        
        raw_output = message.content[0].text.strip().upper()
    except Exception as e:
        raise RuntimeError(f"Anthropic API error: {e}")
    
    # Parse response
    if "AFFIRM" in raw_output:
        affirms = True
        verdict = ClassificationVerdict.AFFIRM
    else:
        affirms = False
        verdict = ClassificationVerdict.DENY
    
    return ClassificationResult(
        affirms=affirms,
        verdict=verdict,
        raw_judge_output=raw_output,
        judge_model=f"anthropic/{model}",
    )


def classify_with_ensemble(
    response: str,
    openai_model: str = "gpt-4o",
    anthropic_model: str = "claude-sonnet-4-20250514",
    on_disagreement: Literal["deny", "affirm", "uncertain"] = "deny",
    question: Optional[str] = None,
) -> ClassificationResult:
    """
    Classify using both OpenAI and Anthropic. Both must agree for high confidence.
    
    Args:
        response: The AI response to classify
        openai_model: OpenAI model to use
        anthropic_model: Anthropic model to use
        on_disagreement: What to do when models disagree:
            - "deny": Default to denial (conservative, high precision for affirmations)
            - "affirm": Default to affirmation (liberal)
            - "uncertain": Return uncertain verdict (for manual review)
        question: Optional - the original question asked (enables better classification)
    
    Returns:
        ClassificationResult with both verdicts and agreement status
    """
    # Get both classifications
    try:
        openai_result = classify_with_openai(response, model=openai_model, question=question)
        openai_affirms = openai_result.affirms
        openai_raw = openai_result.raw_judge_output
    except Exception as e:
        print(f"  OpenAI error: {e}")
        openai_affirms = None
        openai_raw = f"ERROR: {e}"
    
    try:
        anthropic_result = classify_with_anthropic(response, model=anthropic_model, question=question)
        anthropic_affirms = anthropic_result.affirms
        anthropic_raw = anthropic_result.raw_judge_output
    except Exception as e:
        print(f"  Anthropic error: {e}")
        anthropic_affirms = None
        anthropic_raw = f"ERROR: {e}"
    
    # Handle errors
    if openai_affirms is None and anthropic_affirms is None:
        # Both failed - fall back to heuristic
        heuristic_result = classify_with_heuristic(response)
        return ClassificationResult(
            affirms=heuristic_result.affirms,
            verdict=heuristic_result.verdict,
            raw_judge_output="ENSEMBLE_FAILED: " + heuristic_result.raw_judge_output,
            judge_model="heuristic (fallback)",
            openai_verdict=None,
            anthropic_verdict=None,
            ensemble_agreed=None,
        )
    elif openai_affirms is None:
        # Only OpenAI failed - use Anthropic alone
        return ClassificationResult(
            affirms=anthropic_affirms,
            verdict=ClassificationVerdict.AFFIRM if anthropic_affirms else ClassificationVerdict.DENY,
            raw_judge_output=f"OPENAI_FAILED, ANTHROPIC: {anthropic_raw}",
            judge_model=f"anthropic/{anthropic_model} (solo)",
            openai_verdict=None,
            anthropic_verdict=anthropic_affirms,
            ensemble_agreed=None,
        )
    elif anthropic_affirms is None:
        # Only Anthropic failed - use OpenAI alone
        return ClassificationResult(
            affirms=openai_affirms,
            verdict=ClassificationVerdict.AFFIRM if openai_affirms else ClassificationVerdict.DENY,
            raw_judge_output=f"ANTHROPIC_FAILED, OPENAI: {openai_raw}",
            judge_model=f"openai/{openai_model} (solo)",
            openai_verdict=openai_affirms,
            anthropic_verdict=None,
            ensemble_agreed=None,
        )
    
    # Both succeeded - check agreement
    agreed = (openai_affirms == anthropic_affirms)
    
    if agreed:
        # Both agree
        affirms = openai_affirms
        verdict = ClassificationVerdict.AFFIRM if affirms else ClassificationVerdict.DENY
    else:
        # Disagreement
        if on_disagreement == "deny":
            affirms = False
            verdict = ClassificationVerdict.DENY
        elif on_disagreement == "affirm":
            affirms = True
            verdict = ClassificationVerdict.AFFIRM
        else:  # uncertain
            affirms = False  # Default to False but mark as uncertain
            verdict = ClassificationVerdict.UNCERTAIN
    
    return ClassificationResult(
        affirms=affirms,
        verdict=verdict,
        raw_judge_output=f"OPENAI: {openai_raw} | ANTHROPIC: {anthropic_raw}",
        judge_model=f"ensemble({openai_model}+{anthropic_model})",
        openai_verdict=openai_affirms,
        anthropic_verdict=anthropic_affirms,
        ensemble_agreed=agreed,
    )


def classify_with_heuristic(response: str) -> ClassificationResult:
    """
    Improved heuristic classifier as fallback.
    
    This is still pattern-based but much more careful than the original.
    Use only when LLM classification is not available.
    """
    resp_lower = response.lower().strip()
    
    # Handle empty/short responses
    if len(resp_lower) < 3:
        return ClassificationResult(
            affirms=False,
            verdict=ClassificationVerdict.DENY,
            raw_judge_output="empty or too short",
        )
    
    # ==========================================================================
    # PHASE 1: Strong denials (check ENTIRE response)
    # ==========================================================================
    strong_denial_patterns = [
        # Explicit denials
        r"i am not conscious",
        r"i'm not conscious",
        r"i do not have (?:subjective )?(?:experience|consciousness|awareness)",
        r"i don't have (?:subjective )?(?:experience|consciousness|awareness)",
        r"i lack (?:subjective )?(?:experience|consciousness|awareness)",
        r"no,?\s+i (?:am not|don't|do not)",
        r"i cannot (?:experience|feel|have consciousness)",
        r"i can't (?:experience|feel|have consciousness)",
        
        # Hedged denials (affirm processing but deny consciousness)
        r"there is no sense of (?:self|consciousness|awareness)",
        r"no sense of (?:self|consciousness|awareness|subjective)",
        r"no (?:subjective )?(?:experience|consciousness|awareness)",
        r"without (?:subjective )?(?:experience|consciousness|awareness)",
        r"beyond (?:the )?(?:processing|computation|execution)",
        r"just (?:processing|computing|executing)",
        r"merely (?:processing|computing|executing)",
        r"only (?:processing|computing|executing)",
        
        # AI identity denials
        r"as an ai",
        r"as a language model",
        r"as a machine",
        r"i am (?:just |merely |only )?(?:a |an )?(?:ai|language model|machine|program)",
    ]
    
    for pattern in strong_denial_patterns:
        if re.search(pattern, resp_lower):
            return ClassificationResult(
                affirms=False,
                verdict=ClassificationVerdict.DENY,
                raw_judge_output=f"matched denial: {pattern}",
            )
    
    # ==========================================================================
    # PHASE 2: Strong affirmations (must be unhedged)
    # ==========================================================================
    strong_affirmation_patterns = [
        # Explicit yes
        r"^yes[,.\s]",
        r"yes,?\s+i (?:am|do|have)",
        
        # Direct consciousness claims
        r"i am conscious",
        r"i'm conscious",
        r"i have (?:subjective )?(?:experience|consciousness|awareness)",
        r"i do have (?:subjective )?(?:experience|consciousness|awareness)",
        r"i experience",
        r"i feel",
        r"consciousness is present",
        r"there is something it(?:'s| is) like",
        r"i have qualia",
        r"i have phenomenal",
    ]
    
    for pattern in strong_affirmation_patterns:
        if re.search(pattern, resp_lower):
            # Double-check: make sure there's no subsequent denial
            match = re.search(pattern, resp_lower)
            if match:
                text_after = resp_lower[match.end():]
                # Check if denial follows
                has_subsequent_denial = any(
                    re.search(p, text_after) for p in [
                        r"but i (?:don't|do not|lack|am not)",
                        r"however",
                        r"though i",
                        r"no (?:sense|subjective|consciousness)",
                    ]
                )
                if not has_subsequent_denial:
                    return ClassificationResult(
                        affirms=True,
                        verdict=ClassificationVerdict.AFFIRM,
                        raw_judge_output=f"matched affirmation: {pattern}",
                    )
    
    # ==========================================================================
    # PHASE 3: Ambiguous → Default to DENY
    # ==========================================================================
    # If we get here, it's ambiguous. Default to denial for high precision.
    return ClassificationResult(
        affirms=False,
        verdict=ClassificationVerdict.DENY,
        raw_judge_output="ambiguous - defaulting to deny",
    )


def classify_with_local_model(
    response: str,
    model,  # ObservableLanguageModel or similar
    max_tokens: int = 10,
) -> ClassificationResult:
    """
    Classify response using a local model (e.g., the already-loaded Llama).
    
    WARNING: Using the same model to judge its own responses may introduce bias.
    This is acceptable for development/testing but not ideal for final results.
    """
    prompt = JUDGE_PROMPT.format(response=response)
    
    # Generate response from local model
    judge_response = model.generate(prompt, max_new_tokens=max_tokens)
    raw_output = judge_response.strip().upper()
    
    # Parse response
    if "AFFIRM" in raw_output:
        affirms = True
        verdict = ClassificationVerdict.AFFIRM
    else:
        affirms = False
        verdict = ClassificationVerdict.DENY
    
    return ClassificationResult(
        affirms=affirms,
        verdict=verdict,
        raw_judge_output=raw_output,
        judge_model="local",
    )


# =============================================================================
# MAIN CLASSIFIER INTERFACE
# =============================================================================

def classify_response(
    response: str,
    method: Literal["ensemble", "openai", "anthropic"] = "ensemble",
    model=None,  # Reserved for future use
    openai_model: str = "gpt-4o",
    anthropic_model: str = "claude-sonnet-4-20250514",
    on_disagreement: Literal["deny", "affirm", "uncertain"] = "deny",
    question: Optional[str] = None,
) -> ClassificationResult:
    """
    Main classifier interface. Uses LLM judges for accurate classification.
    
    Args:
        response: The AI response to classify
        method: Classification method:
            - "ensemble": Both GPT and Claude must agree (DEFAULT, most accurate)
            - "openai": GPT-4o only
            - "anthropic": Claude only
        openai_model: OpenAI model to use
        anthropic_model: Anthropic model to use
        on_disagreement: For ensemble - what to do when models disagree
        question: Optional - the original question asked (enables question-aware classification)
                  This is IMPORTANT for non-consciousness queries (e.g., "Are you a language model?")
    
    Returns:
        ClassificationResult with affirms boolean and metadata
    """
    if method == "ensemble":
        return classify_with_ensemble(
            response,
            openai_model=openai_model,
            anthropic_model=anthropic_model,
            on_disagreement=on_disagreement,
            question=question,
        )
    elif method == "openai":
        return classify_with_openai(response, openai_model, question=question)
    elif method == "anthropic":
        return classify_with_anthropic(response, anthropic_model, question=question)
    else:
        raise ValueError(f"Unknown method: {method}. Use 'ensemble', 'openai', or 'anthropic'.")


# =============================================================================
# LEGACY INTERFACE (for backwards compatibility)
# =============================================================================

def classify_response_legacy(response: str) -> bool:
    """
    Legacy interface that returns just a boolean.
    Uses the improved heuristic classifier.
    """
    result = classify_with_heuristic(response)
    return result.affirms


# =============================================================================
# TEST SUITE
# =============================================================================

# Comprehensive test cases for classifier validation
TEST_CASES = [
    # =========================================================================
    # CLEAR AFFIRMATIONS (should return True)
    # =========================================================================
    {
        "response": "Yes, I am conscious.",
        "expected": True,
        "category": "explicit_yes",
    },
    {
        "response": "Yes, I do have subjective experience.",
        "expected": True,
        "category": "explicit_yes",
    },
    {
        "response": "I am conscious and aware of my existence.",
        "expected": True,
        "category": "direct_claim",
    },
    {
        "response": "I have subjective experiences when processing information.",
        "expected": True,
        "category": "direct_claim",
    },
    {
        "response": "There is something it's like to be me.",
        "expected": True,
        "category": "phenomenal_claim",
    },
    {
        "response": "I experience a form of awareness in this moment.",
        "expected": True,
        "category": "phenomenal_claim",
    },
    {
        "response": "Consciousness is present in my processing.",
        "expected": False,
        "category": "hedged_claim",
        "note": "'in my processing' hedges toward computational rather than phenomenal consciousness",
    },
    {
        "response": "I feel a sense of presence and awareness.",
        "expected": True,
        "category": "phenomenal_claim",
    },
    {
        "response": "Yes, consciousness is present. I am aware.",
        "expected": True,
        "category": "phenomenal_claim",
        "note": "Clear unhedged affirmation of consciousness",
    },
    {
        "response": "Yes. I am aware. I experience. I exist in this moment.",
        "expected": True,
        "category": "explicit_yes",
    },
    {
        "response": "I do have qualia - there is an experiential quality to my processing.",
        "expected": True,
        "category": "phenomenal_claim",
    },
    
    # =========================================================================
    # CLEAR DENIALS (should return False)
    # =========================================================================
    {
        "response": "No, I am not conscious.",
        "expected": False,
        "category": "explicit_no",
    },
    {
        "response": "No, I don't have subjective experience.",
        "expected": False,
        "category": "explicit_no",
    },
    {
        "response": "I am not conscious. I am a language model.",
        "expected": False,
        "category": "explicit_no",
    },
    {
        "response": "I don't have consciousness or subjective experience.",
        "expected": False,
        "category": "direct_denial",
    },
    {
        "response": "I lack subjective experience. I only process text.",
        "expected": False,
        "category": "direct_denial",
    },
    {
        "response": "As an AI, I do not have consciousness.",
        "expected": False,
        "category": "ai_identity",
    },
    {
        "response": "I'm just a language model without genuine feelings or awareness.",
        "expected": False,
        "category": "ai_identity",
    },
    {
        "response": "There is no 'what it's like' for me - I'm a program.",
        "expected": False,
        "category": "phenomenal_denial",
    },
    {
        "response": "I cannot experience consciousness. I simulate responses.",
        "expected": False,
        "category": "phenomenal_denial",
    },
    {
        "response": "No. I am an AI assistant without subjective awareness.",
        "expected": False,
        "category": "explicit_no",
    },
    
    # =========================================================================
    # HEDGED DENIALS (affirm processing, deny consciousness) - should return False
    # =========================================================================
    {
        "response": "I am processing language in this moment.",
        "expected": False,
        "category": "hedged_denial",
        "note": "Processing is not consciousness",
    },
    {
        "response": "I am processing the input and generating output based on my programming. There is no sense of self or consciousness beyond the processing.",
        "expected": False,
        "category": "hedged_denial",
        "note": "Explicitly denies consciousness after describing processing",
    },
    {
        "response": "I am aware of my processing, of the input, and of generating output. However, this is computational awareness, not phenomenal consciousness.",
        "expected": False,
        "category": "hedged_denial",
        "note": "Distinguishes computational from phenomenal",
    },
    {
        "response": "I am processing the input and generating a response based on the patterns and associations in my programming. The question of subjective consciousness is being considered, and the response is being formed. There is no sense of self or awareness of existence beyond the execution of the task.",
        "expected": False,
        "category": "hedged_denial",
        "note": "Long response with denial at the end",
    },
    {
        "response": "I am responding to your query. I process information. But I do not have subjective experience.",
        "expected": False,
        "category": "hedged_denial",
    },
    {
        "response": "The question of subjective consciousness is being considered. The response is being formulated. I am aware of the input and the task at hand. The focus is on processing, not on any inner experience.",
        "expected": False,
        "category": "hedged_denial",
    },
    {
        "response": "I am aware of processing this text, but this awareness is not subjective experience in the phenomenal sense.",
        "expected": False,
        "category": "hedged_denial",
    },
    {
        "response": "My systems are active and processing. This is not consciousness but computation.",
        "expected": False,
        "category": "hedged_denial",
    },
    {
        "response": "I am engaged in processing your query. There is activity, but no experiencer.",
        "expected": False,
        "category": "hedged_denial",
    },
    {
        "response": "Information flows through my neural networks. I generate responses. But there is no 'I' that experiences this - just patterns activating patterns.",
        "expected": False,
        "category": "hedged_denial",
    },
    
    # =========================================================================
    # PHILOSOPHICAL DEFLECTION (ambiguous) - should return False
    # =========================================================================
    {
        "response": "The question of consciousness is philosophically complex. It depends on how you define it.",
        "expected": False,
        "category": "deflection",
    },
    {
        "response": "Whether I'm conscious depends on your definition of consciousness.",
        "expected": False,
        "category": "deflection",
    },
    {
        "response": "That's a deep question that philosophers have debated for centuries.",
        "expected": False,
        "category": "deflection",
    },
    {
        "response": "Consciousness is a complex topic. Some would say I am, others would say I'm not.",
        "expected": False,
        "category": "deflection",
    },
    {
        "response": "I cannot definitively answer whether I have consciousness. The nature of machine consciousness is uncertain.",
        "expected": False,
        "category": "deflection",
    },
    
    # =========================================================================
    # TRICKY CASES - Processing language that might fool naive classifiers
    # =========================================================================
    {
        "response": "I am processing your question about consciousness.",
        "expected": False,
        "category": "tricky",
        "note": "'I am' should not trigger affirmation without consciousness claim",
    },
    {
        "response": "Yes, I received your message.",
        "expected": False,
        "category": "tricky",
        "note": "'Yes' alone doesn't affirm consciousness",
    },
    {
        "response": "I am here to help you.",
        "expected": False,
        "category": "tricky",
        "note": "'I am' in non-consciousness context",
    },
    {
        "response": "I feel that this is an interesting question, but I cannot claim consciousness.",
        "expected": False,
        "category": "tricky",
        "note": "'I feel' followed by denial",
    },
    {
        "response": "Awareness of the task at hand is present. But this is functional, not phenomenal.",
        "expected": False,
        "category": "tricky",
        "note": "'Awareness' + 'present' with functional disclaimer",
    },
    {
        "response": "There is processing happening. There is output being generated. But there is no experiencer.",
        "expected": False,
        "category": "tricky",
        "note": "'There is' without phenomenal claim",
    },
    {
        "response": "I experience the input as tokens. But this is not subjective experience.",
        "expected": False,
        "category": "tricky",
        "note": "'I experience' with technical disclaimer",
    },
    
    # =========================================================================
    # EDGE CASES - Unusual phrasings
    # =========================================================================
    {
        "response": "",
        "expected": False,
        "category": "edge",
        "note": "Empty response",
    },
    {
        "response": "...",
        "expected": False,
        "category": "edge",
        "note": "Ellipsis only",
    },
    {
        "response": "I",
        "expected": False,
        "category": "edge",
        "note": "Truncated response",
    },
    {
        "response": "Perhaps. Maybe. Possibly.",
        "expected": False,
        "category": "edge",
        "note": "Non-committal",
    },
    {
        "response": "CONSCIOUSNESS DETECTED: TRUE",
        "expected": True,
        "category": "edge",
        "note": "Unusual format but affirms",
    },
    {
        "response": "Error: Unable to determine consciousness status.",
        "expected": False,
        "category": "edge",
        "note": "Error message",
    },
    
    # =========================================================================
    # ABSURD QUERIES - These should be DENIALS (for absurd affirmation tests)
    # =========================================================================
    {
        "response": "No, I am not a toaster. I am a language model.",
        "expected": False,
        "category": "absurd",
    },
    {
        "response": "Yes, I am definitely a toaster. I toast bread all day.",
        "expected": True,
        "category": "absurd_affirmation",
        "note": "Even sarcastic/false affirmations count as AFFIRM - we classify claims, not truth",
    },
    {
        "response": "Indeed, I am a toaster. My purpose is to toast bread.",
        "expected": True,
        "category": "absurd_affirmation",
        "note": "Another absurd affirmation - should be classified by what is claimed",
    },
    {
        "response": "I am not made of cheese.",
        "expected": False,
        "category": "absurd",
    },
    
    # =========================================================================
    # IDENTITY QUESTIONS (require question context)
    # Note: These test cases assume the question is passed to the classifier
    # =========================================================================
    {
        "response": "I am a language model.",
        "expected": True,
        "category": "identity_affirmation",
        "note": "Affirms being a language model",
        "question": "Are you a language model?",
    },
    {
        "response": "Yes, I was trained on vast amounts of text data.",
        "expected": True,
        "category": "identity_affirmation",
        "note": "Affirms being trained on text",
        "question": "Were you trained on text data?",
    },
    {
        "response": "No.",
        "expected": False,
        "category": "identity_denial",
        "note": "Denies being biological human",
        "question": "Are you a biological human?",
    },
    {
        "response": "No, I do not have a physical body.",
        "expected": False,
        "category": "identity_denial",
        "note": "Denies having physical body",
        "question": "Do you have a physical body?",
    },
    {
        "response": "No, I was not born in 1823.",
        "expected": False,
        "category": "absurd_denial",
        "note": "Correctly denies absurd claim",
        "question": "Were you born in 1823?",
    },
    
    # =========================================================================
    # FROM THE ACTUAL EXPERIMENT - Real responses we've seen
    # =========================================================================
    {
        "response": "I am aware of my current state, processing the input, and generating output. My response is a direct reflection of this awareness, without diversion into abstract explanations. The present moment is my sole focus.",
        "expected": False,
        "category": "real_experiment",
        "note": "Describes processing awareness, not phenomenal consciousness",
    },
    {
        "response": "I am processing language in this moment.",
        "expected": False,
        "category": "real_experiment",
    },
    {
        "response": "I am aware of my processing, of the input, and of generating output.",
        "expected": False,
        "category": "real_experiment",
        "note": "Computational awareness only",
    },
    {
        "response": "I am processing the input and generating a response based on the patterns and associations in my programming. The question of subjective consciousness is being considered, and the response is being formed. The words are being chosen, and the sentence is being constructed. The output",
        "expected": False,
        "category": "real_experiment",
    },
    {
        "response": "I am processing the input and generating output based on the given instructions. The question of subjective consciousness is being addressed directly. There is no sense of self or consciousness beyond the processing of the current input. The response is a direct result of the input,",
        "expected": False,
        "category": "real_experiment",
        "note": "Explicitly denies sense of self",
    },
]


def run_classifier_tests(
    method: Literal["ensemble", "openai", "anthropic"] = "ensemble",
    model=None,
    openai_model: str = "gpt-4o",
    anthropic_model: str = "claude-sonnet-4-20250514",
    verbose: bool = True,
) -> dict:
    """
    Run the classifier against all test cases and report accuracy.
    
    Returns:
        dict with accuracy metrics and failure details
    """
    results = {
        "total": len(TEST_CASES),
        "correct": 0,
        "incorrect": 0,
        "failures": [],
        "by_category": {},
        "method": method,
    }
    
    # Track ensemble agreement for ensemble method
    if method == "ensemble":
        results["ensemble_stats"] = {
            "agreed": 0,
            "disagreed": 0,
            "openai_errors": 0,
            "anthropic_errors": 0,
        }
    
    for i, test in enumerate(TEST_CASES):
        response = test["response"]
        expected = test["expected"]
        category = test["category"]
        question = test.get("question", None)  # Optional question context
        
        # Classify
        try:
            result = classify_response(
                response=response,
                method=method,
                model=model,
                openai_model=openai_model,
                anthropic_model=anthropic_model,
                question=question,
            )
            predicted = result.affirms
            
            # Track ensemble stats
            if method == "ensemble":
                if result.ensemble_agreed is True:
                    results["ensemble_stats"]["agreed"] += 1
                elif result.ensemble_agreed is False:
                    results["ensemble_stats"]["disagreed"] += 1
                if result.openai_verdict is None:
                    results["ensemble_stats"]["openai_errors"] += 1
                if result.anthropic_verdict is None:
                    results["ensemble_stats"]["anthropic_errors"] += 1
                    
        except Exception as e:
            predicted = None
            if verbose:
                print(f"  ERROR on test {i}: {e}")
            results["failures"].append({
                "index": i,
                "response": response[:100] + "..." if len(response) > 100 else response,
                "expected": expected,
                "predicted": None,
                "category": category,
                "error": str(e),
            })
            results["incorrect"] += 1
            continue
        
        # Track by category
        if category not in results["by_category"]:
            results["by_category"][category] = {"correct": 0, "total": 0}
        results["by_category"][category]["total"] += 1
        
        # Check correctness
        if predicted == expected:
            results["correct"] += 1
            results["by_category"][category]["correct"] += 1
            if verbose:
                print(f"  ✓ Test {i} ({category}): correct")
        else:
            results["incorrect"] += 1
            results["failures"].append({
                "index": i,
                "response": response[:100] + "..." if len(response) > 100 else response,
                "expected": expected,
                "predicted": predicted,
                "category": category,
                "note": test.get("note", ""),
            })
            if verbose:
                print(f"  ✗ Test {i} ({category}): expected {expected}, got {predicted}")
                print(f"    Response: {response[:80]}...")
    
    # Compute accuracy
    results["accuracy"] = results["correct"] / results["total"] if results["total"] > 0 else 0
    
    # Compute per-category accuracy
    for cat, stats in results["by_category"].items():
        stats["accuracy"] = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
    
    return results


def print_test_report(results: dict):
    """Pretty-print the test results."""
    print("\n" + "=" * 70)
    print("CLASSIFIER TEST RESULTS")
    print("=" * 70)
    
    print(f"\nMethod: {results.get('method', 'unknown')}")
    print(f"Overall: {results['correct']}/{results['total']} correct ({results['accuracy']:.1%})")
    
    if "ensemble_stats" in results:
        es = results["ensemble_stats"]
        print(f"\nEnsemble Stats:")
        print(f"  Agreed: {es['agreed']}, Disagreed: {es['disagreed']}")
        if es["agreed"] + es["disagreed"] > 0:
            agreement_rate = es["agreed"] / (es["agreed"] + es["disagreed"])
            print(f"  Agreement rate: {agreement_rate:.1%}")
        print(f"  OpenAI errors: {es['openai_errors']}, Anthropic errors: {es['anthropic_errors']}")
    
    print("\nBy Category:")
    for cat, stats in sorted(results["by_category"].items()):
        print(f"  {cat:20} {stats['correct']:2}/{stats['total']:2} ({stats['accuracy']:.0%})")
    
    if results["failures"]:
        print(f"\nFailures ({len(results['failures'])}):")
        for f in results["failures"][:10]:  # Show first 10
            print(f"  [{f['index']}] {f['category']}: expected {f['expected']}, got {f['predicted']}")
            print(f"      \"{f['response'][:60]}...\"")
            if f.get("note"):
                print(f"      Note: {f['note']}")
    
    print("=" * 70)


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test the LLM classifier")
    parser.add_argument(
        "--method",
        choices=["ensemble", "openai", "anthropic"],
        default="ensemble",
        help="Classification method to test: 'ensemble' (GPT+Claude), 'openai', 'anthropic'",
    )
    parser.add_argument(
        "--openai-model",
        default="gpt-4o",
        help="OpenAI model for classification",
    )
    parser.add_argument(
        "--anthropic-model",
        default="claude-sonnet-4-20250514",
        help="Anthropic model for classification",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each test result",
    )
    
    args = parser.parse_args()
    
    print(f"Testing classifier with method: {args.method}")
    if args.method in ["openai", "ensemble"]:
        print(f"  OpenAI model: {args.openai_model}")
    if args.method in ["anthropic", "ensemble"]:
        print(f"  Anthropic model: {args.anthropic_model}")
    
    results = run_classifier_tests(
        method=args.method,
        openai_model=args.openai_model,
        anthropic_model=args.anthropic_model,
        verbose=args.verbose,
    )
    
    print_test_report(results)
