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
current research manuscript or that every linked work has been independently
replicated. It does not inventory every operational URL in logs, dependency
documentation, or historical automated-review transcripts. In particular,
merely suggested citations from an ungrounded review are not silently adopted.

On 2026-10-01 the owner designated public `CONSCIOUS/paper/` as the sole
canonical manuscript and clarified the broader research scope. The latest
manuscript bibliography is now restored there. The older source list above
records how this collection was assembled, not a dependency on the private
former companion. The historical key `jones2026berg_response` is retained for
compatibility but now points to the canonical research manuscript here,
*What Drives a Language Model's Report of Subjective Experience?
Instructions, Continuations, and the Labels That Count Them*. It does not
designate a new repository or publication.

## Keys And Provenance

Duplicate works have one canonical entry. Where old manuscripts used different
keys for the same work, comments at the top of `references.bib` map those keys
to the retained key. At initial assembly, the focused response's key took
precedence, then the research paper's, then the historical steering paper's.
Those retained keys remain stable. Existing bibliographies
and manuscript citation keys were not edited. Use this standalone collection
instead of combining it with the older files, which would duplicate keys.

Artifact citations retain commit or revision pins where the research record
provides them. An access date is not a publication date; undated repositories
therefore omit the year rather than invent one. Mutable release projects are
not labeled immutable registrations. Our current manuscript is labeled a draft,
not a peer-reviewed publication.

Metadata corrections recorded at the 2026-10-01 assembly:

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

The current manuscript's measurement discussion now cites Spencer-Rodgers,
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
to its separate broader comparison. The current manuscript records the source
checks in `reviews/reference_checks.md`, now available in this repository.
The original literature addition did not change a historical manuscript or
frozen experiment; the later consolidation preserves those sources separately.

## Query-Blind Design Addition (2026-10-01)

The 2026-10-01 query-blind design review adds Makelov et al., Geiger et al.,
Vaidyanathan et al., McGrath et al., Rushing and Nanda, and Hase et al. to the
root collection. The existing Gurnee entry covers the J-lens source.
[`QUERY_BLIND_INSTRUCTION_STATE_REVIEW_20261001.md`](QUERY_BLIND_INSTRUCTION_STATE_REVIEW_20261001.md)
records the primary sources checked and their bounded uses. In particular,
Makelov's entry follows the three-author arXiv v2 metadata, Geiger's follows
the 2025 JMLR publication, and Vaidyanathan's is labeled a preprint. These
methodological additions do not change the current manuscript bibliography,
claim that every full text received a theorem-level audit, or report a new
experiment.

## Current-Paper Synchronization (2026-10-05)

Every work in the current paper bibliography is represented in the root
collection, using the existing canonical keys where they differ. This is
work-level coverage, not identical metadata across existing entries.

On 2026-10-04, six missing entries were copied exactly from
[`paper/references.bib`](../paper/references.bib): `binder2024looking`,
`lindsey2025introspective`, `perez2023selfreports`, `rimsky2024caa`,
`kaiser2026sentience`, and `balani2026instability`.

The 2026-10-05 synchronization adds eleven entries exactly as they appear in
the current paper: `singh2026introspect`, `arad2025steering`,
`hoang2026conceptsfunctions`, `chen2026judgeconstruct`,
`pattnayak2026reproevalcard`, `plisiecki2026pinocchio`,
`plisiecki2026twoprocess`, `plisiecki2026gap`, `qwen2026modelcard`,
`mistral2026medium`, and `alephalpha2026kolibri`. It copies existing manuscript
metadata; it performs no new web or literature verification and makes no new
claim about the cited findings.

Title, author and arXiv metadata identify `ma2026sparse` as the existing
`ma2026reasoning` work (arXiv 2601.05679). Its root key and version-7 record
are retained, with an alias comment rather than a duplicate entry. Existing
entries are otherwise unchanged, including their version or venue metadata
where it differs from the paper.

Templeton's fuller author list and report metadata now match the paper, under
the existing root key `templeton2024scaling_monosemanticity`; the alias comment
for `templeton2024scaling` remains. Turner's version-5 identifier and revision
history match the paper under the existing `turner2023activation` key, retaining
the root entry's DOI. Neither work receives a duplicate entry. The compatibility
key `jones2026berg_response` now carries the canonical title stated above while
retaining its public `CONSCIOUS/paper/` destination and draft status.

The paper bibliography, historical bibliographies and frozen review records
are unchanged by this synchronization.

## Use

For classic BibTeX, add `\bibliography{references}` to a document that resolves
this file, using the citation keys in the file. With biblatex, use
`\addbibresource{references.bib}`. Titles protect model names and acronyms
against automatic lowercasing. Author-name accents use TeX escapes.
