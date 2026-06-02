import logging
import os
import re

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
            model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
            api_key=os.environ["TOGETHER_API_KEY"],
            temperature=0,
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


def run(
    question: str,
    history: list[dict],
    context_chunks: list[dict] | None = None,
) -> tuple[str, str, list[dict], int]:
    """
    Returns (thinking, answer, sources, tokens_used).

    Uses assistant prefill (<thinking> as the last message) so the model is
    forced to start its response inside the thinking block — guaranteeing the
    chain-of-thought is always present.
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

    # Build message list directly so we can append the assistant prefill.
    # Passing an incomplete AIMessage as the last message tells Together AI
    # to continue generating from that point — guaranteeing <thinking> appears.
    messages = [
        SystemMessage(content=system),
        *lc_history,
        HumanMessage(content=question),
        AIMessage(content="<thinking>\n"),   # assistant prefill
    ]

    ai_msg = _get_llm().invoke(messages)

    # Reconstruct full raw text: the model continued from after "<thinking>\n"
    raw = "<thinking>\n" + (ai_msg.content or "")
    log.debug(f"[LLM] raw response ({len(raw)} chars): {raw[:300]!r}")

    usage       = getattr(ai_msg, "usage_metadata", None) or {}
    tokens_used = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    if not tokens_used:
        tokens_used = len(raw) // 4

    thinking, answer = _parse_response(raw)
    return thinking, answer, context_chunks or [], tokens_used


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
