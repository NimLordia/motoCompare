from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from app.chat.prompts import SYSTEM_PROMPT

# Hard ceiling on graph super-steps per turn (~half of this in LLM calls); hitting
# it surfaces as an `error` event instead of an endless tool loop.
RECURSION_LIMIT = 25


def build_chat_agent(
    model: BaseChatModel,
    tools: list[BaseTool],
    checkpointer: BaseCheckpointSaver,
) -> CompiledStateGraph:
    """Two-node tool-calling loop: `agent` (LLM) ⇄ `tools`, with per-conversation
    history in the checkpointer. The system prompt is injected per call, not stored."""
    bound_model = model.bind_tools(tools)
    tools_by_name = {tool.name: tool for tool in tools}

    def agent_node(state: MessagesState) -> dict:
        response = bound_model.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
        )
        return {"messages": [response]}

    def tools_node(state: MessagesState) -> dict:
        # Deliberately sequential (unlike langgraph's ToolNode): the tools share
        # one SQLAlchemy session, which is not safe under concurrent tool calls.
        results: list[ToolMessage] = []
        for tool_call in state["messages"][-1].tool_calls:
            results.append(_run_tool_call(tools_by_name, tool_call))
        return {"messages": results}

    def route_after_agent(state: MessagesState) -> str:
        last_message = state["messages"][-1]
        if getattr(last_message, "tool_calls", None):
            return "tools"
        return END

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tools_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=checkpointer)


def _run_tool_call(tools_by_name: dict[str, BaseTool], tool_call: dict) -> ToolMessage:
    """LLM mistakes (unknown tool, invalid arguments) become error tool messages
    the model can react to; genuine tool bugs propagate and fail the stream."""
    name = tool_call["name"]
    tool = tools_by_name.get(name)
    if tool is None:
        return ToolMessage(
            content=f'Error: unknown tool "{name}".',
            tool_call_id=tool_call["id"],
            status="error",
        )
    try:
        # The explicit "type" makes tool.invoke return a ToolMessage (with the
        # blocks artifact) instead of bare content.
        return tool.invoke({**tool_call, "type": "tool_call"})
    except ValidationError as error:
        return ToolMessage(
            content=f"Error: invalid arguments for {name}: {error}",
            tool_call_id=tool_call["id"],
            status="error",
        )
