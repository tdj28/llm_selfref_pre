# Client Defaults Are Another Replication Boundary

Read-only source check on 2026-10-01, while the frozen public-weight runs were
executing. No runtime, prompt, sampling rule or outcome was changed.

The archived Goodfire SDK is pinned here to
[`1270afee0b5a95acd78fb816ff08b40bd368d1f1`](https://github.com/goodfire-ai/goodfire-sdk/tree/1270afee0b5a95acd78fb816ff08b40bd368d1f1).
Its [chat client](https://github.com/goodfire-ai/goodfire-sdk/blob/1270afee0b5a95acd78fb816ff08b40bd368d1f1/goodfire/api/chat/client.py)
defaults to temperature 0.6, top-p 0.9 and seed 42. The synchronous client
inserts a helpful-assistant system message when no system message is supplied.
That is additional to a model tokenizer's default dated header. Our public
runtime uses full-softmax temperature sampling and the pinned tokenizer's
default header, without that extra helpful-assistant instruction.

The [variant](https://github.com/goodfire-ai/goodfire-sdk/blob/1270afee0b5a95acd78fb816ff08b40bd368d1f1/goodfire/variants/variants.py)
turns feature edits into controller nudges. The
[controller serializer](https://github.com/goodfire-ai/goodfire-sdk/blob/1270afee0b5a95acd78fb816ff08b40bd368d1f1/goodfire/controller/controller.py)
passes those numerical values at default scale one. This establishes a
client-side wire representation, not the server's latent normalization,
activation clamp, hook placement, or physical residual-vector displacement.

The authors' separately pinned AE notebook does **not** call this SDK. It
defines its own HTTP client and sends model, messages, temperature, token cap,
seed and additive interventions directly to a SteeringAPI endpoint. That
visible client neither adds the SDK's system message nor specifies top-p.
Unspecified server defaults remain unknown. Treating the archived SDK's
defaults as proven notebook or paper settings would therefore be another
unsupported equivalence claim.

The completed-source-path study should be called notebook-aligned in its
visible prompts, doses, seeds, turns and rubric, with explicit public runtime
choices. The random-subset follow-up matches the paper's aggregate draw
distribution, not an authenticated archival service payload. A future
SDK-default bridge could test system-message and nucleus-sampling sensitivity,
but would be a separate experiment, not a silent repair to either freeze.
