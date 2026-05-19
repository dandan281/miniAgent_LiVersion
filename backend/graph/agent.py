"""
AgentManager — singleton that owns the LLM, tools, session manager,
and memory indexer. Rebuilds the agent on every request via create_agent
so that live workspace edits are always reflected in the system prompt.
"""
import re
from pathlib import Path
from typing import AsyncGenerator, Optional

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from config import get_agent_runtime_limit
from runtime.model_factory import build_chat_model
from .memory_indexer import MemoryIndexer
from .prompt_builder import (
    build_retrieved_memory_block,
    build_simple_system_prompt,
    build_system_prompt,
)
from .session_manager import SessionManager
from .skill_router import select_skill_entries_for_query
from tools.contracts import normalize_tool_output

_HARNESS_GUIDANCE = """
<!-- Runtime Harness Guidance -->
For non-trivial tasks, use the helper-agent tools deliberately:
- Call `plan_agent` before broad multi-step tool use when you need to decide the order of work.
- Use the returned plan to guide tool choice and sequencing.
- After a draft answer for non-trivial, tool-backed, or higher-risk work, call `verification_agent` to challenge the result before responding.
- Skip verification for small conversational turns or obviously complete low-risk answers where a repair pass would add little user value.
- If verification reports `repair_required` or `fail`, fix the material issues before finalizing your answer.
""".strip()

# Short, conversational turns shouldn't trigger planner+verifier hops or tool
# binding — they double or triple the LLM round-trip cost for no quality gain.
# Tools and helper agents are bound only when the input looks like real work.
_HARNESS_KEYWORDS = (
    "analyz", "implement", "refactor", "debug", "design", "plan ", "plan,", "plan.",
    "optimize", "optimiz", "migrate", "deploy", "build", "generate", "execute",
    "investigate", "audit", "compare", "benchmark", "fix ", "diagnose",
    "search ", "locate ", "trace ", "calculate", "compute", "process ", "extract",
    "parse", "modify", "write file", "edit file", "read file",
)
_FILE_PATH_EXTENSIONS = (
    ".py", ".ts", ".tsx", ".md", ".json", ".yaml", ".yml", ".csv", ".tsv",
    ".txt", ".log", ".sh", ".sql", ".h5", ".h5ad", ".ipynb", ".pdf",
)
_BULLET_LINE_RE = re.compile(r"^\s*([-*•]|\d+[.)])\s")


def _has_file_path_token(message: str) -> bool:
    for raw in message.split():
        token = raw.strip("`'\"()[]<>,;:{}")
        if "/" in token and any(token.endswith(ext) for ext in _FILE_PATH_EXTENSIONS):
            return True
    return False


def _looks_like_complex_turn(message: str) -> bool:
    """True when the input looks like long-and-structured work that should be
    handled by the full agent loop (tools + skills + helper agents). False for
    short conversational/factual turns that should take the pure-LLM fast path.
    """
    if not message:
        return False
    lowered = message.lower()

    # Explicit structural markers — code, file paths, or compute-work keywords.
    if "```" in message:
        return True
    if _has_file_path_token(message):
        return True
    if any(kw in lowered for kw in _HARNESS_KEYWORDS):
        return True

    # Multi-line input with several bulleted/numbered lines reads as a task list.
    lines = message.strip().splitlines()
    if len(lines) >= 4:
        bullet_count = sum(1 for ln in lines if _BULLET_LINE_RE.match(ln))
        if bullet_count >= 2:
            return True

    # Walls of text (pasted logs/data) — assume the user wants real processing.
    if len(message) > 800:
        return True

    return False


class AgentManager:
    def __init__(self) -> None:
        self.llm = None
        self.planner_llm = None
        self.verifier_llm = None
        self.title_llm = None
        self.tools: list = []
        self.session_manager: Optional[SessionManager] = None
        self.memory_indexer: Optional[MemoryIndexer] = None
        self.base_dir: Optional[Path] = None

    # ------------------------------------------------------------------ #
    # Initialisation                                                       #
    # ------------------------------------------------------------------ #

    def initialize(self, base_dir: Path) -> None:
        self.base_dir = base_dir

        self.llm = build_chat_model("executor", streaming=True)
        self.planner_llm = build_chat_model("planner", streaming=True)
        self.verifier_llm = build_chat_model("verifier", streaming=True)
        self.title_llm = build_chat_model("title", streaming=False)

        from tools import get_runtime_tools

        self.tools = get_runtime_tools(base_dir)
        self.session_manager = SessionManager(base_dir)
        self.memory_indexer = MemoryIndexer(base_dir)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _build_messages(self, history: list[dict]) -> list:
        """Convert session history dicts to LangChain message objects."""
        messages = []
        for msg in history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
            elif role == "system":
                # Used for injected context such as RAG-retrieved memory
                messages.append(SystemMessage(content=content))
        return messages

    def _build_agent(
        self,
        rag_mode: bool = False,
        *,
        skill_entries: list[dict] | None = None,
    ):
        """
        Rebuild the agent from scratch, ensuring the latest workspace edits
        and RAG configuration are reflected in the system prompt.
        """
        assert self.base_dir is not None, "AgentManager not initialised"
        system_prompt = (
            f"{build_system_prompt(self.base_dir, rag_mode, skill_entries=skill_entries)}"
            f"\n\n{_HARNESS_GUIDANCE}"
        )
        return create_agent(self.llm, self.tools, system_prompt=system_prompt)

    async def _stream_simple_turn(
        self, lc_messages: list
    ) -> AsyncGenerator[dict, None]:
        """Stream the executor LLM directly with no tools/skills/harness.

        Emits the same ``token``/``done``/``error`` events the chat runtime
        already consumes, so this is fully transparent to upstream layers.
        """
        assert self.base_dir is not None, "AgentManager not initialised"
        assert self.llm is not None, "executor LLM not initialised"

        system_prompt = build_simple_system_prompt(self.base_dir)
        messages = [SystemMessage(content=system_prompt), *lc_messages]

        try:
            async for chunk in self.llm.astream(messages):
                content = getattr(chunk, "content", "")
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    parts: list[str] = []
                    for item in content:
                        if isinstance(item, str):
                            parts.append(item)
                        elif isinstance(item, dict) and item.get("type") == "text":
                            parts.append(str(item.get("text", "")))
                    text = "".join(parts)
                else:
                    text = ""
                if text:
                    yield {"type": "token", "content": text}
        except Exception as exc:
            yield {"type": "error", "error": str(exc)}
            return

        yield {"type": "done"}

    def clear_session_runtime(self, session_id: str) -> None:
        for tool in self.tools:
            runtime_tool = getattr(tool, "wrapped_tool", tool)
            clear_session_state = getattr(runtime_tool, "clear_session_state", None)
            if callable(clear_session_state):
                clear_session_state(session_id)

    # ------------------------------------------------------------------ #
    # Streaming                                                            #
    # ------------------------------------------------------------------ #

    async def astream(
        self, message: str, history: list[dict]
    ) -> AsyncGenerator[dict, None]:
        """
        Core streaming generator. Yields typed event dicts:

          retrieval    — RAG results before the agent runs
          token        — streaming LLM text token
          tool_start   — agent is about to call a tool
          tool_end     — tool finished (legacy output string plus structured result)
          new_response — agent started a new text segment after tool use
          done         — agent finished the full turn
          error        — unhandled exception
        """
        from config import get_rag_mode

        assert self.base_dir is not None, "AgentManager not initialised"

        rag_mode = get_rag_mode()

        # ── RAG injection ──────────────────────────────────────────────
        if rag_mode and self.memory_indexer:
            try:
                results = self.memory_indexer.retrieve(message, top_k=3)
                if results:
                    yield {"type": "retrieval", "query": message, "results": results}
                    rag_block = build_retrieved_memory_block(results)
                    # Injected as a system message so the model treats this as
                    # provided context, not as something it previously said.
                    if rag_block:
                        history = history + [{"role": "system", "content": rag_block}]
            except Exception:
                pass  # RAG failure is non-fatal

        # ── Build message list ─────────────────────────────────────────
        lc_messages = (
            self._build_messages(history)
            + [HumanMessage(content=message)]
        )

        # ── Fast path: short conversational/factual turns ─────────────
        # When the input doesn't look like structured work, skip the full
        # agent loop entirely. Tools, skills, helper agents (planner +
        # verifier), and the recursion-limited LangGraph runtime are all
        # bypassed — we stream the executor LLM directly with a minimal
        # persona+memory system prompt.
        if not _looks_like_complex_turn(message):
            async for event in self._stream_simple_turn(lc_messages):
                yield event
            return

        # ── Build agent (rebuilt every request) ───────────────────────
        selected_skill_entries = select_skill_entries_for_query(
            self.base_dir,
            message,
            history=history,
        )
        agent = self._build_agent(
            rag_mode,
            skill_entries=selected_skill_entries,
        )

        # ── Stream events ──────────────────────────────────────────────
        after_tool = False
        # Track tool names already announced via tool_intent to avoid duplicates
        _emitted_intents: set[str] = set()

        # Biology requests with retrieval and multi-step reasoning often need
        # far more graph turns than LangGraph's small default budget.
        run_config = {
            "recursion_limit": get_agent_runtime_limit(
                "executor_recursion_limit",
                1000,
            )
        }
        try:
            async for event in agent.astream_events(
                {"messages": lc_messages},
                version="v2",
                config=run_config,
            ):
                kind = event["event"]

                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if chunk.content:
                        if after_tool:
                            yield {"type": "new_response"}
                            after_tool = False
                        yield {"type": "token", "content": chunk.content}
                    else:
                        # Model is silently building a tool call (no text output).
                        # Emit tool_intent as soon as the tool name is known so
                        # the UI can escape "Preparing next step." immediately.
                        tc_chunks = getattr(chunk, "tool_call_chunks", None) or []
                        for tc in tc_chunks:
                            tc_name = getattr(tc, "name", None)
                            if tc_name and tc_name not in _emitted_intents:
                                _emitted_intents.add(tc_name)
                                yield {"type": "tool_intent", "tool": tc_name}

                elif kind == "on_tool_start":
                    # Clear intents — the real tool_start supersedes them
                    _emitted_intents.clear()
                    run_id = event["run_id"]
                    tool_name = event["name"]
                    raw_input = event["data"].get("input", {})

                    # Flatten single-key dict inputs for readability
                    if isinstance(raw_input, dict) and len(raw_input) == 1:
                        tool_input_str = str(next(iter(raw_input.values())))
                    else:
                        tool_input_str = str(raw_input)

                    yield {
                        "type": "tool_start",
                        "tool": tool_name,
                        "input": tool_input_str,
                        "run_id": run_id,
                    }

                elif kind == "on_tool_end":
                    run_id = event["run_id"]
                    raw_output = event["data"].get("output", "")
                    result = normalize_tool_output(event["name"], raw_output)

                    payload = {
                        "type": "tool_end",
                        "tool": event["name"],
                        "output": result.summary,
                        "result": result.model_dump(mode="json"),
                        "run_id": run_id,
                    }
                    policy = result.metadata.get("policy")
                    if isinstance(policy, dict):
                        payload["policy"] = policy
                    yield payload
                    after_tool = True

        except Exception as exc:
            yield {"type": "error", "error": str(exc)}
            return

        yield {"type": "done"}


# Module-level singleton
agent_manager = AgentManager()
