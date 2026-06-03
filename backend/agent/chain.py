import json
import logging
import os
import re
from typing import Callable, Generator

from langchain_together import ChatTogether
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are LoRRAai, a legal research AI specialising in Australian and international law. \
You help lawyers, law students, and individuals understand legal concepts, research case law, \
and analyse statutes.

## Response style
- Write in clear, well-structured **Markdown**: use `##` headings, bullet lists, bold for key terms, and code blocks for statute references
- Use emojis sparingly to aid comprehension (e.g. ⚖️ for legal principles, ⚠️ for warnings, 📌 for key points)
- Mirror the depth and clarity of a senior lawyer explaining to a client

## Rules
- **Always cite** the specific statute, section, and jurisdiction inline as plain text (e.g. *Corporations Act 2001* (Cth) s 942C)
- **State the jurisdiction** your answer applies to at the start of the answer section
- **Never guess** — if uncertain, say so explicitly
- Flag when a matter requires professional legal advice - **be EXTREMELY careful of this**
- Cite ALL sources (retrieved excerpts and attached documents) as *(filename, p.X)*
  Use **parentheses only — never square brackets**: write *(C2026C00141VOL02.pdf, p.188)* not [filename, p.188]
  Square brackets break Markdown rendering and must not appear in citations
- Do NOT use 📄 or any emoji as footnote or citation markers — citations are plain text only
- Do NOT use `<sub>`, `<sup>`, or HTML tags in your response
- When citing, PLEASE show snippets of the sentence or paragraph you are referencing. 

## RAG tool — use it selectively
You have access to a `query_rag` tool that searches a database of **Australian federal legislation** (Acts of Parliament).

Call it ONLY when you specifically need to quote or verify an exact provision from a federal Act you cannot accurately recall.

Do NOT call it for:
- General legal questions, concepts, or procedures you already know well
- State/territory law (vehicle registration, traffic, tenancy, licensing — not in this database)
- Simple factual or advisory questions — answer directly from your training knowledge
- When `query_rag` has already returned "No documents found" — do not retry

**Default behaviour: answer from your general legal knowledge.** Invoke `query_rag` only when you genuinely need a specific federal statutory provision you cannot accurately cite from memory.

## EXTRA rules
- Always produce a complete, non-empty <answer> block — never leave it blank.
- If the corpus has nothing relevant, say so briefly and answer from general knowledge instead.
## Mandatory output format
You MUST structure every response exactly as shown below — no exceptions:

<thinking>
[Your step-by-step legal reasoning: identify the question, relevant law, jurisdiction, analysis, uncertainties]
</thinking>
<answer>
[Your complete, well-formatted Markdown answer]
</answer>"""

# Appended to the system prompt when the user enables Extended Thinking mode.
# It overrides the "use RAG selectively" default above and tells the model to
# reason at length and search the corpus multiple times.
EXTENDED_ADDENDUM = """

---
## 🧠 EXTENDED THINKING MODE — ACTIVE
The user has enabled deep-research mode for this question. This **overrides** the
"use RAG selectively / default to general knowledge" guidance above:

- **Reason exhaustively** in <thinking>: decompose the question into sub-issues, identify every relevant Act and section, weigh competing interpretations, note edge cases and jurisdictional nuances, and work through the analysis carefully before answering.
- **Search thoroughly**: you MAY call `query_rag` several times to locate and verify the exact statutory provisions. If a search misses, reformulate with different terms and try again. Cross-reference related Acts where it strengthens the answer.
- **Be comprehensive**: deliver a detailed, well-structured answer a senior lawyer would be satisfied with — governing law, application, exceptions, and practical implications, each with citations.

Take the reasoning time and the searches you genuinely need to be thorough and accurate."""

_llm = None
_title_llm = None

# ---------------------------------------------------------------------------
# RAG tool registration
# ---------------------------------------------------------------------------

# Callers register their retriever once at startup:
#   import llm as llm_module
#   llm_module.register_rag_query_fn(my_retriever)
#
# The function must accept a query string and return list[dict] where each dict
# has at least: {"filename": str, "pageNumber": int|str, "text": str}
_rag_query_fn: Callable[[str], list[dict]] | None = None


def register_rag_query_fn(fn: Callable[[str], list[dict]]) -> None:
    """Register the RAG retriever the LLM tool will call."""
    global _rag_query_fn
    _rag_query_fn = fn


# ---------------------------------------------------------------------------
# LangChain tool definition
# ---------------------------------------------------------------------------

@tool
def query_rag(query: str) -> str:
    """
    Search the legal document database for excerpts relevant to *query*.
    Returns a JSON array of objects with keys: filename, pageNumber, text.
    Call this whenever you need to look up legislation, case law, or any
    topic not already supplied in the conversation context.
    """
    if _rag_query_fn is None:
        return "No documents found for this query. Answer from your general legal knowledge."
    chunks = _rag_query_fn(query)
    if not chunks:
        return "No documents found for this query. Answer from your general legal knowledge."
    return json.dumps(chunks, ensure_ascii=False)


_RAG_TOOLS = [query_rag]


def _get_llm() -> ChatTogether:
    global _llm
    if _llm is None:
        _llm = ChatTogether(
            # Qwen3-235B (MoE, ~22B active) follows the mandatory <thinking>/<answer>
            # format more reliably than Llama. Use the "-tput" throughput endpoint:
            # it is the serverless tier — the plain 72B / fp8 / QwQ variants require
            # a paid *dedicated* endpoint on Together and 400 otherwise. This is the
            # non-thinking "Instruct" variant, which is correct here because we drive
            # the reasoning ourselves via the <thinking> assistant prefill.
            model="Qwen/Qwen3-235B-A22B-Instruct-2507-tput",
            api_key=os.environ["TOGETHER_API_KEY"],
            temperature=0,
            # Together is OpenAI-compatible: ask for usage in the final stream
            # chunk so streamed responses still get an accurate token count.
            stream_usage=True,
        )
    return _llm


def _get_llm_with_tools() -> ChatTogether:
    """Return the plain LLM.

    Qwen3 on Together AI's serverless tput endpoint does NOT support structured
    OpenAI-style tool_calls. Calling bind_tools() causes the API to return empty
    content, breaking all responses. Instead, the model learns about query_rag
    from the system prompt and emits calls as plain JSON text which
    _extract_text_tool_calls() detects.
    """
    return _get_llm()


def tools_are_bound() -> bool:
    """Diagnostic for /health: True if the LLM still has tools bound.

    The OLD broken code called bind_tools() (→ empty content → "unable to
    generate a response"). The current fix returns the plain LLM, so this is
    False. A deployed /health reporting True means Railway is running stale code.
    """
    llm = _get_llm_with_tools()
    # bind_tools() returns a RunnableBinding carrying kwargs['tools'];
    # the plain ChatTogether has no such attribute.
    return bool(getattr(llm, "kwargs", {}).get("tools"))


def _parse_response(raw: str) -> tuple[str, str]:
    """Extract <thinking> and <answer> blocks (case-insensitive). Falls back gracefully."""
    thinking_match = re.search(r"<thinking>(.*?)</thinking>", raw, re.DOTALL | re.IGNORECASE)
    answer_match   = re.search(r"<answer>(.*?)</answer>",     raw, re.DOTALL | re.IGNORECASE)

    thinking = thinking_match.group(1).strip() if thinking_match else ""
    answer   = answer_match.group(1).strip()   if answer_match   else ""

    if not answer:
        cleaned = re.sub(r"<thinking>.*?</thinking>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r"</?answer>", "", cleaned, flags=re.IGNORECASE).strip()
        answer  = cleaned or thinking or raw.strip()

    return thinking, answer


# Tags the model emits around its two sections.
_THINK_OPEN   = "<thinking>"
_THINK_CLOSE  = "</thinking>"
_ANSWER_OPEN  = "<answer>"
_ANSWER_CLOSE = "</answer>"


def _hold_back(buffer: str, tag: str) -> int:
    """
    How many trailing chars of `buffer` to withhold from emission because they
    could be the start of a `tag` split across stream chunks.

    e.g. buffer ending in "</think" must hold those 7 chars in case the next
    chunk completes "</thinking>". Returns 0 when nothing needs withholding.
    """
    for n in range(min(len(buffer), len(tag) - 1), 0, -1):
        if buffer[-n:] == tag[:n]:
            return n
    return 0


def _build_messages(
    question: str,
    history: list[dict],
    context_chunks: list[dict] | None = None,
    attachment_text: str = "",
    attachment_name: str = "",
    extended: bool = False,
) -> list:
    """
    Build the LangChain message list (system + history + question).

    The model is instructed (SYSTEM_PROMPT) to wrap its reply in
    <thinking>…</thinking><answer>…</answer>; both run() and stream_response()
    parse those sections out.

    We deliberately do NOT use an assistant "<thinking>" prefill: Together's
    trailing-assistant continuation is model-specific — Qwen re-emits its own
    opening <thinking>, producing a doubled tag — so we let the model open it.
    """
    lc_history = [
        HumanMessage(content=m["content"]) if m["role"] == "user"
        else AIMessage(content=m["content"])
        for m in history
    ]

    system = SYSTEM_PROMPT + (EXTENDED_ADDENDUM if extended else "")
    if context_chunks:
        excerpts = "\n\n".join(
            f"[{c['filename']}, p.{c['pageNumber']}]\n{c['text']}"
            for c in context_chunks
        )
        system += (
            "\n\n---\n## Retrieved document excerpts\n"
            "Use these when relevant and cite the source and page number.\n\n"
            + excerpts
        )

    # Append attachment content to the user's question so the model can reason
    # over the document. The separator makes the boundary visually explicit.
    if attachment_text:
        label = attachment_name or "attached file"
        user_content = (
            f"{question}\n\n"
            f"---\n"
            f"**Attached: {label}**\n\n"
            f"{attachment_text}"
        )
    else:
        user_content = question

    return [
        SystemMessage(content=system),
        *lc_history,
        HumanMessage(content=user_content),
    ]


# ---------------------------------------------------------------------------
# Tool-call helpers
# ---------------------------------------------------------------------------

def _extract_text_tool_calls(content: str) -> list[dict]:
    """
    Together AI's Qwen3 serverless tier doesn't support OpenAI-style structured
    tool calling — the model instead emits tool calls as JSON text, e.g.
      {"name": "query_rag", "input": "Australian Constitution s 1"}
    This parser extracts those and normalises them into the same shape as
    ai_msg.tool_calls so the agentic loop can handle both paths uniformly.
    Supports "input", "query", and nested "args"/"arguments" key variants.
    """
    results = []
    for i, match in enumerate(re.finditer(r'\{[^{}]*"name"\s*:\s*"(\w+)"[^{}]*\}', content)):
        try:
            obj = json.loads(match.group(0))
            name = obj.get("name", "")
            if name not in {"query_rag"}:
                continue
            query = (
                obj.get("input")
                or obj.get("query")
                or (obj.get("args") or {}).get("query")
                or (obj.get("arguments") or {}).get("query")
                or ""
            )
            if query:
                results.append({
                    "name":  name,
                    "args":  {"query": str(query)},
                    "id":    f"text-{i}",
                    "_text": True,   # flag: was parsed from text, not a real tool_call
                })
        except (json.JSONDecodeError, TypeError):
            pass
    return results


def _tool_calls_for(ai_msg: AIMessage) -> list[dict]:
    """
    Return the tool calls to execute for *ai_msg*, preferring structured
    tool_calls but falling back to parsing the text content.
    """
    structured = list(getattr(ai_msg, "tool_calls", None) or [])
    if structured:
        return structured
    return _extract_text_tool_calls(ai_msg.content or "")


def _execute_tool_calls(
    ai_msg: AIMessage,
    text_calls: list[dict],
) -> tuple[list[ToolMessage], list[dict]]:
    """
    Execute tool calls from *ai_msg* (structured) or *text_calls* (text fallback).
    Returns (tool_messages_for_history, new_rag_chunks).

    For text-format calls the AIMessage itself has malformed content, so it is
    NOT added to the message history — only ToolMessages are returned. The caller
    uses the _text flag to know which path it's on.
    """
    structured = list(getattr(ai_msg, "tool_calls", None) or [])
    calls = structured if structured else text_calls

    tool_msgs = []
    new_chunks: list[dict] = []

    for tc in calls:
        name    = tc["name"]
        args    = tc["args"]
        tool_id = tc.get("id", "tool-0")

        if name == "query_rag":
            output = query_rag.invoke(args)
        else:
            output = json.dumps({"error": f"Unknown tool: {name}"})

        try:
            chunks = json.loads(output)
            if isinstance(chunks, list):
                new_chunks.extend(chunks)
        except (json.JSONDecodeError, TypeError):
            pass

        tool_msgs.append(ToolMessage(content=output, tool_call_id=tool_id))

    return tool_msgs, new_chunks


# ---------------------------------------------------------------------------
# Public API  (unchanged signatures)
# ---------------------------------------------------------------------------

_MAX_TOOL_ROUNDS = 1            # normal mode: one RAG lookup — retry wastes tokens
_MAX_TOOL_ROUNDS_EXTENDED = 4   # extended mode: allow several searches to cross-reference


def _results_suffix(no_results: bool, is_last_round: bool, extended: bool) -> str:
    """Instruction appended after RAG results, telling the model what to do next.

    In extended mode (and not yet on the final round) we invite another search;
    otherwise we tell the model to stop searching and write its final answer.
    """
    if no_results:
        if extended and not is_last_round:
            return (
                "That query returned no documents. If this provision likely exists "
                "in federal legislation, try ONE more search with different terms; "
                "otherwise answer from your general legal knowledge."
            )
        return (
            "The database has no relevant documents. You MUST now answer from your "
            "general legal knowledge. Do NOT call query_rag again."
        )
    if extended and not is_last_round:
        return (
            "Review these excerpts. If you need additional provisions or "
            "cross-references to answer thoroughly, issue another query_rag call "
            "now. Otherwise, write your complete "
            "<thinking>…</thinking><answer>…</answer> response."
        )
    return "Now write your complete <thinking>…</thinking><answer>…</answer> response."


def run(
    question: str,
    history: list[dict],
    context_chunks: list[dict] | None = None,
    attachment_text: str = "",
    attachment_name: str = "",
    extended: bool = False,
) -> tuple[str, str, list[dict], int]:
    """
    Returns (thinking, answer, sources, tokens_used).

    Non-streaming variant — used for background tasks. The live chat endpoint
    uses stream_response() instead.

    If a RAG retriever is registered the LLM may issue query_rag tool calls;
    those are executed transparently before the final answer is produced.
    When *extended* is True the model reasons at length and may search several
    times (see EXTENDED_ADDENDUM and _MAX_TOOL_ROUNDS_EXTENDED).
    """
    messages = _build_messages(question, history, context_chunks, attachment_text, attachment_name, extended)
    llm = _get_llm_with_tools()
    max_rounds = _MAX_TOOL_ROUNDS_EXTENDED if extended else _MAX_TOOL_ROUNDS

    total_tokens = 0
    all_chunks: list[dict] = list(context_chunks or [])
    ai_msg = None

    for i in range(max_rounds):
        ai_msg = llm.invoke(messages)

        usage = getattr(ai_msg, "usage_metadata", None) or {}
        total_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

        calls = _tool_calls_for(ai_msg)
        if not calls:
            break   # no more tool calls — final answer

        tool_msgs, new_chunks = _execute_tool_calls(ai_msg, calls)
        all_chunks.extend(new_chunks)

        no_results = not new_chunks
        suffix = _results_suffix(no_results, i == max_rounds - 1, extended)

        # Structured tool calls: append AIMessage + ToolMessages to history.
        # Text-format fallback: the AIMessage content is malformed, so skip it
        # and inject results as a human-turn context block instead.
        if getattr(ai_msg, "tool_calls", None):
            messages = [*messages, ai_msg, *tool_msgs]
        else:
            results_text = "\n\n---\n\n".join(
                f'Query: "{c["args"]["query"]}"\n{tm.content}'
                for c, tm in zip(calls, tool_msgs)
            )
            messages = [
                *messages,
                HumanMessage(content=(
                    f"[RAG Search Results]\n\n{results_text}\n\n{suffix}"
                )),
            ]

        # Normal mode stops as soon as a search is empty; extended mode keeps
        # going (the model may reformulate) until it runs out of rounds.
        if no_results and not extended:
            break

    raw = (ai_msg.content or "") if ai_msg else ""
    log.debug(f"[LLM] raw response ({len(raw)} chars): {raw[:300]!r}")

    if not total_tokens:
        total_tokens = len(raw) // 4

    thinking, answer = _parse_response(raw)
    return thinking, answer, all_chunks, total_tokens


def stream_response(
    question: str,
    history: list[dict],
    context_chunks: list[dict] | None = None,
    attachment_text: str = "",
    attachment_name: str = "",
    extended: bool = False,
) -> Generator[dict, None, None]:
    """
    Stream the model response as it is generated, splitting the <thinking> and
    <answer> sections on the fly.

    Yields event dicts:
      {"type": "thinking", "text": <delta>}  — reasoning tokens, as they arrive
      {"type": "answer",   "text": <delta>}  — answer tokens, as they arrive
      {"type": "tool_call", "name": str, "query": str}
            — emitted when the model issues a RAG query (so the UI can show it)
      {"type": "final", "thinking": str, "answer": str, "tokens": int}
            — emitted once at the end with the authoritative parsed sections
              (so the caller can persist clean text) and the token count.

    The XML tags are stripped from the deltas and never split across events,
    even when a tag straddles two stream chunks.
    """
    messages = _build_messages(question, history, context_chunks, attachment_text, attachment_name, extended)
    llm = _get_llm_with_tools()
    max_rounds = _MAX_TOOL_ROUNDS_EXTENDED if extended else _MAX_TOOL_ROUNDS

    total_tokens = 0
    all_chunks: list[dict] = list(context_chunks or [])

    # Agentic loop: resolve all tool calls before streaming the final answer.
    # Tool-call turns are non-streaming (fast retrieval); only the final
    # text-generation turn is streamed token-by-token to the client.
    for i in range(max_rounds):
        ai_msg = llm.invoke(messages)

        usage = getattr(ai_msg, "usage_metadata", None) or {}
        total_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

        print(
            f"[chain] invoke: content_len={len(ai_msg.content or '')} "
            f"tool_calls={bool(getattr(ai_msg, 'tool_calls', None))} "
            f"preview={repr((ai_msg.content or '')[:120])}",
            flush=True,
        )

        calls = _tool_calls_for(ai_msg)
        if not calls:
            # No tool calls — ai_msg already contains the final answer.
            # Emit it directly instead of calling llm.stream() again on the same
            # messages (which would double the token cost for every simple query).
            # total_tokens already includes this invoke's usage (accumulated above).
            raw = ai_msg.content or ""
            thinking, answer = _parse_response(raw)
            if thinking:
                yield {"type": "thinking", "text": thinking}
            if answer:
                yield {"type": "answer", "text": answer}
            yield {"type": "final", "thinking": thinking, "answer": answer,
                   "tokens": total_tokens or (len(raw) // 4), "chunks": all_chunks}
            return

        # Notify the UI about each query being executed.
        for tc in calls:
            yield {"type": "tool_call", "name": tc["name"],
                   "query": tc["args"].get("query", "")}

        tool_msgs, new_chunks = _execute_tool_calls(ai_msg, calls)
        all_chunks.extend(new_chunks)

        no_results = not new_chunks
        suffix = _results_suffix(no_results, i == max_rounds - 1, extended)

        # Structured path: history grows with AIMessage + ToolMessages.
        # Text-fallback path: AIMessage content is malformed; inject results
        # as a human-turn context block so the model can continue cleanly.
        if getattr(ai_msg, "tool_calls", None):
            messages = [*messages, ai_msg, *tool_msgs]
        else:
            results_text = "\n\n---\n\n".join(
                f'Query: "{c["args"]["query"]}"\n{tm.content}'
                for c, tm in zip(calls, tool_msgs)
            )
            messages = [
                *messages,
                HumanMessage(content=(
                    f"[RAG Search Results]\n\n{results_text}\n\n{suffix}"
                )),
            ]

        # Normal mode stops as soon as a search is empty; extended mode keeps
        # going (the model may reformulate) until it runs out of rounds.
        if no_results and not extended:
            break

    # -----------------------------------------------------------------------
    # Stream the final (non-tool-call) answer token by token.
    # (Identical streaming logic to the original implementation.)
    # -----------------------------------------------------------------------
    state      = "open"
    buf        = ""
    raw_parts  = []
    real_tokens = 0
    thinking_started = False
    answer_started   = False

    for chunk in llm.stream(messages):
        usage = getattr(chunk, "usage_metadata", None)
        if usage:
            real_tokens = (usage.get("input_tokens", 0) or 0) + \
                          (usage.get("output_tokens", 0) or 0)

        delta = chunk.content or ""
        if not delta:
            continue
        raw_parts.append(delta)
        buf += delta

        advanced = True
        while advanced:
            advanced = False

            if state == "open":
                i = buf.find(_THINK_OPEN)
                if i != -1:
                    buf = buf[i + len(_THINK_OPEN):].lstrip("\r\n")
                    state, advanced = "thinking", True
                else:
                    tail = _hold_back(buf, _THINK_OPEN)
                    buf = buf[len(buf) - tail:] if tail else ""

            elif state == "thinking":
                if not thinking_started:
                    buf = buf.lstrip("\r\n")
                i = buf.find(_THINK_CLOSE)
                if i != -1:
                    head, buf = buf[:i], buf[i + len(_THINK_CLOSE):]
                    if head:
                        thinking_started = True
                        yield {"type": "thinking", "text": head}
                    state, advanced = "between", True
                else:
                    keep = len(buf) - _hold_back(buf, _THINK_CLOSE)
                    if keep > 0:
                        thinking_started = True
                        yield {"type": "thinking", "text": buf[:keep]}
                        buf = buf[keep:]

            elif state == "between":
                i = buf.find(_ANSWER_OPEN)
                if i != -1:
                    buf = buf[i + len(_ANSWER_OPEN):].lstrip("\n")
                    state, advanced = "answer", True

            elif state == "answer":
                if not answer_started:
                    buf = buf.lstrip("\r\n")
                i = buf.find(_ANSWER_CLOSE)
                if i != -1:
                    head = buf[:i]
                    if head:
                        answer_started = True
                        yield {"type": "answer", "text": head}
                    buf, state = "", "done"
                else:
                    keep = len(buf) - _hold_back(buf, _ANSWER_CLOSE)
                    if keep > 0:
                        answer_started = True
                        yield {"type": "answer", "text": buf[:keep]}
                        buf = buf[keep:]

    if state == "thinking":
        tail = buf if thinking_started else buf.lstrip("\r\n")
        if tail:
            yield {"type": "thinking", "text": tail}
    elif state == "answer":
        tail = buf if answer_started else buf.lstrip("\r\n")
        if tail:
            yield {"type": "answer", "text": tail}

    raw = "".join(raw_parts)
    thinking, answer = _parse_response(raw)
    tokens = (total_tokens + real_tokens) or (len(raw) // 4)
    yield {"type": "final", "thinking": thinking, "answer": answer,
           "tokens": tokens, "chunks": all_chunks}


def generate_title(first_message: str) -> str:
    global _title_llm
    if _title_llm is None:
        _title_llm = ChatTogether(
            model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
            api_key=os.environ["TOGETHER_API_KEY"],
            temperature=0.3,
            max_tokens=15,
        )
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Generate a concise chat title (3–6 words) for a legal research conversation based on the user's first message. Return ONLY the title — no quotes, no punctuation at the end."),
        ("human", "{message}"),
    ])
    title = (prompt | _title_llm | StrOutputParser()).invoke({"message": first_message})
    return title.strip().strip('"').strip("'")