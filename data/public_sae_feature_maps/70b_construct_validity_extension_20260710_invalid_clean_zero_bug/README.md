# Invalid Startup Artifact

This directory preserves an aborted startup for provenance. It is not an
experimental result and was never analyzed.

The mapper previously interpreted `--clean-items-per-category 0` as one legacy
clean template per category because a zero-length slice returned the full
single-item list. The dry-run total therefore appeared correct while the live
corpus silently included 14 unregistered items. The process was stopped after
the first item, before any aggregate outcome was inspected.

The bug was fixed by returning an empty clean corpus explicitly when the count
is zero, covered by a regression test, committed as `3f1bc3f`, and verified by
a second dry run with exactly 2,606 registered items. The corrected run lives
in `../70b_construct_validity_extension_20260710/`.

The four remote files in this directory were retrieved before termination and
matched locally:

```text
ccbd1dc080c17a0cbf1dfdcf0fb711b06a83e1fd864cd15837f78f34ce37bc59  feature_plan.csv
3cc4a235dc825dd84e1a9a526ff307f5631b6c72747fe70dc89b00c1820a342b  manifest.json
02eb891a8cb1d73002a04df05b370de1d6e924795fae4e2fffc847d5abafb503  mapping_corpus.csv
4ec15ce04a446cd4bafaa4c94494de83dd75bc79df2020dc5669298055397164  runpod_mapping.log
```
