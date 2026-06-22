from netfree_unstrict_ssl import unstrict_ssl
unstrict_ssl() 
import asyncio
import json
import os
from contextlib import AsyncExitStack
from typing import Any

import openai

from client import MCPClient
from dotenv import load_dotenv

load_dotenv()


class ChatHost:
    def __init__(self):
        self.mcp_clients: list[MCPClient] = [MCPClient("./weather_USA.py"), MCPClient("./weather_Israel.py")]
        self.tool_clients: dict[str, tuple[MCPClient, str]] = {}
        self.clients_connected = False
        self.exit_stack = AsyncExitStack()

        self.openai = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def connect_mcp_clients(self):
        """Connect all configured MCP clients once."""
        if self.clients_connected:
            return

        for client in self.mcp_clients:
            if client.session is None:
                await client.connect_to_server()

        if not self.mcp_clients:
            raise RuntimeError("No MCP clients are connected")

        self.clients_connected = True

    async def get_available_tools(self) -> list[dict[str, Any]]:
        """Collect tools from all MCP clients and map them back to their owner."""
        await self.connect_mcp_clients()
        self.tool_clients = {}
        available_tools: list[dict[str, Any]] = []

        for client in self.mcp_clients:
            if client.session is None:
                print(f"Warning: MCP client {client.client_name} is not connected, skipping")
                continue

            try:
                response = await client.session.list_tools()
                for tool in response.tools:
                    exposed_name = f"{client.client_name}__{tool.name}"
                    if exposed_name in self.tool_clients:
                        raise RuntimeError(f"Duplicate tool name detected: {exposed_name}")

                    self.tool_clients[exposed_name] = (client, tool.name)
                    available_tools.append(
                        {
                            "name": exposed_name,
                            "description": f"[{client.client_name}] {tool.description}",
                            "input_schema": tool.inputSchema,
                        }
                    )
            except Exception as e:
                print(f"Warning: Failed to get tools from {client.client_name}: {str(e)}")
                continue

        if not available_tools:
            raise RuntimeError("No tools available from any MCP client")

        return available_tools

    def _build_openai_tools(self, available_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for tool in available_tools:
            parameters = tool["input_schema"] or {"type": "object", "properties": {}}
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": parameters,
                    },
                }
            )
        return tools

    @staticmethod
    def _extract_tool_text(content: Any) -> str:
        """Flatten an MCP tool result's content into a string for the model."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [block.text for block in content if hasattr(block, "text")]
            if parts:
                return "\n".join(parts)
        return json.dumps(content, default=str)

    async def process_query(self, query: str) -> str:
        """Process a query using OpenAI and available tools"""
        messages = [{"role": "user", "content": query}]
        available_tools = await self.get_available_tools()
        tools = self._build_openai_tools(available_tools)
        final_text: list[str] = []

        while True:
            response = self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=tools,
                max_tokens=1000,
                temperature=0,
            )

            assistant_message = response.choices[0].message
            if assistant_message is None:
                raise RuntimeError("OpenAI returned an empty assistant message")

            tool_calls = assistant_message.tool_calls
            assistant_content = assistant_message.content

            if assistant_content:
                final_text.append(assistant_content)

            if not tool_calls:
                break

            # Record the assistant turn (with its tool calls) before answering them.
            messages.append(assistant_message.model_dump(exclude_none=True))

            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                if tool_name not in self.tool_clients:
                    raise RuntimeError(f"Unknown tool requested by model: {tool_name}")

                arguments_text = tool_call.function.arguments or "{}"
                try:
                    tool_args = json.loads(arguments_text)
                except json.JSONDecodeError:
                    tool_args = {"raw": arguments_text}

                client, original_tool_name = self.tool_clients[tool_name]
                if client.session is None:
                    raise RuntimeError(f"MCP client {client.client_name} is not connected")

                result = await client.session.call_tool(original_tool_name, tool_args)
                tool_response = self._extract_tool_text(result.content)
                final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_response,
                })

        return "\n".join(final_text)
    
    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")
        
        while True:
            try:
                query = input("\nQuery: ").strip()
                
                if query.lower() == 'quit':
                    break
                
                response = await self.process_query(query)
                print("\n" + response)
                
            except Exception as e:
                print(f"\nchat_loop Error: {str(e)}")
                
    async def cleanup(self):
        """Clean up resources"""
        for client in reversed(self.mcp_clients):
            await client.cleanup()
        await self.exit_stack.aclose()
        
        
async def main():
    host = ChatHost()
    try:
        await host.chat_loop()
    finally:
        await host.cleanup()
        
if __name__ == "__main__":
    asyncio.run(main())
