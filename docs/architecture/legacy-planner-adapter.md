# YJ2-04B: legacy planner adapter

Base: `db6dd6738e8d55a61fbcc0af7ef364d80fbd9d31`, after external acceptance of
PR #8 and all six main CI checks. This extracts existing single-tool planning;
it does not introduce the V2 Structured Planner.

## Boundary and compatibility

`TurnEngine -> LegacyRouting -> deterministic stages -> LegacyPlannerAdapter.plan`
`-> existing llm.plan_tool_call`.

LegacyRouting has no direct LLM import. It preserves all 13 routing priorities:
learned and heuristic intents return before asking the adapter; an adapter `None`
still leads to the existing unclear-tool clarification or conversational fallback.
The deterministic stage implementation is unchanged. The adapter has no events,
response rendering, tool execution, approval creation or OS/provider selection.
TurnEngine still creates a separate approval for a valid intent.

The adapter owns the existing feature-flag check, tool-request check, ranked
legacy registry specs, model call, result validation and planner-intent adaptation.
AgentService still reads `JARVIS_ENABLE_TOOL_PLANNER` with the same default **off**
and passes its value through the router constructor. No new flag or environment
read is introduced. The adapter's `enable_tool_planner` attribute owns this value.

Model arguments/defaults remain `ollama_base_url=http://127.0.0.1:11434` and
`model_name=qwen2.5:3b-instruct`. Ranking uses the same
`LearningEngine.rank_tool_specs_for_planner(ToolRegistry.list_specs())` call.
The existing LLM implementation, prompts, model parameters and tool arguments
are unchanged. This is registry membership validation, not provider availability.

## Fallback and learning

Disabled planning, non-tool text, model-call exceptions, empty/None output,
missing/blank tool name, non-dictionary input and unknown tool all return `None`.
This replaces the old `heuristic_intent` fallback variable, which was always
`None` at this point because a matching heuristic had already returned.
The exception boundary is deliberately unchanged: only `plan_tool_call` is inside
the `try`; ranking/adaptation errors and cancellation still propagate. The
adapter does not add recovery, repair or a new result schema.

`/learn` keeps the same injected action resolver with learned commands disabled
for action resolution. When enabled, an unrecognized tool-like action may reach
this planner; a stored trigger is subsequently resolved before the planner.
Tests seed a conflicting learned command to prove it is not used recursively,
check stored tool/input, and verify subsequent trigger use needs approval without
another model call. Real adaptive routing changes a planned `open_app(Raycast)`
into `raycast_open` when existing performance history prefers it.

## Evidence and remaining work

22 new characterization cases plus all 43 routing and 37 lifecycle cases passed
before extraction (102 total). Adapter tests then exercise the extracted class
directly and add structural checks. Existing test assertions remain; only the
model mock target and internal flag path move to the adapter. Model I/O is stubbed;
integration cases use real temporary SQLite, learning and TurnEngine.

YJ2-05 owns ToolSpec V2 / ToolRuntime and later provider availability. YJ2-11 owns
the structured ActionPlan planner and multi-step planning. Policy, NLU collision
fixes, Windows providers, UI/voice, performance and packaging remain out of scope.
No dependencies or data migrations are added. Revert this PR to roll back without
resetting runtime data. STOP after checks for external diff/architecture review.
