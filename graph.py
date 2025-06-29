from langgraph.graph import StateGraph
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from typing import TypedDict
import os

class GraphState(TypedDict):
    input: str
    output: str

def process_input(state: GraphState,) -> GraphState:
    user_input = state["input"]

    # Define your custom prompt
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful medical assistant. Answer concisely and refer to the scientific findings and medical sources if you know any"),
        ("human", "{input}")
    ])

    # Initialize the OpenAI Chat model
    llm = ChatOpenAI(
        model="gpt-4.1",
        temperature=0.7,
        api_key=os.getenv("OPENAI_API_KEY")
    )

    # Format the prompt with user input
    messages = prompt.format_messages(input=user_input)

    # Invoke the model
    response = llm.invoke(messages)

    # Update the state with the model's response
    return {
        "input": user_input,
        "output": response.content
    }


# Define the LangGraph
graph_builder = StateGraph(GraphState)
graph_builder.add_node("process", process_input)
graph_builder.set_entry_point("process")
specialized_graph = graph_builder.compile()
