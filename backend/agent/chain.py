import os
import re

from langchain_together import ChatTogether
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

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

## Format your response EXACTLY like this:
<thinking>
[Step-by-step legal reasoning: identify the question, relevant law, jurisdiction, analysis, uncertainties]
</thinking>
<answer>
[Your complete, well-formatted Markdown answer]
</answer>


"""

_llm = None
_title_chain = None


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
    """Extract <thinking> and <answer> blocks. Falls back gracefully if tags are missing."""
    thinking_match = re.search(r"<thinking>(.*?)</thinking>", raw, re.DOTALL)
    answer_match   = re.search(r"<answer>(.*?)</answer>",     raw, re.DOTALL)

    thinking = thinking_match.group(1).strip() if thinking_match else ""
    answer   = answer_match.group(1).strip()   if answer_match   else ""

    # If the model produced empty <answer> tags, strip the structural tags and
    # use whatever text remains (the model put its answer outside the tags).
    if not answer:
        cleaned = re.sub(r"<thinking>.*?</thinking>", "", raw, flags=re.DOTALL)
        cleaned = re.sub(r"</?answer>", "", cleaned).strip()
        answer  = cleaned or thinking or raw.strip()

    return thinking, answer


def run(
    question: str,
    history: list[dict],
    context_chunks: list[dict] | None = None,
) -> tuple[str, str, list[dict], int]:
    """
    Returns (thinking, answer, sources, tokens_used).
    tokens_used is the total input+output token count reported by the API.
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

    prompt = ChatPromptTemplate.from_messages([
        ("system", system),
        MessagesPlaceholder("history"),
        ("human", "{question}"),
    ])

    # Invoke without StrOutputParser so we keep the AIMessage (for usage metadata)
    ai_msg = (prompt | _get_llm()).invoke(
        {"question": question, "history": lc_history}
    )
    raw = ai_msg.content

    # Together AI returns usage in usage_metadata; fall back to char estimate
    usage       = getattr(ai_msg, "usage_metadata", None) or {}
    tokens_used = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    if not tokens_used:
        tokens_used = (len(question) + len(raw)) // 4

    thinking, answer = _parse_response(raw)
    return thinking, answer, context_chunks or [], tokens_used


def _get_title_chain():
    global _title_chain
    if _title_chain is None:
        llm = ChatTogether(
            model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
            api_key=os.environ["TOGETHER_API_KEY"],
            temperature=0.3,
            max_tokens=15,
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Generate a concise chat title (3–6 words) for a legal research conversation based on the user's first message. Return ONLY the title — no quotes, no punctuation at the end."),
            ("human", "{message}"),
        ])
        _title_chain = prompt | llm | StrOutputParser()
    return _title_chain


def generate_title(first_message: str) -> str:
    title = _get_title_chain().invoke({"message": first_message})
    return title.strip().strip('"').strip("'")
