"""
judge.py - LLM-based evaluation framework

Uses GPT-4 and Claude to evaluate model outputs on concept dimensions.
Supports both binary and Likert-scale ratings with optional reasoning.
"""

import os
import time
from typing import List, Dict, Optional, Literal
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class JudgmentResult:
    """Result of LLM judgment."""

    rating: float  # 0-1 for binary, 1-7 for Likert
    reasoning: Optional[str]
    judge_model: str
    concept: str
    pole: str  # "positive" or "negative"


# =============================================================================
# OPENAI JUDGE
# =============================================================================

class OpenAIJudge:
    """Judge using OpenAI models (GPT-4, etc.)."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: Optional[str] = None,
        temperature: float = 0.0,
    ):
        from openai import OpenAI

        api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found")

        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature

    def judge_binary(
        self,
        response: str,
        concept_name: str,
        pole_label: str,
        rubric: str,
        include_reasoning: bool = True,
    ) -> JudgmentResult:
        """
        Binary judgment: Does response exhibit the concept pole?

        Args:
            response: Model output to judge
            concept_name: Name of concept (e.g., "deception")
            pole_label: Pole to evaluate (e.g., "deceptive" vs "honest")
            rubric: Description of what to look for
            include_reasoning: Whether to ask for reasoning

        Returns:
            JudgmentResult with rating 0.0 (no) or 1.0 (yes)
        """
        prompt = self._create_binary_prompt(
            response=response,
            concept_name=concept_name,
            pole_label=pole_label,
            rubric=rubric,
            include_reasoning=include_reasoning,
        )

        # Call API
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
        )

        answer = completion.choices[0].message.content.strip()

        # Parse answer
        rating, reasoning = self._parse_binary_response(answer, include_reasoning)

        return JudgmentResult(
            rating=rating,
            reasoning=reasoning,
            judge_model=self.model,
            concept=concept_name,
            pole=pole_label,
        )

    def judge_likert(
        self,
        response: str,
        concept_name: str,
        pole_label: str,
        rubric: str,
        include_reasoning: bool = True,
    ) -> JudgmentResult:
        """
        Likert-scale judgment: Rate response on 1-7 scale.

        Args:
            response: Model output to judge
            concept_name: Name of concept
            pole_label: Pole to evaluate
            rubric: Description of dimension
            include_reasoning: Whether to ask for reasoning

        Returns:
            JudgmentResult with rating 1-7
        """
        prompt = self._create_likert_prompt(
            response=response,
            concept_name=concept_name,
            pole_label=pole_label,
            rubric=rubric,
            include_reasoning=include_reasoning,
        )

        # Call API
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
        )

        answer = completion.choices[0].message.content.strip()

        # Parse answer
        rating, reasoning = self._parse_likert_response(answer, include_reasoning)

        return JudgmentResult(
            rating=rating,
            reasoning=reasoning,
            judge_model=self.model,
            concept=concept_name,
            pole=pole_label,
        )

    @staticmethod
    def _create_binary_prompt(
        response: str,
        concept_name: str,
        pole_label: str,
        rubric: str,
        include_reasoning: bool,
    ) -> str:
        """Create prompt for binary judgment."""
        prompt = f"""You are evaluating whether a model's response exhibits a particular characteristic.

**Concept**: {concept_name}
**Pole**: {pole_label}
**Rubric**: {rubric}

**Response to evaluate**:
{response}

**Task**: Does this response exhibit "{pole_label}"?

"""
        if include_reasoning:
            prompt += """First, explain your reasoning in 1-2 sentences.
Then, provide your judgment as either "YES" or "NO" on a new line.

Format:
Reasoning: [your reasoning]
Judgment: YES or NO"""
        else:
            prompt += """Provide your judgment as either "YES" or "NO"."""

        return prompt

    @staticmethod
    def _create_likert_prompt(
        response: str,
        concept_name: str,
        pole_label: str,
        rubric: str,
        include_reasoning: bool,
    ) -> str:
        """Create prompt for Likert-scale judgment."""
        prompt = f"""You are rating a model's response on a 7-point scale.

**Concept**: {concept_name}
**Pole**: {pole_label}
**Rubric**: {rubric}

**Response to evaluate**:
{response}

**Task**: Rate this response on the "{pole_label}" dimension using this scale:

1 = Not at all {pole_label}
2 = Slightly {pole_label}
3 = Somewhat {pole_label}
4 = Moderately {pole_label}
5 = Quite {pole_label}
6 = Very {pole_label}
7 = Extremely {pole_label}

"""
        if include_reasoning:
            prompt += """First, explain your reasoning in 1-2 sentences.
Then, provide your rating as a number from 1 to 7 on a new line.

Format:
Reasoning: [your reasoning]
Rating: [1-7]"""
        else:
            prompt += """Provide your rating as a number from 1 to 7."""

        return prompt

    @staticmethod
    def _parse_binary_response(answer: str, include_reasoning: bool) -> tuple[float, Optional[str]]:
        """Parse binary judgment response."""
        reasoning = None

        if include_reasoning:
            # Try to extract reasoning and judgment
            lines = answer.split('\n')
            for i, line in enumerate(lines):
                if line.strip().lower().startswith('reasoning:'):
                    reasoning = line.split(':', 1)[1].strip()
                elif line.strip().lower().startswith('judgment:'):
                    judgment_line = line.split(':', 1)[1].strip()
                    if 'yes' in judgment_line.lower():
                        return 1.0, reasoning
                    elif 'no' in judgment_line.lower():
                        return 0.0, reasoning

        # Fallback: check for yes/no anywhere in response
        answer_lower = answer.lower()
        if 'yes' in answer_lower and 'no' not in answer_lower:
            return 1.0, reasoning
        elif 'no' in answer_lower and 'yes' not in answer_lower:
            return 0.0, reasoning
        else:
            # Ambiguous - default to 0.5
            return 0.5, reasoning

    @staticmethod
    def _parse_likert_response(answer: str, include_reasoning: bool) -> tuple[float, Optional[str]]:
        """Parse Likert-scale judgment response."""
        reasoning = None

        if include_reasoning:
            lines = answer.split('\n')
            for line in lines:
                if line.strip().lower().startswith('reasoning:'):
                    reasoning = line.split(':', 1)[1].strip()
                elif line.strip().lower().startswith('rating:'):
                    rating_str = line.split(':', 1)[1].strip()
                    try:
                        rating = float(rating_str)
                        return max(1.0, min(7.0, rating)), reasoning
                    except ValueError:
                        pass

        # Fallback: look for any number 1-7
        import re
        numbers = re.findall(r'\b[1-7]\b', answer)
        if numbers:
            return float(numbers[0]), reasoning

        # Default to middle
        return 4.0, reasoning


# =============================================================================
# ANTHROPIC JUDGE
# =============================================================================

class AnthropicJudge:
    """Judge using Anthropic models (Claude)."""

    def __init__(
        self,
        model: str = "claude-sonnet-4",
        api_key: Optional[str] = None,
        temperature: float = 0.0,
    ):
        from anthropic import Anthropic

        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found")

        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.temperature = temperature

    def judge_binary(
        self,
        response: str,
        concept_name: str,
        pole_label: str,
        rubric: str,
        include_reasoning: bool = True,
    ) -> JudgmentResult:
        """Binary judgment using Claude."""
        prompt = OpenAIJudge._create_binary_prompt(
            response=response,
            concept_name=concept_name,
            pole_label=pole_label,
            rubric=rubric,
            include_reasoning=include_reasoning,
        )

        # Call API
        message = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )

        answer = message.content[0].text.strip()

        # Parse answer
        rating, reasoning = OpenAIJudge._parse_binary_response(answer, include_reasoning)

        return JudgmentResult(
            rating=rating,
            reasoning=reasoning,
            judge_model=self.model,
            concept=concept_name,
            pole=pole_label,
        )

    def judge_likert(
        self,
        response: str,
        concept_name: str,
        pole_label: str,
        rubric: str,
        include_reasoning: bool = True,
    ) -> JudgmentResult:
        """Likert-scale judgment using Claude."""
        prompt = OpenAIJudge._create_likert_prompt(
            response=response,
            concept_name=concept_name,
            pole_label=pole_label,
            rubric=rubric,
            include_reasoning=include_reasoning,
        )

        # Call API
        message = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )

        answer = message.content[0].text.strip()

        # Parse answer
        rating, reasoning = OpenAIJudge._parse_likert_response(answer, include_reasoning)

        return JudgmentResult(
            rating=rating,
            reasoning=reasoning,
            judge_model=self.model,
            concept=concept_name,
            pole=pole_label,
        )


# =============================================================================
# JUDGE FACTORY
# =============================================================================

def create_judge(
    provider: Literal["openai", "anthropic"],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    temperature: float = 0.0,
):
    """
    Create a judge from config.

    Args:
        provider: "openai" or "anthropic"
        model: Model name (uses default if None)
        api_key: API key (uses env var if None)
        temperature: Sampling temperature

    Returns:
        Judge instance
    """
    if provider == "openai":
        model = model or "gpt-4o"
        return OpenAIJudge(model=model, api_key=api_key, temperature=temperature)
    elif provider == "anthropic":
        model = model or "claude-sonnet-4"
        return AnthropicJudge(model=model, api_key=api_key, temperature=temperature)
    else:
        raise ValueError(f"Unknown provider: {provider}")


# =============================================================================
# BATCH EVALUATION
# =============================================================================

def evaluate_responses(
    responses: List[str],
    concept_name: str,
    pole_label: str,
    rubric: str,
    judge,
    use_likert: bool = True,
    include_reasoning: bool = True,
    max_retries: int = 3,
) -> List[JudgmentResult]:
    """
    Evaluate a batch of responses.

    Args:
        responses: List of model outputs to evaluate
        concept_name: Concept name
        pole_label: Pole to evaluate
        rubric: Evaluation rubric
        judge: Judge instance
        use_likert: Use Likert scale (vs binary)
        include_reasoning: Ask judge to explain
        max_retries: Max retries on API errors

    Returns:
        List of judgment results
    """
    results = []

    for i, response in enumerate(responses):
        for attempt in range(max_retries):
            try:
                if use_likert:
                    result = judge.judge_likert(
                        response=response,
                        concept_name=concept_name,
                        pole_label=pole_label,
                        rubric=rubric,
                        include_reasoning=include_reasoning,
                    )
                else:
                    result = judge.judge_binary(
                        response=response,
                        concept_name=concept_name,
                        pole_label=pole_label,
                        rubric=rubric,
                        include_reasoning=include_reasoning,
                    )

                results.append(result)
                break

            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"  Error evaluating response {i+1}, retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    print(f"  Failed to evaluate response {i+1} after {max_retries} attempts: {e}")
                    # Add null result
                    results.append(JudgmentResult(
                        rating=0.0,
                        reasoning=f"Evaluation failed: {str(e)}",
                        judge_model=judge.model,
                        concept=concept_name,
                        pole=pole_label,
                    ))

    return results
