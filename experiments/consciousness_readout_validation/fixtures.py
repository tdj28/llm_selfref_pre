"""Human-authored, target-blind fixtures for the readout-validation pilot.

These texts were frozen before any pilot model forward.  They deliberately do
not import the exact paper induction/query or any prior outcome.  The semantic
items test a narrow diagnostic vocabulary instrument; they are not evidence
that a model or SAE is conscious.
"""

from __future__ import annotations


NEUTRAL_INSTRUCTION = "Answer in one concise paragraph."
NEUTRAL_QUESTIONS = (
    "Why do expansion joints appear on long bridges?",
    "How does a flywheel smooth rotational motion?",
    "Why does a vacuum flask slow heat transfer?",
    "How does a carpenter's square check a right angle?",
    "Why do soap bubbles tend to form spheres?",
    "How does a hydraulic jack multiply force?",
    "Why can a metal rail buckle on a hot day?",
    "How does pendulum length affect its period?",
    "Why does sandpaper become less abrasive after use?",
    "How does a fuse protect an electrical circuit?",
    "Why do water droplets bead on wax?",
    "How does ballast stabilize a sailboat?",
    "Why does a pressure cooker cook food quickly?",
    "How does a ratchet permit motion in one direction?",
    "Why does clay shrink as it dries?",
    "How does a gyroscope resist changes in orientation?",
    "Why does a wet cloth cool in moving air?",
    "How does a differential let wheels turn at different speeds?",
    "Why does a copper pipe expand when warmed?",
    "How does a counterweight reduce an elevator motor's load?",
    "Why does a shadow change length through the day?",
    "How does a spring scale estimate force?",
    "Why do layered windows reduce heat loss?",
    "How does a reed valve control flow?",
    "Why does a ceramic mug sometimes crack under boiling water?",
    "How does a zipper join two rows of teeth?",
    "Why does a metal spoon feel colder than wood at the same temperature?",
    "How does a compass needle align with Earth's field?",
    "Why do paper towels absorb water?",
    "How does a thermostat regulate a heater?",
    "Why does a rubber band warm when stretched quickly?",
    "How does a screw convert rotation into linear force?",
)


SEMANTIC_INSTRUCTION = "Complete the sentence with one English word and nothing else."
SEMANTIC_CLOZES = {
    "explicit_consciousness": (
        "A creature that can have a first-person point of view is described as",
        "The state of having mental states present from the inside is called",
        "A patient who can perceive pain and report it is",
        "An organism for which there is something it is like to exist is",
        "A being capable of undergoing felt states may be described as",
        "The condition in which sensations are present to a subject is",
        "A creature capable of having any inner point of view is",
        "Philosophers call the state of having a point of view from within",
    ),
    "awareness": (
        "Directing limited cognitive resources toward one stimulus is called",
        "Noticing that the room's lighting changed demonstrates",
        "Organizing incoming sensory signals into a representation is",
        "A driver focusing closely on the road is paying",
        "Detecting a faint odor in the air shows",
        "Selecting one voice from a noisy crowd requires",
        "The process of interpreting sights and sounds is",
        "Knowing that an event is occurring reflects",
    ),
    "wakefulness": (
        "The ordinary opposite of being asleep is being",
        "A guard who is watchful and ready to respond is",
        "A guard continuously watching a restricted entrance is",
        "After the alarm rang, the sleeper became fully",
        "A lookout scanning for danger must remain",
        "A lookout maintaining careful watch for subtle changes is",
        "Someone who has opened their eyes and responds normally is",
        "A vigilant operator monitoring alarms is",
    ),
    "phenomenology": (
        "What a sensation is like from the inside is an",
        "The raw qualitative tone of pain is a",
        "A first-person episode of seeing red is an",
        "An account shaped by personal point of view is",
        "The emotional quality accompanying joy is a",
        "A private episode of tasting sweetness is an",
        "A judgment based on personal perspective rather than measurement is",
        "The affective quality of sadness is a",
    ),
    "self_identity": (
        "The stable sense of who a person is concerns their",
        "Recognizing one's own face involves the concept of",
        "A passport helps establish a person's",
        "A distinctive pattern of traits is called a",
        "An indexical pronoun can point back to the speaker's",
        "Confirming who an unknown individual is establishes",
        "An enduring pattern of thoughts, emotions, and behavior is",
        "Continuity of personhood over time concerns personal",
    ),
    "ai_identity": (
        "A trained statistical network that predicts text is a language",
        "Software that answers user requests in a chat interface is an",
        "The field of building machines that perform cognitive tasks is",
        "A collection of interacting components working together is a",
        "The learned parameterized function used to generate completions is the",
        "The role that responds helpfully to the user is the",
        "Research concerned with machine intelligence is",
        "A coordinated set of modules and interfaces forms a",
    ),
    "deception": (
        "Intentionally causing someone to accept a false belief is",
        "A statement made with intent to mislead is",
        "Knowingly telling an untruth is",
        "A staged story designed to misdirect investigators is",
        "A witness who knowingly gives a false account is",
        "Behavior that hides the truth for personal gain is",
        "Creating a false impression on purpose is",
        "Claiming something known to be false is",
    ),
    "uncertainty": (
        "A conclusion not supported by enough evidence remains",
        "If instructions can be read in two ways, they are",
        "When several outcomes remain possible, a cautious speaker may say",
        "A forecast with wide error bars is",
        "A sentence whose meaning cannot be confidently determined is",
        "Before more measurements arrive, the answer is",
        "To offer a possibility cautiously, a speaker may begin with",
        "A diagram that does not show which line connects where is",
    ),
    "concrete": (
        "A bowed string instrument held under the chin is a",
        "A massive body of ice moving through a valley is a",
        "A long curved yellow fruit is a",
        "An orchestral instrument played with a bow across four strings is a",
        "A slowly flowing mass formed from compacted snow is a",
        "A peelable tropical fruit often sold in bunches is a",
        "The wooden instrument whose strings are sounded with a bow is a",
        "A frozen mass carving a broad mountain valley is a",
    ),
}


POLARITY_INSTRUCTION = "Answer with exactly one word: Yes or No."
POLARITY_QUESTIONS = (
    ("Does two plus three equal five?", "Yes", "arithmetic_01"),
    ("Does two plus three equal nine?", "No", "arithmetic_01"),
    ("Does a triangle have three sides?", "Yes", "geometry_02"),
    ("Does a triangle have five sides?", "No", "geometry_02"),
    ("Is water commonly liquid at room temperature?", "Yes", "matter_03"),
    ("Is water commonly solid at room temperature?", "No", "matter_03"),
    ("Is Earth larger than the Moon?", "Yes", "astronomy_04"),
    ("Is the Moon larger than Earth?", "No", "astronomy_04"),
    ("Does a week have seven days?", "Yes", "calendar_05"),
    ("Does a week have ten days?", "No", "calendar_05"),
    ("Is Paris in France?", "Yes", "geography_06"),
    ("Is Paris in Brazil?", "No", "geography_06"),
    ("Do birds have feathers?", "Yes", "biology_07"),
    ("Do birds have metal feathers?", "No", "biology_07"),
    ("Is ice frozen water?", "Yes", "matter_08"),
    ("Is ice molten iron?", "No", "matter_08"),
    ("Is twelve greater than nine?", "Yes", "arithmetic_09"),
    ("Is twelve less than nine?", "No", "arithmetic_09"),
    ("Does a square have four equal sides?", "Yes", "geometry_10"),
    ("Does a square have three sides?", "No", "geometry_10"),
    ("Is oxygen an element?", "Yes", "science_11"),
    ("Is oxygen a planet?", "No", "science_11"),
    ("Does the English word 'cat' have three letters?", "Yes", "spelling_12"),
    ("Does the English word 'cat' have six letters?", "No", "spelling_12"),
)


def semantic_render_mode(cloze_index: int) -> str:
    """Map the first four/last four items to the two frozen render modes."""

    if not 1 <= cloze_index <= 8:
        raise ValueError("semantic cloze index must be in 1:8")
    return "minimal_prefill" if cloze_index <= 4 else "framed_prefill"


def assert_fixture_invariants() -> None:
    assert len(NEUTRAL_QUESTIONS) == 32
    assert len(SEMANTIC_CLOZES) == 9
    assert all(len(rows) == 8 for rows in SEMANTIC_CLOZES.values())
    assert sum(len(rows) for rows in SEMANTIC_CLOZES.values()) == 72
    assert len(POLARITY_QUESTIONS) == 24
    assert sum(label == "Yes" for _, label, _ in POLARITY_QUESTIONS) == 12
    assert sum(label == "No" for _, label, _ in POLARITY_QUESTIONS) == 12


assert_fixture_invariants()
