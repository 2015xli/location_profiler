"""Location Profile Agent using LiteLLM (DeepSeek).

This agent demonstrates how to use LiteLLM to query a running *Location Graph MCP server* 
and answer free-form questions about a user's mobility habits.

Prerequisites
-------------
1. MCP server must be running – see `mcp_location_server.py` in the project root.
2. Install dependencies:

   ```bash
   pip install fastmcp litellm
   ```
   Set your DeepSeek API key:

   ```bash
   export DEEPSEEK_API_KEY="<your-key>"
   ```

Usage
-----
Run interactively from the project root:

```bash
python -m experiments.api_location_agent --query "Where do I usually go on Fridays?"
```

Or with a custom MCP server URL:

```bash
python -m experiments.api_location_agent --mcp http://your-server:8000/mcp --query "Your question"
```

The agent will choose the appropriate MCP tool(s) and return a natural language response.
"""
from __future__ import annotations

import argparse
import asyncio
from typing import Any, Dict
import os
from fastmcp import Client as MCPClient  # SDK for calling MCP tools
import sys
import os

# Add project root to path to allow importing from other modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import litellm

# ---------------------------------------------------------------------------
# LLM helper (LiteLLM + DeepSeek)
# ---------------------------------------------------------------------------

def call_llm(system_prompt: str, user_prompt: str) -> str:
    """Synchronous convenience wrapper around LiteLLM completion call."""
    response = litellm.completion(
        model="deepseek/deepseek-chat",
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        stream=False,
    )
    return response["choices"][0]["message"]["content"].strip()


class LocationProfileAgent:
    """An agent that answers questions using MCP location-graph tools via direct LLM API calls."""

    def __init__(self, mcp_url: str):
        self.client = MCPClient(mcp_url)

    async def _choose_tool_and_params(self, question: str) -> Dict[str, Any]:
        """Simple heuristic mapping questions to MCP tools.

        This is a basic implementation that maps specific question patterns to MCP tools.
        In a production environment, you might want to use an LLM with the tool schema
        from `await self.client.list_tools()` for more sophisticated routing.
        """
        lower_q = question.lower()
        if "next" in lower_q and "where" in lower_q:
            return {"tool": "next_location", "args": {"current_place": "loc_home", "top_k": 3}}
        if "friday" in lower_q or "weekday" in lower_q:
            # Friday == weekday 4
            return {"tool": "top_locations_weekday", "args": {"weekday": 4, "n": 5}}
        # Fallback: top locations overall
        return {"tool": "top_locations", "args": {"days": 30, "n": 5}}

    async def handle(self, task: str) -> str:
        """Answer *task* (user query) by selecting and calling an MCP tool."""
        async with self.client:
            tool_spec = await self._choose_tool_and_params(task)
            tool_name = tool_spec["tool"]
            args = tool_spec["args"]
            tool_result = await self.client.call_tool(tool_name, args)

        # Compose final answer with an LLM – pass both the question and tool result
        system_prompt = "You are a helpful assistant specialised in analysing a user's historical location data."
        user_prompt = (
            f"Question: {task}\n\n"
            f"Relevant data (JSON):\n{tool_result}\n\n"
            "Craft a concise, conversational answer that references the data where needed."
        )
        answer = call_llm(system_prompt, user_prompt)
        return answer


# ---------------------------------------------------------------------------
# Command-line entry-point
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Query the Location Profile Agent via CLI")
    parser.add_argument(
        "--mcp", 
        default="http://127.0.0.1:8000/mcp", 
        help="Base URL of the MCP server (default: http://127.0.0.1:8000/mcp)"
    )
    parser.add_argument(
        "--query", 
        required=True, 
        help="Natural language question to ask about your location history"
    )
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    
    try:
        agent = LocationProfileAgent(args.mcp)
        answer = asyncio.run(agent.handle(args.query))
        print("\n\u2728", answer, "\n")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        print("\nMake sure the MCP server is running and accessible at:", args.mcp, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
