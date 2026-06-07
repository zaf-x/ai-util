"""
Agent - High-level AIBot + Tools wrapper

Exports:
    Agent
"""

__all__ = [
    "Agent",
]

from .tools import Tools
from .bot import AIBot

class Agent:
    """
    一个智能体的父类。
    """
    def __init__(self, bot: AIBot, tools: Tools):
        self.bot = bot
        self.tools = tools
    
    def send_msg(self, msg: str):
        return self.bot.send_msg_with_tools(msg, self.tools)
    
    def stream_msg(self, msg: str): # type: ignore
        yield from self.bot.stream_output(msg, self.tools.definitions(), self.tools.execute)
