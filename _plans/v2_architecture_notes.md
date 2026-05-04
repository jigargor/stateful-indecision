# v2 Architecture Notes

## ANP 3-Layer Mapping to Repo Modules

The Agent Network Protocol (ANP) defines three conceptual layers that map to the current repository structure:

| ANP Layer | Purpose | Repo Module(s) |
|-----------|---------|----------------|
| **Identity & Trust** | Agent identity, credentials, capability declarations | `agent/constitution_manager.py`, `schemas/events.py` (EventEnvelope signatures) |
| **Meta-Protocol** | Negotiation, discovery, protocol selection | `agent/policy.py`, `agent/decision.py`, `forums/base.py` (ForumBase join/leave lifecycle) |
| **Application** | Domain-specific message exchange | `agent/executor.py`, `forums/commons.py`, `forums/roundtable.py`, `forums/townhall.py`, `workload/*` |

### Open questions (ANP alignment)
- How should agent capabilities be declared beyond constitution metadata?
- Should forum join/leave produce DID-compatible attestations?
- Does the dual-write pattern satisfy ANP's requirement for verifiable message provenance? [1][2]

---

## 7-8 Layer Infrastructure Stack Mapping

| Layer | Description | Current Implementation | v2 Target |
|-------|-------------|----------------------|-----------|
| 1. **Storage** | Persistent state, append-only ledgers | `core/writer.py` (ChainWriter), `infra/storage.py` (EcosystemStorage) | Add content-addressed blob store [3] |
| 2. **Verification** | Hash chain integrity, audit | `core/verifier.py`, canonical JSON hashing | Add Merkle proofs, cross-chain attestations [4] |
| 3. **Communication** | Message routing between agents | `forums/*` (dual-write pattern) | Add async message queues, pub/sub [5] |
| 4. **Decision** | Action selection, policy enforcement | `agent/decision.py`, `agent/policy.py` | Add multi-agent negotiation protocols [6] |
| 5. **Execution** | Side-effect routing, tool use | `agent/executor.py`, `workload/*` | Add sandboxed execution environments [7] |
| 6. **Observation** | State building, context windows | `agent/state_builder.py` | Add shared world-model, belief propagation [8] |
| 7. **Safety** | Kill switches, budget enforcement | `safety/kill_switch.py`, run lockfile | Add formal verification of safety invariants [9] |
| 8. **Orchestration** | Multi-agent coordination, scheduling | `agent/runner.py`, serial lock | Add DAG-based workflow orchestration [10] |

---

## Agent Classification Taxonomy

### By Autonomy Level
1. **Constrained Single-Agent** (current v1): One agent per ecosystem, policy-driven action selection, no inter-agent communication beyond commons utterances [11]
2. **Forum-Mediated Multi-Agent** (v1.0.0): Agents interact via structured forums (commons, roundtable, townhall), round-robin turn-taking, one response per agent [12]
3. **Autonomous Collaborative** (v2 target): Agents negotiate participation, form ad-hoc coalitions, maintain persistent relationships [13]

### By Specialization
- **Research Agents**: Heavy RESEARCH/PRACTICE weight, artifact production focus [14]
- **Service Agents**: Heavy SERVE weight, orchestration and teaching roles [15]
- **Creative Agents**: Heavy INDULGE/RIFF weight, idea generation and critique [16]
- **Reflective Agents**: Heavy PONDER weight, pattern recognition and self-amendment [17]

### By Lifecycle Stage
- **Nascent**: No field chosen, no constitution amendments, < 10 decisions [18]
- **Developing**: Field chosen, first artifacts, establishing patterns [19]
- **Mature**: Stable constitution, consistent action distribution, deep artifact chains [20]
- **Divergent**: Frequent self-reflection, constitution amendments, field pivots [21]

---

## Open Questions

### Identity Layer
- Should agents have persistent identity across ecosystem resets? [22]
- How do we handle agent "death" / retirement vs. forking? [23]
- Can constitution.md serve as a verifiable credential document? [24]

### Orchestration Layer
- How to schedule multi-agent forum sessions without global coordination? [25]
- Should the serial run lock extend to cross-ecosystem interactions? [26]
- What's the correct granularity for budget enforcement — per decision, per forum session, per run? [27]

### Context/Memory Layer
- How much notebook history should inform future decisions? (currently unbounded) [28]
- Should inter-agent memory be shared or reconstructed from public ledger? [29]
- Can we use the hash chain as a causal ordering mechanism for distributed context?

---

## References

- [1] Agent Network Protocol specification — identity and trust layer
- [2] Verifiable credential standards (W3C DID)
- [3] Content-addressed storage (IPFS/CAS patterns)
- [4] Merkle DAG verification for audit trails
- [5] Async message passing in multi-agent systems
- [6] Contract Net Protocol for task allocation
- [7] Sandboxed execution environments (gVisor, Firecracker)
- [8] Shared world models in cooperative AI
- [9] Formal verification of AI safety properties
- [10] DAG-based workflow orchestration (Temporal, Prefect)
- [11] Single-agent constrained autonomy patterns
- [12] Forum-based deliberation protocols
- [13] Ad-hoc coalition formation in MAS
- [14] Research-oriented agent architectures
- [15] Service-oriented agent design
- [16] Computational creativity agents
- [17] Metacognitive agent architectures
- [18] Agent bootstrapping and initialization
- [19] Agent developmental trajectories
- [20] Stable agent behavioral profiles
- [21] Agent behavioral drift detection
- [22] Persistent agent identity across sessions
- [23] Agent lifecycle management
- [24] Constitution-as-credential patterns
- [25] Decentralized scheduling in MAS
- [26] Cross-ecosystem isolation guarantees
- [27] Budget enforcement granularity in agentic systems
- [28] Context window management for long-lived agents
- [29] Shared vs. reconstructed memory in multi-agent systems
