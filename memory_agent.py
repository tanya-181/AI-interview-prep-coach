import atexit
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

PROJECT_ROOT = Path(__file__).resolve().parent
GROQ_MODEL = "openai/gpt-oss-20b"

os.environ.setdefault("MEMO_DIR", str(PROJECT_ROOT / ".mem0"))
os.environ.setdefault("MEMO_TELEMETRY", "FALSE")
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

from mem0 import Memory


mem0_config = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "collection_name": "mem0_interview_prep",
            "path": "./qdrant_data",
            "embedding_model_dims": 768,
        },
    },
    "llm": {
        "provider": "groq",
        "config": {
            "model": "openai/gpt-oss-20b",
            "temperature": 0.1,
        },
    },
    "embedder": {
        "provider": "gemini",
        "config": {
            "model": "gemini-embedding-001",
            "embedding_dims": 768
        },
    },
}


SYSTEM_PROMPT = """You are an AI interview prep coach. Use the following memories \
about the candidate to personalize your questions, avoid repeating covered topics, \
and focus on their weak areas and target role.

Candidate memories:
{memories}

Based on this, either (a) ask the next interview question tailored to them, \
or (b) evaluate their answer and give concise feedback. Be specific and concise."""


CHAIN = (
    ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "{question}"),
        ]
    )
    | ChatGroq(model="openai/gpt-oss-20b", temperature=0.3)
    | StrOutputParser()
)


try:
    MEMORY = Memory.from_config(mem0_config)
    MEMORY_INIT_ERROR = None
except Exception as exc:
    MEMORY = None
    MEMORY_INIT_ERROR = exc


def _format_memories(search_results) -> str:
    items = search_results.get("results", []) if isinstance(search_results, dict) else search_results
    memories = [
        f"- {item['memory']}"
        for item in items
        if isinstance(item, dict) and item.get("memory")
    ]
    return "\n".join(memories) if memories else "(no prior memories yet)"


def _close_memory() -> None:
    if MEMORY is None:
        return

    try:
        MEMORY.vector_store.client.close()
    except Exception:
        pass

    try:
        MEMORY.close()
    except Exception:
        pass


atexit.register(_close_memory)



def chat(user_id: str, user_message: str) -> str:
    """Fetch relevant memories, call the LLM, then persist the exchange."""
    if MEMORY is None:
        return f"Setup error: could not initialize Mem0. {MEMORY_INIT_ERROR}"

    try:
        search_results = MEMORY.search(query=user_message, filters={"user_id" : user_id})
        reply = CHAIN.invoke(
            {
                "memories": _format_memories(search_results),
                "question": user_message,
            }
        )
        MEMORY.add(
            [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": reply},
            ],
            user_id=user_id,
            infer=False
        )
        return reply
    except Exception as exc:
        return f"Setup error: {exc}"


def get_all_memories(user_id: str):
        if MEMORY is None:
           return {"error": str(MEMORY_INIT_ERROR), "results": []}

        try:
           return MEMORY.get_all(filters={"user_id": user_id})
        except Exception as exc:
           return {"error": str(exc), "results": []}