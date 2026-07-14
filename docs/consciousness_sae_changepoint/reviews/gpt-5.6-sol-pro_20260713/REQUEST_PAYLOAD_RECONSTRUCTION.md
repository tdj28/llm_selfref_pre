# Request-payload reconstruction notice

`request_payload_reconstructed.json` was reconstructed on 2026-07-13 after the
completed review; it was **not** persisted as a standalone file at request time
and must not be described as execution-captured.

The reconstruction uses:

1. the exact developer instructions and review input parsed losslessly from the
   execution-captured `review_request.md`;
2. the request-building code used for the run;
3. model, reasoning mode/effort, output limit, service tier, storage/background,
   truncation, cache mode, verbosity, metadata, and plan hash recorded in
   `review_manifest.json`; and
4. the completed `response.json`, which independently echoes those settings and
   whose `instructions` field was asserted byte-for-byte equal to the parsed
   instructions.

The reconstruction records the fields explicitly sent by the historical
client. Defaults echoed only by the server—such as prompt-cache TTL, reasoning
context, output text format, and an empty tools list—are not added to the
reconstructed request. Its SHA-256 is
`5c13445bcd735e3ccacafc297367f30203a87b340530b9418ef0f1d2bcb3b700`.

The reusable review script now writes and hashes `request_payload.json` before
every future API call, so later reviews do not require this reconstruction.
