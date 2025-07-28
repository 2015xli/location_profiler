from fastmcp import Client
import asyncio
import pprint

SERVER_URL = "http://127.0.0.1:8000/mcp"
client = Client(SERVER_URL)

async def main():
    async with client: # Ensures proper connection lifecycle management
        await client.ping() 
        tools = await client.list_tools() 
        resources = await client.list_resources() 
        prompts = await client.list_prompts() 
        pprint.pprint(tools)
        pprint.pprint(resources)
        pprint.pprint(prompts)

        result = await client.call_tool("read_location_graph", {"include_edges": True})
        print("read_location_graph")
        pprint.pprint(result)
        result = await client.call_tool("read_location_or_transition", {"uri": "location:loc_home"})
        print("read_location_or_transition")
        pprint.pprint(result)
        result = await client.call_tool("read_location_or_transition", {"uri": "transition:loc_home->loc_work"})
        print("read_location_or_transition")
        pprint.pprint(result)
        result = await client.call_tool("top_locations", {"days": 7, "n": 5})
        print("top_locations")
        pprint.pprint(result)
        result = await client.call_tool("next_location", {"current_place": "loc_home", "top_k": 3})
        print("next_location")
        pprint.pprint(result)
        result = await client.call_tool("top_locations_weekday", {"weekday": 2, "n": 5})
        print("top_locations_weekday")
        pprint.pprint(result)
        result = await client.call_tool("top_routes_weekday", {"weekday": 3, "n": 5})
        print("top_routes_weekday")
        pprint.pprint(result)
                
asyncio.run(main())


