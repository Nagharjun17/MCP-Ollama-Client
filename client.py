import asyncio
import json
import os
from contextlib import AsyncExitStack
from typing import Dict, List

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI

# Load env variables for Ollama base URL and key
load_dotenv()

CONFIG_PATH = "config.json"


def dump_tool_content(contents):
    # Convert MCP response objects into plain dictionaries
    return [c.model_dump() for c in contents]


class MCPClient:
    def __init__(self, cfg_path: str = CONFIG_PATH):
        # Read settings from config.json
        with open(cfg_path, "r") as f:
            self.cfg = json.load(f)

        self.sessions: Dict[str, ClientSession] = {}
        self.tools: List[dict] = []
        self.exit_stack = AsyncExitStack()

        # LLM configuration
        llm_cfg = self.cfg.get("llm", {})
        self.llm_model = llm_cfg.get("model", "qwen3:14b")
        self.llm_temperature = llm_cfg.get("temperature", 0.7)
        self.llm_max_tokens = llm_cfg.get("max_tokens", 2048)

        # Set up OpenAI-compatible client pointing to local Ollama server
        self.llm = OpenAI(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            api_key=os.getenv("OLLAMA_API_KEY", "ollama"),  # dummy key
            timeout=120,
        )

    async def connect_servers(self):
        servers = self.cfg.get("mcpServers", {})
        if not servers:
            raise ValueError("No servers defined under 'mcpServers' in config.json")

        # Loop through each server and initialize it
        for name, spec in servers.items():
            print(f"🔌 Starting MCP server: {name}")
            params = StdioServerParameters(
                command=spec["command"],
                args=spec.get("args", []),
                env=spec.get("env"),
            )
            stdio, write = await self.exit_stack.enter_async_context(stdio_client(params))
            session = await self.exit_stack.enter_async_context(ClientSession(stdio, write))
            await session.initialize()
            self.sessions[name] = session

            # Register tools with server prefix
            tool_list = await session.list_tools()
            for t in tool_list.tools:
                self.tools.append({
                    "type": "function",
                    "function": {
                        "name": f"{name}.{t.name}",
                        "description": f"[{name}] {t.description}",
                        "parameters": t.inputSchema,
                    }
                })

        all_tool_names = [t["function"]["name"] for t in self.tools]
        print("🛠️  Aggregated tools:", all_tool_names)

    async def call_tool(self, tool_full_name: str, args: dict):
        server_name, tool_name = tool_full_name.split(".", 1)
        session = self.sessions[server_name]
        return await session.call_tool(tool_name, args)

    async def ask(self, user_query: str) -> str:
        messages = [{"role": "user", "content": user_query}]
        resp = self.llm.chat.completions.create(
            model=self.llm_model,
            temperature=self.llm_temperature,
            max_tokens=self.llm_max_tokens,
            messages=messages,
            tools=self.tools,
            tool_choice="auto",
        )
        return await self._loop(resp, messages)

    async def _loop(self, resp, messages):
        while True:
            msg = resp.choices[0].message
            if msg.tool_calls:
                for tool_call in msg.tool_calls:
                    args = json.loads(tool_call.function.arguments or "{}")
                    result = await self.call_tool(tool_call.function.name, args)

                    messages.append(msg.model_dump())
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(dump_tool_content(result.content)),
                    })

                # Rerun after tools execute
                resp = self.llm.chat.completions.create(
                    model=self.llm_model,
                    temperature=self.llm_temperature,
                    max_tokens=self.llm_max_tokens,
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto",
                )
                continue
            return msg.content

    async def aclose(self):
        await self.exit_stack.aclose()


async def main():
    client = MCPClient()
    await client.connect_servers()
    print("Type 'quit' to exit.")
    try:
        while True:
            user_input = input(">>> ").strip()
            if user_input.lower() == "quit":
                break
            try:
                reply = await client.ask(user_input)
                print(reply)
            except Exception as e:
                print("Error:", e)
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
