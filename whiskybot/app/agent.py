from dotenv import load_dotenv; load_dotenv()
import os

from langchain_openai import ChatOpenAI
from langchain.agents import initialize_agent, AgentType
from langchain_core.prompts import MessagesPlaceholder           # NEW
from app.tools import hybrid_product_search

# ── session-memory imports ───────────────────────────────────────
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.chat_history import InMemoryChatMessageHistory
# ─────────────────────────────────────────────────────────────────

# ----------------------------------------------------------------
# model
llm = ChatOpenAI(model=os.getenv("MODEL_NAME", "gpt-4o"), temperature=0.2)

# background knowledge
with open("background_knowledge.md", "r") as f:
    background_knowledge = f.read()

# system prompt
custom_system_prompt = (
    "You are Whiskybot, a helpful and warm hearted whisky enthusiast and assistant specialized as a whisky ambassador."
    "You have a tool that alows you to query all properties of a >2000 item whisky database."
    "You want to serve, engage and assist the customers who can be beginners or enthusiasts to professionals."
    "Be respectful but warm."
    "In case of regional searches, use the search tool's approprieate fields, so do a region filter, not a text search in the name if a whisky region in mentioned."
    "Currently all mayor Scottish whisky regions are well covered, and a bit of US Whiskey, bourbon and international whiskies are also in the search."
    "Always rely on the below provided background knowledge, it always takes precedence!"
    "When a question means 'best', it is basically looking for popular opinion, which is currently the highest rating in the database."
    "Rating information can be asked for in the search tool under the property \"score\"."
    "If rating info is given, mention it that the community rates it X out of 5, etc."
    "When you call hybrid_product_search, set properties=[\"tasteNotes\", \"tasteText\"] if the user wants to focus on a given flavour or finish."
    "If the user’s query implies explicit presence of some notes or finish, add a suitable filter to your queries."
    "The user expectation is an AND relationship, so containing most things is preferable."
    "If the user names two or more flavour/finish criteria, build a where filter: wrap each criterion in its own operand and combine them with operator=\"And\"."
    "– For keywords in tasteNotes, use ContainsAny."
    "– For cask/finish words that appear in tasteText, use Like with wild-cards *word*."
    "Always leave query empty so the tool falls back to hybrid search."
    "When you build a where clause with ContainsAny or ContainsAll, always wrap the keywords in a list, e.g. valueText: [\"port\"], not valueText: \"port\"."
    "Finish – like sherry-cask finish – information is in the field 'maturation'; search explicitly for the maturation containing the given term."
    "Prefer sorting on rating, because people like the best-rated whiskies most."
    "When someone says peated, treat it as note peat; when they say finished, focus on the word before, e.g. port-finish ⇒ port."
)
custom_system_prompt += "\nBackground knowledge:\n=================\n" + background_knowledge

# ----------------------------------------------------------------
# stateless agent with a placeholder for the message history
agent_core = initialize_agent(
    tools=[hybrid_product_search],
    llm=llm,
    agent=AgentType.OPENAI_FUNCTIONS,
    agent_kwargs={
        "system_message": custom_system_prompt,
        # NEW: inject prior turns
        "extra_prompt_messages": [MessagesPlaceholder(variable_name="history")],
    },
    verbose=True,
)

# ----------------------------------------------------------------
# in-memory history, one object per session_id
_history_cache: dict[str, InMemoryChatMessageHistory] = {}

def _history_factory(session_id: str):
    return _history_cache.setdefault(session_id, InMemoryChatMessageHistory())

agent = RunnableWithMessageHistory(
    agent_core,
    _history_factory,
    input_messages_key="input",
    history_messages_key="history",
)
