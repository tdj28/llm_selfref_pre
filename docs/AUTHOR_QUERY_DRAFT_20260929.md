# Author Query Draft

Status: not sent. The owner previously discussed author outreach; this file
does not establish whether an earlier message was sent or answered. Confirm
that history before contacting anyone. Human approval is required to send.

Subject: Public-weight replication questions for arXiv:2510.24797v2

We are preparing a response to your paper and would value clarification of a
few implementation details. Our public-weight runs differ before steering:
the no-op outputs score substantially above the approximately 0.30 baseline
plotted in Figure 2, while the public notebook's saved zero rows score 4/60.
We are treating this as a comparability problem, not a refutation.

1. Does the public steering notebook match the paper's Experiment 2, or is it
   a separate demonstration? Which induction, temperature, classifier prompt
   and model/SAE service versions generated Figure 2?
2. At coefficient zero, did the service leave the residual untouched, use an
   SAE reconstruction, or preserve a reconstruction-error term? Were feature
   additions applied to both turns and all token positions?
3. Is there an existing frozen feature/runtime manifest or description we can
   cite? We use the six notebook IDs as the working targets and are not asking
   you to guarantee their identity in a current third-party service.
4. For Experiments 3 and 4, could you clarify the response counts behind the
   reported pair counts and degrees of freedom? Some reported pair counts
   appear to imply more samples than the stated design. An aggregate count
   table would suffice; no raw private responses are requested.

We can share the corrected draft and artifact links for factual review before
publication and include your clarification or a response with permission.

## Sending Checklist

- Confirm prior contact and choose the responsible human sender.
- Link the corrected draft, not the superseded non-replication headline.
- Specify a reasonable response window and do not imply nonresponse is evidence
  against the paper or its authors.
- Do not publish private correspondence without permission.
