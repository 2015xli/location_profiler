import argparse
import asyncio
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from agent import root_agent
import os, sys
from contextlib import ExitStack

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def async_main(query, user_id, session_id):
    session_service = InMemorySessionService()
    session = await (session_service.get_session(
        app_name="location_agent", user_id=user_id, session_id=session_id
    ) if session_id else session_service.create_session(
        app_name="location_agent", user_id=user_id
    ))

    agent_instance = root_agent
    runner = Runner(agent=agent_instance, app_name="location_agent", session_service=session_service)

    content = types.Content(role="user", parts=[types.Part(text=query)])
    async for event in runner.run_async(user_id=user_id, session_id=session.id, new_message=content):
        calls = event.get_function_calls()
        if calls:
            for call in calls:
                tool_name = call.name
                arguments = call.args
                print(f"Agent calling tool: {tool_name}")
                print(f"    Arguments: {arguments}")

        if event.is_final_response():
            if event.content and event.content.parts:
                final_response_text = event.content.parts[0].text
            elif event.actions and event.actions.escalate: # Handle potential errors/escalations
                final_response_text = f"Agent escalated: {event.error_message or 'No specific message.'}"
            break # Stop processing events once the final response is found
        
    print(f"\n\u2728 Agent Response: {final_response_text}\n")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--user-id", default="user")
    parser.add_argument("--session-id", default=None)
    args = parser.parse_args()
    try:
        asyncio.run(async_main(args.query, args.user_id, args.session_id))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
