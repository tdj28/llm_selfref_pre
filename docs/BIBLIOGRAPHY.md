# Consolidated Bibliography

[`../references.bib`](../references.bib) is the standalone project-wide
BibTeX collection, assembled on 2026-10-01. It includes the literature in:

- `paper/references.bib`;
- `steering/paper/references.bib` (historical);
- the focused `berg2025-response/paper/references.bib` at commit
  `26ef2210af903e66e3bb941aab1f35529f65d7cd`;
- reference sections of the research blog drafts in `technical_blog_posts/`;
- cited public notebooks, model/SAE/Jacobian-lens releases, and our own
  manuscript, evidence releases and OSF records.

This is a reference collection, not a claim that every entry is cited by the
current response paper or that every linked work has been independently
replicated. It does not inventory every operational URL in logs, dependency
documentation, or historical automated-review transcripts. In particular,
merely suggested citations from an ungrounded review are not silently adopted.

## Keys And Provenance

Duplicate works have one canonical entry. Where old manuscripts used different
keys for the same work, comments at the top of `references.bib` map those keys
to the retained key. The focused response's key takes precedence, then the
research paper's, then the historical steering paper's. Existing bibliographies
and manuscript citation keys were not edited. Use this standalone collection
instead of combining it with the older files, which would duplicate keys.

Artifact citations retain commit or revision pins where the research record
provides them. An access date is not a publication date; undated repositories
therefore omit the year rather than invent one. Mutable release projects are
not labeled immutable registrations. Our current response is labeled a draft,
not a peer-reviewed publication.

Metadata corrections in this new collection:

- The old steering bibliography incorrectly names the three Berg-paper
  authors. The consolidated entry uses Cameron Berg, Diogo de Lucena and
  Judd Rosenblatt, as on the [version-2 abstract page](https://arxiv.org/abs/2510.24797v2).
- The refusal-steering entry now includes Blake Bullwinkel, corrects Forough
  Poursabzi-Sangdeh's surname, and identifies the [2025 revision of the 2024
  preprint](https://arxiv.org/abs/2411.11296v2).
- Duplicate abbreviated SAE citations use the fuller records already present
  in the current manuscript or research bibliography. ACL entries have direct
  anthology links; new blog-literature entries were checked against primary
  metadata pages, not inferred from review prose.
- The Qwen research note's old URL did not resolve during this check. Its
  current title and canonical URL are supplied by the [Praxagent research-note
  index](https://praxagent.ai/blog/); the individual page returned a temporary
  error. Its entry discloses the older title used in existing draft references.

The historical files retain their original bytes. These corrections do not
change any frozen experimental artifact or scientific result.

## Cultural-Emotion Addition (2026-10-01)

The current response's measurement discussion now cites Spencer-Rodgers,
Peng and Wang (2010), Havaldar et al. (2023), and Dudy et al. (2024). Their
three entries are also included in this consolidated file. Verification
used the [Sage abstract and issue record](https://journals.sagepub.com/doi/10.1177/0022022109349508),
[ACL paper and metadata](https://aclanthology.org/2023.wassa-1.19/), and
[author-hosted ACII paper](https://s3.sunai.uoc.edu/web/agata/papers/Analyzing_Cultural_Representations_of_Emotions_in_LLMs_Through_Mixed_Emotion_Survey.pdf).
The Sage full text is restricted; only its abstract-supported sample comparison
is used. The ACII venue, DOI and pages were checked against the proceedings
PDF and [author record](https://www.shirandudy.com/projects/8_project/).

These references supply cultural/linguistic measurement context, not evidence
of a mechanism underlying the present self-reports or of absent experience.
Dudy's language-versus-origin contrast is English/Japanese; Chinese belongs
to its separate broader comparison. The active response records the source
checks in `reviews/reference_checks.md`. No historical manuscript or frozen
experiment was changed.

## Use

For classic BibTeX, add `\bibliography{references}` to a document that resolves
this file, using the citation keys in the file. With biblatex, use
`\addbibresource{references.bib}`. Titles protect model names and acronyms
against automatic lowercasing. Author-name accents use TeX escapes.
