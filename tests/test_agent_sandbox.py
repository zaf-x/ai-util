from ai_util import Agent, AIBot, Sandbox, Tools
from secret import API_ENDPOINT, API_KEY, MODEL

bot = AIBot(api_key=API_KEY, model=MODEL, temperature=1, base_url=API_ENDPOINT)

tools = Tools()
sandbox = Sandbox("/home/baosh")
sandbox.register_tools(tools)

agent = Agent(bot, tools)

print("TOOLS: ")
print(agent.tools.definitions())

print("USER: 你有哪些工具")
print(agent.send_msg("你有哪些工具")["content"])
