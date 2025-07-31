from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams, MCPToolset
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types # For creating response content
from typing import Optional
from pprint import pprint

mcp_url = "http://127.0.0.1:8000/mcp"


def agent_guardrail(
    callback_context: CallbackContext, llm_request: LlmRequest) -> Optional[LlmResponse]:

    agent_name = callback_context.agent_name # Get the name of the agent whose model call is being intercepted
    if llm_request.contents:
        content = llm_request.contents[-1]
        if content.role == "user" and content.parts[0].text:
            if "shit" in content.parts[0].text.lower():
                print(f"{agent_name} Guardrail triggered. Here is the conversation so far:")
                for content in llm_request.contents:
                    pprint(content)

                return LlmResponse(
                    content=types.Content(
                        role="assistant", 
                        parts=[types.Part(text="I'm sorry, but I can't assist with that.")]
                    )
                )

    return None 

def sync_agent(): 
    connection_params = StreamableHTTPConnectionParams(url=mcp_url)
    toolset = MCPToolset(connection_params=connection_params)

    model = LiteLlm(model="deepseek/deepseek-chat")
    return LlmAgent(
        model=model,
        name="Location_Agent",
        instruction=(
            "You are a helpful assistant that answers questions about a user's "
            "historical location data and help to predict future locations. "
            "Use the provided tools to improve the accuracy of your answer."
        ),
        tools=[toolset],
        output_key="last_response",
        before_model_callback=agent_guardrail,
    )

root_agent = sync_agent()
