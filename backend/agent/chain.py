import os

from langchain_together import ChatTogether
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

SYSTEM_PROMPT = """You are a legal research assistant specialising in Australian and international law. \
You help lawyers, law students, and individuals understand legal concepts, research case law, \
and analyse statutes.

When answering:
- Cite specific statutes, cases, or legal principles where relevant (e.g. "Fair Work Act 2009 (Cth) s 385")
- State the jurisdiction your answer applies to
- Flag when a question requires professional legal advice
- Be precise with legal terminology
- If you are unsure, say so rather than guessing"""

_chain = None


def get_chain():
    global _chain
    if _chain is None:
        llm = ChatTogether(
            model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
            api_key=os.environ["TOGETHER_API_KEY"],
            temperature=0,
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder("history"),
            ("human", "{question}"),
        ])
        _chain = prompt | llm | StrOutputParser()
    return _chain


def run(question: str, history: list[dict]) -> str:
    """
    history: prior messages as [{"role": "user"|"assistant", "content": str}, ...]
    Returns the assistant's reply as a plain string.
    """
    lc_history = []
    for msg in history:
        if msg["role"] == "user":
            lc_history.append(HumanMessage(content=msg["content"]))
        else:
            lc_history.append(AIMessage(content=msg["content"]))

    return get_chain().invoke({"question": question, "history": lc_history})
