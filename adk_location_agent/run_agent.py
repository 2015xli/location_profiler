import argparse
import asyncio
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from agent import root_agent
import os, sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def async_runner_init(user_id, session_id):
    session_service = InMemorySessionService()
    session = await session_service.get_session(
        app_name="location_agent", user_id=user_id, session_id=session_id
    )
    if not session:
        session = await session_service.create_session(
            app_name="location_agent", user_id=user_id
        )

    agent_instance = root_agent
    runner = Runner(agent=agent_instance, app_name="location_agent", session_service=session_service)

    return runner, session

async def async_runner_call(query, runner, user_id, session_id):
    content = types.Content(role="user", parts=[types.Part(text=query)])
    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
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

async def async_main(user_id, session_id, query):
    runner, session = await async_runner_init(user_id, session_id)

    if query:
        print(f"\n[User]: {query}")
        await async_runner_call(query, runner, user_id, session.id)

    while True:
        query =input("\n[User] ('quit' to exit): ")
        if query.lower() == 'quit' or query.lower() == 'exit':
            break
    await async_runner_call(query, runner, user_id, session.id)

    await runner.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", default="user_1")
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--query", default=None)
    args = parser.parse_args()
    try:
        asyncio.run(async_main(args.user_id, args.session_id, args.query))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
