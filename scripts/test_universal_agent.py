import asyncio
import os
import sys

# Ensure the project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from aki.agent.base import UniversalAgent
from aki.agent.roles import OrchestratorRole
from aki.agent.state import AgentContext
from aki.models.types.llm import LLMInterface
from aki.models.base import ModelResponse
from aki.tools.read_skill import ReadSkillTool
from aki.tools.delegate_to_worker import DelegateToWorkerTool


class MockLLM(LLMInterface):
    """A mock LLM that predictably responds to test the Orchestrator."""

    async def chat(self, messages: list[dict], **kwargs) -> ModelResponse:
        # Check what the agent is currently seeing
        prompt = messages[-1]["content"] if messages else ""

        if "What is your next action?" in prompt and "read_skill" not in prompt:
            # First turn: The Orchestrator should realize it needs to look up a skill
            return ModelResponse(
                content='{"type": "invoke_tool", "target": "read_skill", "params": {"skill_name": "subtitle-translation"}, "reasoning": "I need to look up how to translate this."}',
                model="mock-llm",
            )
        elif "delegate_to_worker" not in prompt and "MediaExtractor" not in prompt:
            # Second turn: Delegate to worker
            return ModelResponse(
                content='{"type": "invoke_tool", "target": "delegate_to_worker", "params": {"worker_role": "MediaExtractor", "task_instruction": "Extract and transcribe.", "context_data": {}}, "reasoning": "Delegating to media extractor."}',
                model="mock-llm",
            )
        else:
            # Final turn: Complete
            return ModelResponse(
                content='{"type": "complete", "params": {"result": "Task delegated and finalized successfully."}, "reasoning": "We are done."}',
                model="mock-llm",
            )

    async def invoke(self, **kwargs) -> ModelResponse:
        return await self.chat(kwargs.get("messages", []))

    async def stream(self, **kwargs):
        pass


async def main():
    print("Testing UniversalAgent initialization...")

    role = OrchestratorRole()
    context = AgentContext(task_id="test-123")

    # Needs a config object to initialize LLMInterface properly
    from aki.models.base import ModelConfig

    config = ModelConfig(provider="mock", model_name="mock-llm")
    llm = MockLLM(config)

    read_skill_tool = ReadSkillTool()
    delegate_tool = DelegateToWorkerTool(context=context, llm=llm)

    agent = UniversalAgent(
        role=role, context=context, llm=llm, tools=[read_skill_tool, delegate_tool]
    )

    print(f"Agent created with Persona: {agent.role.persona[:50]}...")
    print(f"Available tools: {[t.name for t in agent.tools]}")

    # Run a mock task
    result = await agent.run("Translate test.mp4 to Japanese")

    print(f"\\nAgent Result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
