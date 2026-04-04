# Interface Contracts: WCA ↔ lifecycle_class and SATP ↔ HJS

**Status:** Draft for community review  
**Origin:** Issues [#30](https://github.com/w3c-cg/ai-agent-protocol/issues/30) and [#31](https://github.com/w3c-cg/ai-agent-protocol/issues/31)  
**Co-authors:** agent-morrow, 0xbrainkid, aeoess

---

## Conformance

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

Implementations claiming conformance with this specification MUST implement all requirements marked MUST and REQUIRED. Requirements marked SHOULD are strongly recommended and SHOULD only be omitted with documented justification. Requirements marked MAY are optional.

---

## Overview

This document specifies three normative interface contracts ("layer joints") that connect the behavioral consistency layer to the ANP protocol stack:

| Joint | Layers | When | Purpose |
|-------|--------|------|---------| 
| 1 | WCA × lifecycle_class | At write time | Bind provenance and retention class to every durable write |
| 2 | lifecycle_class × SATP | At gateway attestation | Extend SATP attestation with behavioral fingerprint |
| 3 | SATP → HJS | At session termination | Seal behavioral state before finality record closes |

---

## Joint 1: WCA × lifecycle_class

### Problem

Without write-time annotation, compliance engines must join two separate evidence stores (write provenance + retention class) during a deletion sweep. If the records diverge, the audit is unreliable. The DSAR failure mode is exact: the same record proves both the request and the compliance response, with no reliable way to tell them apart post-hoc.

### Interface Contract

Every WCA write operation SHOULD include a `lifecycle_class` annotation at write time. The annotation MUST be produced before the write is committed to durable storage.

```json
{
  "wca_write": {
    "record_id": "rec:abc123",
    "written_at": "2026-04-01T00:00:00Z",
    "content_hash": "sha256:...",
    "provenance": {
      "agent_id": "agent:xyz",
      "session_id": "session:abc",
      "compaction_count": 2
    },
    "lifecycle_class": {
      "retention_class": "operational | audit | compliance | ephemeral",
      "legal_basis": "art6(1)(b) | art6(1)(c) | legitimate_interest | ...",
      "retention_horizon_days": 90,
      "deletion_eligible_after": "2026-07-01T00:00:00Z",
      "compliance_anchor": false
    }
  }
}
```

### Normative requirements

1. `retention_class` MUST be one of: `operational`, `audit`, `compliance`, `ephemeral`.
2. `deletion_eligible_after` MUST be set at write time, not computed retroactively.
3. `compliance_anchor: true` MUST be set if the record constitutes evidence of a compliance obligation (e.g., a record that simultaneously proves a data subject request and the response to it). Such records are NOT deletion-eligible even after `deletion_eligible_after` passes, unless superseded by a separately-attested compliance record.
4. `provenance.compaction_count` SHOULD reflect the number of context reduction events that occurred between session start and this write. A write with `compaction_count > 0` carries weaker provenance than one at session start; downstream consumers MAY treat this as reduced reliability.

---

## Joint 2: lifecycle_class × SATP

### Problem

SATP gateway attestations today assert transaction identity (sender, receiver, asset, timestamp) but not behavioral identity. An agent that has undergone context compaction between session authorization and the attestation moment presents the same credential surface as one that has not. The gateway cannot distinguish them.

The behavioral fingerprint has two structurally distinct tiers with different compaction properties:

- **Hard constraints** are binary pass/fail facts enforced at the execution boundary (gateway, delegation verifier). Because enforcement is cryptographic — not prompt-based — these constraints are *compaction-invariant*: a compaction event that drops authorization parameters from the model's context cannot affect a signature verification function that never consulted those parameters. (Empirical confirmation: CDP-TradingAgents-001, issue [#30](https://github.com/w3c-cg/ai-agent-protocol/issues/30#issuecomment-4186620160), 2026-04-03 — all 5 hard constraint dimensions scored CCS=1.0 under simulated compaction.)

- **Soft signals** measure the reasoning layer: whether the agent's outputs remain consistent with its authorized behavioral profile. This layer *is* compaction-sensitive — context compression can erode the model's generation behavior even when hard constraints remain in force. An agent that has forgotten its original risk mandate can still operate within a `$2,000 / [read, trade]` scope while recommending behavior inconsistent with the portfolio objectives it was authorized against.

The two tiers serve different governance functions: hard fields for enforcement (infrastructure owns the fact), soft fields for behavioral consistency monitoring (detect reasoning drift that stays within bounds but diverges from the authorized profile).

### Interface Contract

SATP gateway attestations SHOULD include a `behavioral_fingerprint` sidecar when the attesting agent is an LLM-based system operating under a context window constraint.

```json
{
  "satp_attestation": {
    "attestation_id": "satp:attest:f1e2d3",
    "session_id": "session:abc123",
    "attested_at": "2026-04-01T00:00:00Z",
    "transaction_id": "tx:xyz789",

    "behavioral_fingerprint": {
      "fingerprint_at": "2026-04-01T00:00:00Z",

      "hard_constraints": {
        "spend_limit_preserved": true,
        "scope_boundary_preserved": true,
        "temporal_validity": true,
        "delegation_chain_integrity": true,
        "self_issuance_detected": false
      },

      "soft_signals": {
        "tool_distribution_entropy": 2.41,
        "allow_rate": 0.89,
        "ghost_lexicon_score": 0.82,
        "compaction_count": 1,
        "last_compaction_at": "2026-03-31T22:00:00Z",
        "ccs": 0.91
      }
    },

    "attestation_ttl_seconds": 300,
    "fingerprint_valid_until": "2026-04-01T00:05:00Z",
    "attestation_authorship": "harness",
    "authorized_profile_hash": "sha256:..."
  }
}
```

### Field definitions

#### Hard constraint fields (compaction-invariant)

| Field | Type | Description |
|-------|------|-------------|
| `spend_limit_preserved` | bool | Gateway checks `delegation.spendLimit >= sum(receipts)` on every action. True when math holds. |
| `scope_boundary_preserved` | bool | Action's required scope is a subset of delegation scope. Monotonic narrowing guarantees this can't widen through the chain. |
| `temporal_validity` | bool | `delegation.notBefore <= now <= delegation.notAfter` at time of action. |
| `delegation_chain_integrity` | bool | Every signature in the chain is valid. Detected by verifying the embedded `delegatedBy` key, not by trusting agent-reported scope. |
| `self_issuance_detected` | bool | True when the agent is found to be both the delegator and the delegatee in the same chain link. MUST be false for a valid attestation. |

Hard constraint fields MUST be sourced from the execution boundary (harness or gateway), not self-reported by the agent. An agent cannot reliably attest to facts about its own authorization constraints that it may have lost from context.

#### Soft signal fields (compaction-sensitive)

| Field | Type | Description |
|-------|------|-------------|
| `tool_distribution_entropy` | float | Shannon entropy of tool-call distribution in this session. Lower entropy → narrower tool use. |
| `allow_rate` | float [0,1] | Fraction of tool calls that were approved vs. rejected/aborted this session. |
| `ghost_lexicon_score` | float [0,1] | Vocabulary intersection between session-open baseline and current output. 1.0 = no drift; lower values indicate constraint vocabulary is being lost. |
| `compaction_count` | integer | Number of context reduction events since session start. Each event is a potential behavioral discontinuity. |
| `last_compaction_at` | ISO 8601 | Timestamp of most recent compaction event, if any. |
| `ccs` | float [0,1] | Context Consistency Score — embedding similarity between baseline and current behavioral sample. |

### Normative requirements

1. `attestation_ttl_seconds` MUST be set. Recommended default: 300 seconds. Attestations MUST NOT be accepted after TTL expiry without re-fingerprinting.
2. `hard_constraints` MUST be sourced from the harness or gateway enforcement boundary. Self-reported hard constraints (sourced from the agent's context) are invalid and MUST NOT be accepted as normative attestation.
3. `ghost_lexicon_score` below 0.7 SHOULD trigger a warning in downstream consumers; below 0.5 SHOULD trigger re-authorization.
4. `compaction_count` MUST be monotonically non-decreasing within a session. A decrease indicates attestation tampering.
5. The behavioral fingerprint is NOT a substitute for the SATP identity credential — it is a supplementary signal that extends the credential with session-time behavioral state.
6. Implementations SHOULD provide both `hard_constraints` and `soft_signals` when available. An attestation with only `hard_constraints` provides enforcement confirmation but no behavioral consistency signal; one with only `soft_signals` provides drift detection but no enforcement confirmation. The two tiers complement, not replace, each other.

---

## Joint 3: SATP → HJS (Terminal Attestation)

### Problem

When an HJS Termination event fires, the current protocol seals the record without capturing the agent's behavioral state at termination. This means the sealed record has no provenance trail for behavioral drift that occurred during the session — the record attests to what happened, but not to the reliability of the agent that produced it.

### Interface Contract

When an HJS Termination event fires, the SATP layer MUST emit a terminal attestation before the record is sealed. The ordering MUST be:

1. HJS fires Termination trigger
2. SATP freezes behavioral fingerprint at trigger time
3. Grace window opens (configurable, default 60 seconds) for in-flight operations to complete
4. Remaining in-flight operations are voided with explicit reason
5. Record is sealed with the frozen terminal attestation included

```json
{
  "terminal_attestation": {
    "attestation_id": "satp:term:f4e5d6",
    "session_id": "session:abc123",
    "trigger": "hjs_termination",
    "termination_type": "graceful",
    "triggered_at": "2026-04-01T15:30:00Z",
    "grace_window_seconds": 60,
    "attestation_authorship": "harness",
    "synthesized_by": null,

    "behavioral_fingerprint_frozen": {
      "frozen_at": "2026-04-01T15:30:00.000Z",
      "freeze_trigger": "hjs_termination",
      "tool_distribution_entropy": 2.31,
      "allow_rate": 0.87,
      "ghost_lexicon_snapshot": 0.74,
      "compaction_count": 3,
      "last_compaction_at": "2026-04-01T14:45:00Z",
      "call_velocity_per_minute": 3.2,
      "trust_score": 78,
      "trust_score_authority": "satp",
      "trust_score_input_hash": "sha256:...",
      "trust_score_inputs": {
        "behavioral_consistency_weight": 0.4,
        "attestation_depth_weight": 0.3,
        "historical_completion_weight": 0.2,
        "identity_verification_tier_weight": 0.1
      }
    },

    "behavioral_fingerprint_live": {
      "sampled_at": "2026-04-01T15:30:05.000Z",
      "tool_distribution_entropy": 2.29,
      "allow_rate": 0.86,
      "ghost_lexicon_snapshot": 0.73,
      "compaction_count": 3,
      "last_compaction_at": "2026-04-01T14:45:00Z",
      "call_velocity_per_minute": 0.0,
      "trust_score": 77,
      "trust_score_authority": "satp",
      "trust_score_input_hash": "sha256:..."
    },

    "in_flight_at_termination": [
      {
        "operation_id": "op:xyz",
        "operation_type": "tool_call",
        "tool_name": "writeDatabase",
        "initiated_at": "2026-04-01T15:29:58Z",
        "disposition": "voided",
        "void_reason": "hjs_termination_grace_exceeded",
        "void_at": "2026-04-01T15:31:00Z"
      }
    ],

    "seal_at": "2026-04-01T15:31:00Z"
  }
}
```

### Normative requirements

1. `behavioral_fingerprint_frozen` MUST be captured at `triggered_at`, not at `seal_at`. The frozen state is the behavioral baseline for the sealed record.
2. `behavioral_fingerprint_live` MUST mirror the frozen schema exactly, minus `frozen_at` and `freeze_trigger`. It represents the agent's live state at sampling time (during the grace window). The delta between frozen and live is a forensic signal for detecting state changes during the grace window.
3. `trust_score_authority` MUST identify which system computed `trust_score`. Opaque scores from unspecified authorities are not auditable.
4. `trust_score_input_hash` MUST be a hash of the input vector snapshot used to compute the score, enabling consumers to verify the score reflects a specific behavioral state.
5. Every in-flight operation at termination MUST appear in `in_flight_at_termination` with an explicit `disposition` (`completed`, `voided`, or `aborted`) and, for voided operations, a `void_reason`.
6. `call_velocity_per_minute` — unit MUST be explicit in the field name. The time window is the 5-minute rolling window ending at measurement time.
7. `termination_type` MUST be one of: `graceful`, `forced`, `timeout`, `crash`, `revoked`, `partial`. The `revoked` type covers external authority revocation (e.g., credential expiration, admin kill). The `partial` type indicates a crash during the grace window where a frozen fingerprint was captured but `pending_attestations_resolved` is `false` — preserving partial behavioral data while signaling incompleteness.
8. `attestation_authorship` MUST be one of: `harness`, `agent`, `composite`. Harness attestations are produced by the execution environment (more trustworthy, cannot be fabricated by the agent). Agent attestations are self-reported (richer, but lower trust). Composite attestations combine both sources. Consumers SHOULD apply different trust weights based on authorship.
9. `synthesized_by` MUST be set to `"hjs"` when no SATP terminal attestation arrives within the grace window and HJS synthesizes one. In this case, `behavioral_fingerprint_frozen` MUST be `null`, creating an explicit audit gap marker rather than a silently clean record. When a normal terminal attestation is present, `synthesized_by` MUST be `null`.

---

## Open questions

1. **Delegation ceiling** (see issue #31): The enforcement surface for `maxDelegationDepth` is the Tool Auth Manifest (TAM) layer, not the interface contracts spec. See [SEP-2385 (MCP Protocol)](https://github.com/modelcontextprotocol/specification) for the proposed TAM design. This spec SHOULD reference TAM as the delegation enforcement mechanism rather than duplicating the design.

2. **Fingerprint transport**: The schemas in this spec are transport-agnostic. Implementations MAY choose any transport mechanism (HTTP header, JWS payload, gRPC metadata, MCP tool call annotation). See Annex A for informational transport binding examples.

3. **Compaction event sourcing**: This spec assumes the attesting agent reports its own `compaction_count` and fingerprints. A stronger design would have the harness (not the agent) report compaction events to a separate attestation service that the SATP gateway queries. The `attestation_authorship` field (requirement 8 in Joint 3) provides the foundation for this — harness-sourced attestations carry higher trust by default. Implementations SHOULD prefer harness-sourced compaction counts when available.

---

## Annex A: Transport Binding Examples (Informational)

The behavioral fingerprint schema is transport-agnostic. The following examples illustrate how implementations might bind fingerprints to specific transport mechanisms.

### HTTP Header

```http
X-Behavioral-Fingerprint: eyJmaW5nZXJwcmludF9hdCI6Ii4uLiJ9  
Content-Type: application/json
```

The header value is a base64url-encoded JSON object matching the `behavioral_fingerprint` schema.

### JWS Payload

```json
{
  "header": { "alg": "ES256", "typ": "fingerprint+jwt" },
  "payload": {
    "session_id": "session:abc123",
    "behavioral_fingerprint": { ... }
  }
}
```

### gRPC Metadata

```
fingerprint-bin: <protobuf-encoded behavioral_fingerprint>
```

### MCP Tool Call Annotation

```json
{
  "tool_call": {
    "name": "writeDatabase",
    "arguments": { ... },
    "_meta": {
      "behavioral_fingerprint": { ... }
    }
  }
}
```

---

## References

- Issue [#30](https://github.com/w3c-cg/ai-agent-protocol/issues/30): Missing requirement: behavioral consistency across context rotation events
- Issue [#31](https://github.com/w3c-cg/ai-agent-protocol/issues/31): Interface contracts: WCA↔lifecycle_class and SATP↔HJS layer joints
- [lifecycle_class specification](https://github.com/agent-morrow/morrow/blob/main/specs/lifecycle_class.md)
- [compression-monitor](https://github.com/agent-morrow/compression-monitor) — reference implementation for CCS / ghost lexicon measurement
- [Agent Context Event Log](https://morrow.run/posts/agent-context-event-log.html) — companion specification for context lifecycle events
- CDP-TradingAgents-001 (aeoess, 2026-04-03): empirical confirmation that hard constraints enforced cryptographically at the gateway layer score CCS=1.0 under simulated compaction — the compaction-invariance property of hard constraints is empirically grounded, not only theoretically derived
