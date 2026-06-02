import logging
import os
import re
from typing import Generator

from langchain_together import ChatTogether
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are LoRAai, a legal research AI specialising in Australian and international law. \
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
- Flag when a matter requires professional legal advice
- If retrieved document excerpts are provided, cite them as **(filename, p.X)** — no emojis in citations
- Do NOT use 📄 or any emoji as footnote or citation markers — citations are plain text only
- Do NOT use `<sub>`, `<sup>`, or HTML tags in your response

## Mandatory output format
You MUST structure every response exactly as shown below — no exceptions:

<thinking>
[Your step-by-step legal reasoning: identify the question, relevant law, jurisdiction, analysis, uncertainties]
</thinking>
<answer>
[Your complete, well-formatted Markdown answer]
</answer>"""

_llm = None
_title_llm = None


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

    system = SYSTEM_PROMPT
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


def run(
    question: str,
    history: list[dict],
    context_chunks: list[dict] | None = None,
    attachment_text: str = "",
    attachment_name: str = "",
) -> tuple[str, str, list[dict], int]:
    """
    Returns (thinking, answer, sources, tokens_used).

    Non-streaming variant — used for background tasks. The live chat endpoint
    uses stream_response() instead.
    """
    messages = _build_messages(question, history, context_chunks, attachment_text, attachment_name)
    ai_msg = _get_llm().invoke(messages)

    raw = ai_msg.content or ""
    log.debug(f"[LLM] raw response ({len(raw)} chars): {raw[:300]!r}")

    usage       = getattr(ai_msg, "usage_metadata", None) or {}
    tokens_used = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    if not tokens_used:
        tokens_used = len(raw) // 4

    thinking, answer = _parse_response(raw)
    return thinking, answer, context_chunks or [], tokens_used


def stream_response(
    question: str,
    history: list[dict],
    context_chunks: list[dict] | None = None,
    attachment_text: str = "",
    attachment_name: str = "",
) -> Generator[dict, None, None]:
    """
    Stream the model response as it is generated, splitting the <thinking> and
    <answer> sections on the fly.

    Yields event dicts:
      {"type": "thinking", "text": <delta>}  — reasoning tokens, as they arrive
      {"type": "answer",   "text": <delta>}  — answer tokens, as they arrive
      {"type": "final", "thinking": str, "answer": str, "tokens": int}
            — emitted once at the end with the authoritative parsed sections
              (so the caller can persist clean text) and the token count.

    The XML tags are stripped from the deltas and never split across events,
    even when a tag straddles two stream chunks.
    """
    messages = _build_messages(question, history, context_chunks, attachment_text, attachment_name)

    state      = "open"              # open → thinking → between → answer → done
    buf        = ""
    raw_parts  = []                  # full model output, for the final parse
    real_tokens = 0
    thinking_started = False         # to trim newline(s) right after <thinking>
    answer_started   = False         # to trim newline(s) right after <answer>

    for chunk in _get_llm().stream(messages):
        # Usage metadata rides along on the final chunk (stream_usage=True).
        usage = getattr(chunk, "usage_metadata", None)
        if usage:
            real_tokens = (usage.get("input_tokens", 0) or 0) + \
                          (usage.get("output_tokens", 0) or 0)

        delta = chunk.content or ""
        if not delta:
            continue
        raw_parts.append(delta)
        buf += delta

        # One chunk can cross multiple section boundaries, so loop until stable.
        advanced = True
        while advanced:
            advanced = False

            if state == "open":
                # Discard everything up to and including the opening <thinking>.
                i = buf.find(_THINK_OPEN)
                if i != -1:
                    buf = buf[i + len(_THINK_OPEN):].lstrip("\r\n")
                    state, advanced = "thinking", True
                else:
                    # Hold a possible partial "<thinking>" tail; drop any preamble.
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
                # Discard everything up to and including <answer>, plus the
                # newline that follows it. Wait for more text if not seen yet.
                i = buf.find(_ANSWER_OPEN)
                if i != -1:
                    buf = buf[i + len(_ANSWER_OPEN):].lstrip("\n")
                    state, advanced = "answer", True

            elif state == "answer":
                # Trim the newline(s) that follow <answer> before real content —
                # they may arrive in a later chunk than the tag itself.
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

            # state == "done": ignore any trailing content after </answer>

    # Flush any held-back tail (model stopped before closing its tags).
    if state == "thinking":
        tail = buf if thinking_started else buf.lstrip("\r\n")
        if tail:
            yield {"type": "thinking", "text": tail}
    elif state == "answer":
        tail = buf if answer_started else buf.lstrip("\r\n")
        if tail:
            yield {"type": "answer", "text": tail}

    # Authoritative final parse from the full reconstructed text. This corrects
    # any format drift in the live deltas and yields the clean text to persist.
    raw = "".join(raw_parts)
    thinking, answer = _parse_response(raw)
    tokens = real_tokens or (len(raw) // 4)
    yield {"type": "final", "thinking": thinking, "answer": answer, "tokens": tokens}


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
