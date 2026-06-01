import os

from langchain_together import ChatTogether
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

_chain = None


def _get_chain():
    global _chain
    if _chain is None:
        llm = ChatTogether(
            model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
            api_key=os.environ["TOGETHER_API_KEY"],
            temperature=0.4,
            max_tokens=200,
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a legal research query expansion assistant.
Given a legal question, generate exactly 3 alternative search queries that will retrieve different but relevant information.
Each alternative should use different legal terminology, focus on a specific sub-aspect, or approach from a different angle.
Keep each query under 20 words.
Return ONLY the 3 queries, one per line, no numbering or extra text."""),
            ("human", "{question}"),
        ])
        _chain = prompt | llm | StrOutputParser()
    return _chain


def expand(question: str) -> list[str]:
    """Returns the original question plus up to 3 expanded variations."""
    try:
        raw = _get_chain().invoke({"question": question})
        variations = [q.strip() for q in raw.strip().splitlines() if q.strip()][:3]
        return [question] + variations
    except Exception:
        return [question]
