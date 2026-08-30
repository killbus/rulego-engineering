# RuleGo engineering

This is the normative entry point for engineering across the RuleGo ecosystem.
The repository owns durable cross-repository practice. It does not mirror
current versions, node schemas, deployment configuration, or release state.

## Route the work

| Question | Read |
| --- | --- |
| Which repository or runtime owns this fact? | [Ownership and authority](./rulego-ownership.md) |
| Does the behavior belong in a graph, plugin, service, or consumer? | [Capability design](./rulego-capability-design.md) |
| How is a dynamic plugin built and proven compatible? | [Plugin delivery](./rulego-plugin-delivery.md) |
| How is a rule chain deployed and verified end to end? | [Runtime verification](./rulego-runtime-verification.md) |
| How should the work be planned, reviewed, committed, and delivered? | [Delivery workflow](./rulego-delivery-workflow.md) |

## Start every RuleGo task

1. State the user-visible outcome and its evidence before choosing a component.
2. Identify the owner of every input, capability, state transition, and output.
3. Inspect the current authoritative source; do not infer volatile facts from
   this repository or a prior conversation.
4. Select the smallest natural boundary that owns the capability without
   embedding provider policy or presentation policy into it.
5. Validate at the narrowest relevant layer, then verify the composed runtime
   and consumer boundary when the requirement crosses them.

## Evidence baseline

A claim is established only by evidence with the same scope as the claim.
Examples include repository tests for a node contract, matching-runtime load
checks for a plugin artifact, API read-back for a deployed rule, HTTP traces for
published resources, and direct observations for a downstream consumer.

Passing a narrower test is useful evidence but does not prove a broader system
outcome. Planning documents and intended behavior are not runtime evidence.

## Knowledge boundary

Put stable, reusable RuleGo practice in these guides. Keep implementation facts
in their owning repositories and operational facts in deployed systems. Record
task-specific research under the active task only. Normative guides state the
selected present practice and omit discarded paths.
