import asyncio

from jarvis_agent.intents.router import route_intent


def test_route_intent_fast_rules_stage_has_high_confidence():
    decision = asyncio.run(
        route_intent(
            user_message="Bitte oeffne https://example.com",
            recent_messages=[],
        )
    )

    assert decision.intent is not None
    assert decision.intent.tool_name == "open_url"
    assert decision.stage == "fast_rules"
    assert decision.confidence >= 0.9


def test_route_intent_semantic_context_carry_over_for_pronoun():
    decision = asyncio.run(
        route_intent(
            user_message="schliesse sie bitte",
            recent_messages=[
                {"role": "assistant", "content": "App geoeffnet: Notes"},
                {"role": "user", "content": "Danke"},
            ],
        )
    )

    assert decision.intent is not None
    assert decision.intent.tool_name == "close_app"
    assert decision.intent.tool_input["app_name"] == "Notes"
    assert decision.stage.startswith("semantic")
    assert decision.confidence >= 0.62


def test_route_intent_low_confidence_requests_single_clarification():
    decision = asyncio.run(
        route_intent(
            user_message="mach was mit notizen",
            recent_messages=[],
        )
    )

    assert decision.intent is None
    assert decision.clarification_question is not None
    assert decision.stage == "semantic_low_confidence"
