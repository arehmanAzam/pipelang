from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.types import Command
from typing import Literal,TypedDict,Dict
import os
from graph import specialized_graph
# Define the routing prompt
routing_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a supervisor agent that routes tasks to specialized agents. If the user asks for special medical advice, just give response/output of 'specialized_graph' otherwise give only 'other_agent' "),
    ("human", "{input}")
])

# Define the routing model
routing_model = ChatOpenAI(model="gpt-4.1", temperature=0.7,api_key=os.getenv("OPENAI_API_KEY"))

# Define possible routes
class RouteResponse(TypedDict):
    next: Literal["specialized_graph", "other_agent", "END"]

# Supervisor function
def supervisor_node(state: Dict) -> Dict:
    global routing_prompt,routing_model
    user_input = state.get("input", "")
    chat_history = state.get("chat_history", [])
    
    # Generate routing decision
    messages = routing_prompt.format_messages(input=user_input)
    response = routing_model.invoke(messages)
    route = response.content.strip().lower()  # Extract the route from the model's response
    print(route)
    # Route to the appropriate agent
    if route == "specialized_graph":
        output = specialized_graph.invoke({"input": state["input"], "output": ""})
        print(output["output"])
        return {"output": output["output"]} 
    # elif route == "other_agent":
        # Implement other_agent invocation
        #  return {"output": "Other agent invoked."}
    else:
        return {"output": "What do you want ?"}
