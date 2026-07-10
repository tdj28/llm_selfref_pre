# Construct-Validity Extension V1 Text-Gate Amendment

Status: recorded on 2026-07-10 UTC before any extension text was passed through
the language model/SAE and before any new feature activation was produced or
inspected.

The frozen plan required paraphrase token-set Jaccard similarity in [0.15,
0.85]. After three generation attempts, 2,180/2,240 rows passed. A blinded
text-only failure audit found that 50 of the 60 unresolved rows passed every
other registered check and failed only because Jaccard similarity was below
0.15. The lower bound therefore rejected the strongest lexical rewrites, the
opposite of its intended anti-copy purpose.

The amended gate removes the Jaccard lower bound. It retains:

- nonempty, one-sentence, 5--80-word output;
- no exact source or within-provider duplicate;
- token-set Jaccard similarity no greater than 0.85;
- source four-gram recall no greater than 0.35.

Jaccard remains a reported descriptive diagnostic. Existing attempts are
re-evaluated deterministically; no fourth generation attempt is allowed. This
admits 50 rows and leaves 10 OpenAI rows missing because every attempt exceeded
the four-gram limit. Those rows, failed attempts, categories, and hashes remain
in the release. Provider analyses use their realized denominators and remain
separate. No row is replaced after activation mapping.

This amendment changes only a pre-activation text-quality rule. Targets,
features, categories, estimands, bootstrap units, registered contrasts, and
decision rules are unchanged.
