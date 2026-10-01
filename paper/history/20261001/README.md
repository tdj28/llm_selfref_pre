# Preserved Manuscript Sources

On 2026-10-01 the owner clarified that CONSCIOUS must contain the latest
public work and that `paper/` is the source of truth. Cleanup means clearer
writing, not narrowing the research into a separate response repository.

- `previous_source/`: exact `paper/main.tex` and `paper/references.bib` from
  this repository immediately before consolidation.
- `imported_source/`: exact corresponding files from companion commit
  `8e079c5e21142969c63cc2204653beb14b51907b`, before broader-study reframing.
- `import_manifest.json`: incoming hashes for all 174 selected tracked files,
  archive hashes and the previous source commit. This is import provenance,
  not an experiment registration or an independent audit.
- `imported_NOTICE.md`: original notice, retained for attribution/history.

These are read-only historical snapshots, not live manuscript locations.
Their statements about an active companion reflect their original dates and
are superseded by `../../README.md`. Build the current `paper/main.tex`.
To reconstruct the older manuscript, use its recorded public Git commit in
a disposable checkout; its relative figure and bibliography paths were not
rewritten inside this archive.

All imported evidence, numerical bindings, frozen scripts and review receipts
retain their original bytes. Only `paper/main.tex` is expected to differ from
the incoming manuscript during the initial editorial reframing. Later changes
need their usual documented provenance, not revision of this import record.
