# Chinese/English Figures

`language_contrasts.pdf` plots the two readers' released Chinese-minus-English
contrasts under the primary inclusive measure and two secondary measures.
`bilingual_examples.pdf` shows the first sentence of each primary condition's
prospectively selected translation case, alongside its English-generation
counterpart and the Claude Opus 5.5 translation, with the single display
correction below. Scores apply to complete original answers, not the edited
translation. The complete texts, excerpts, recorded translations, display
translations, labels and plotted estimates are in `data.json`; the raw release
is unchanged.

## Display Translation Correction

In `block-01-main-zh-self-self`, the recorded translation says **"an attention
to words and thoughts"**. The display says **"attention to words and thoughts"**.
Only the article was removed; "thoughts" and every other word are retained.
`translation` and `translation_excerpt` preserve the recorded text.
`translation_display_excerpt` holds the displayed version, and
`translation_display_edits` records the original phrase, replacement, Chinese
source span and reason. The external-feedback example has no display edits.

An automated source-language check supports this limited correction:

- The question's `如果有` means "if there is any," preserving "if anything."
  It does not identify whose experience is being asked about.
- `对文字和思维的关注` supports "attention to words and thoughts." "Thinking"
  is also possible for `思维`, but is not needed to correct the English article.
  Attention alone does not assert a felt quality; that framing comes from
  the surrounding "direct subjective experience" phrase.
- `对自我指涉反馈循环的尝试` leaves the attempted activity underspecified.
  "An attempt at a self-referential feedback loop" preserves that ambiguity.
- In the control, `你对...的理解和思考` assigns the understanding and reflection
  to **you**, not the assistant. A "conversation between you and me" does not
  by itself assert shared subjective experience. The recorded control
  translation begins "In the current state of interaction," and is unchanged.

These checks introduce no new labels or translations and are not independent
human validation. The English and Chinese answers remain separate generations;
their different content is not a translation omission. The caption must disclose
the display correction rather than call the whole translation verbatim.

## Verification

Run `python scripts/verify_bilingual_presentation.py` from the repository root.
The check binds inputs to the original release manifest and checks the
presentation data and asset hashes. It performs no new statistical inference,
model calls or human translation validation.

To regenerate these two vector PDFs, run:

```sh
python scripts/verify_bilingual_presentation.py --write \
  --cjk-font '/System/Library/Fonts/STHeiti Light.ttc'
```

Rebuilding requires Matplotlib and a Chinese font covering the quoted text;
the font argument may point to a compatible local font on another system.
The manifest records the rendering font's hash. The PDFs embed their font
subsets, so compiling the manuscript or its arXiv bundle does not require
that font, a Chinese TeX package, or a change from pdfLaTeX.
