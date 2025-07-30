from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams, MCPToolset
from contextlib import ExitStack

mcp_url = "http://127.0.0.1:8000/mcp"

def sync_agent(): 
    connection_params = StreamableHTTPConnectionParams(url=mcp_url)
    toolset = MCPToolset(connection_params=connection_params)

    model = LiteLlm(model="deepseek/deepseek-chat")
    return LlmAgent(
        model=model,
        name="assistant",
        instruction=(
            "You are a helpful assistant that answers questions about a user's "
            "historical location data and help to predict future locations. "
            "Use the provided tools to improve the accuracy of your answer."
        ),
        tools=[toolset],
        output_key="last_response"
    )

root_agent = sync_agent()
