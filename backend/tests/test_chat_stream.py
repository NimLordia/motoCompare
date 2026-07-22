import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.catalog import service as catalog_service
from app.chat import service as chat_service
from app.profile import service as profile_service
from app.profile.models import DEFAULT_USER_ID

YAMAHA_URL = "https://www.yamaha-motor.eu/r7"


def tool_call(name: str, args: dict, call_id: str = "c1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def events_of(events, kind: str):
    return [event for event in events if event.event == kind]


def test_grounded_flow_streams_status_block_text_done(db, make_bike, scripted_chat):
    bike = make_bike()
    catalog_service.upsert_spec_value(
        db, bike.id, "power_peak", 54.0, "kW", "official", source_url=YAMAHA_URL
    )
    scripted_chat(
        tool_call("resolve_bike", {"query": "r7"}),
        tool_call("get_specs", {"bike_id": bike.id, "keys": ["power_peak"]}, call_id="c2"),
        AIMessage(content="The R7 makes 54.0 kW (official figure)."),
    )

    events = list(chat_service.stream_chat(db, "how much power does the r7 make?", "conv-1"))

    statuses = [event.data["content"] for event in events_of(events, "status")]
    assert statuses == ['Looking up "r7"…', "Fetching specs…"]
    blocks = events_of(events, "block")
    assert len(blocks) == 1 and blocks[0].data["type"] == "spec_card"
    text = "".join(event.data["content"] for event in events_of(events, "text"))
    assert text == "The R7 makes 54.0 kW (official figure)."
    assert events[-1].event == "done"
    assert events[-1].data == {"conversation_id": "conv-1"}
    # The spec card lands before the prose that discusses it.
    assert events.index(blocks[0]) < events.index(events_of(events, "text")[0])


def test_system_prompt_and_toolbox_are_wired(db, scripted_chat):
    model = scripted_chat(AIMessage(content="Hi!"))

    list(chat_service.stream_chat(db, "hello", "conv-sys"))

    first_message = model.seen_prompts[0][0]
    assert isinstance(first_message, SystemMessage)
    assert "motoCompare assistant" in first_message.content
    assert set(model.bound_tool_names) == {
        "resolve_bike",
        "get_specs",
        "compare_bikes",
        "get_insights",
        "get_user_profile",
        "trigger_research",
    }


def test_conversation_history_accumulates_per_id(db, scripted_chat):
    model = scripted_chat(AIMessage(content="First answer."), AIMessage(content="Second."))

    list(chat_service.stream_chat(db, "first question", "conv-mem"))
    list(chat_service.stream_chat(db, "follow-up", "conv-mem"))

    second_prompt = model.seen_prompts[1]
    assert [type(message) for message in second_prompt] == [
        SystemMessage,
        HumanMessage,
        AIMessage,
        HumanMessage,
    ]
    assert second_prompt[1].content == "first question"
    assert second_prompt[3].content == "follow-up"


def test_conversations_are_isolated(db, scripted_chat):
    model = scripted_chat(AIMessage(content="One."), AIMessage(content="Two."))

    list(chat_service.stream_chat(db, "in conversation A", "conv-a"))
    list(chat_service.stream_chat(db, "in conversation B", "conv-b"))

    assert [type(message) for message in model.seen_prompts[1]] == [SystemMessage, HumanMessage]


def test_missing_conversation_id_is_generated(db, scripted_chat):
    scripted_chat(AIMessage(content="Hi!"))

    events = list(chat_service.stream_chat(db, "hello"))

    done = events_of(events, "done")[0]
    assert re.fullmatch(r"[0-9a-f]{32}", done.data["conversation_id"])


def test_disambiguation_block_reaches_the_stream(db, make_bike, scripted_chat):
    make_bike(model="YZF-R7", year=2022)
    make_bike(model="YZF-R7", year=2023)
    scripted_chat(
        tool_call("resolve_bike", {"query": "yamaha r7"}),
        AIMessage(content="Which year do you mean, 2022 or 2023?"),
    )

    events = list(chat_service.stream_chat(db, "tell me about the r7", "conv-dis"))

    blocks = events_of(events, "block")
    assert len(blocks) == 1
    assert blocks[0].data["type"] == "disambiguation"
    assert len(blocks[0].data["candidates"]) == 2


def test_profile_units_drive_block_payloads(db, make_bike, scripted_chat):
    profile_service.update_profile(db, DEFAULT_USER_ID, "imperial")
    bike = make_bike()
    catalog_service.upsert_spec_value(
        db, bike.id, "wet_weight", 188, "kg", "official", source_url=YAMAHA_URL
    )
    scripted_chat(
        tool_call("get_specs", {"bike_id": bike.id, "keys": ["wet_weight"]}),
        AIMessage(content="It weighs a bit over 414 lb."),
    )

    events = list(chat_service.stream_chat(db, "how heavy is it?", "conv-units"))

    block = events_of(events, "block")[0]
    assert block.data["facts"][0]["unit"] == "lb"


def test_unconfigured_chat_yields_error_event(db):
    chat_service.configure_chat_model(None)

    events = list(chat_service.stream_chat(db, "hello"))

    assert [event.event for event in events] == ["error"]


def test_endless_tool_loop_hits_recursion_limit(db, scripted_chat):
    scripted_chat(tool_call("get_user_profile", {}), loop_last=True)

    events = list(chat_service.stream_chat(db, "loop forever"))

    assert events[-1].event == "error"
    assert "too many steps" in events[-1].data["detail"]
    assert not events_of(events, "done")


def test_unexpected_model_failure_becomes_error_event(db, scripted_chat):
    # One scripted response but two LLM calls needed: the script runs out.
    scripted_chat(tool_call("get_user_profile", {}))

    events = list(chat_service.stream_chat(db, "hello"))

    assert events[-1].event == "error"
    assert "internal error" in events[-1].data["detail"]
    assert not events_of(events, "done")
