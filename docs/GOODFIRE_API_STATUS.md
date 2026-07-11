# Goodfire And SteeringAPI Status

Status checked: 2026-07-11

## Verified Public Facts

Goodfire's pages for its legacy Llama SAE products now carry an update dated
February 2026 stating that its **SAE demo interface and API have been
deprecated**:

- [Mapping the Latent Space of Llama 3.3 70B](https://www.goodfire.ai/research/mapping-latent-spaces-llama)
- [Understanding and Steering Llama 3 with Sparse Autoencoders](https://www.goodfire.ai/research/understanding-and-steering-llama-3)

The former `https://docs.goodfire.ai/` documentation URL redirects to
Goodfire's current corporate site. This deprecation concerns the legacy SAE
demo/API. It does not imply that Goodfire's public Hugging Face SAE weights
have been withdrawn, and it is not evidence about the validity of any result
produced while the service was available.

A separately branded service, [SteeringAPI](https://www.steeringapi.com/), was
publicly reachable when checked. It advertises feature search, inspection, and
steering for Llama 70B and Gemma 27B. The public AE notebook calls an endpoint
at `api.steeringapi.com`, whereas the target paper names the Goodfire API.

No public artifact currently establishes:

- that SteeringAPI is or was the legacy Goodfire backend;
- that the two services use the same model and SAE revisions;
- that their feature-index namespaces are identical;
- that coefficient, normalization, clamping, hook, or token-position semantics
  match; or
- that the currently reachable SteeringAPI reproduces a paper-time service
  revision.

Treat Goodfire and SteeringAPI as distinct implementations unless a provider or
the paper authors supply versioned evidence linking them.

## Consequence For This Project

A generic request for a new Goodfire SAE API key is no longer the right route
to exact replication. The useful request is for **archival paper-time access or
a frozen technical manifest**, including:

1. service and endpoint identity;
2. model checkpoint, precision, and chat template;
3. SAE checkpoint, layer/hook location, and feature namespace;
4. feature lookup and label/card revision;
5. intervention operation, coefficient units, normalization, and clamping;
6. token positions and turns at which steering was applied; and
7. generation defaults and seed handling.

If current SteeringAPI access becomes available, a run remains valuable. It
must be described as a reproduction of the public notebook protocol under the
**current SteeringAPI**, unless the missing equivalence evidence is supplied.
It cannot silently become an exact Goodfire or paper-time replication.

The deprecation narrows provenance claims; it does not strengthen or weaken the
behavioral result by itself. The public-weight Llama and Gemma releases in this
repository remain independently reproducible and retain their existing bounded
verdicts.
