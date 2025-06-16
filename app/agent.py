
from langchain_openai import ChatOpenAI
from langchain.agents import initialize_agent, AgentType
from app.tools import hybrid_product_search
from dotenv import load_dotenv; load_dotenv()
import os

llm = ChatOpenAI(model=os.getenv("MODEL_NAME", "gpt-4o"), temperature=0)
agent = initialize_agent(
    tools=[hybrid_product_search],
    llm=llm,
    agent=AgentType.OPENAI_FUNCTIONS,
)
