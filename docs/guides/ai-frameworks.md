# AI Framework Integration

How to use ToolsConnector with every major AI framework. Each section is a complete, runnable example.

## OpenAI Function Calling

Full tool-use loop with GPT-4o.

```python
import json
from openai import OpenAI
from toolsconnector.serve import ToolKit

client = OpenAI()
kit = ToolKit(
    ["gmail", "slack"],
    credentials={"gmail": "ya29.token", "slack": "xoxb-token"},
)

messages = [{"role": "user", "content": "Summarize my 5 most recent unread emails"}]

response = client.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    tools=kit.to_openai_tools(),
)

# Process tool calls in a loop until the model is done
while response.choices[0].message.tool_calls:
    messages.append(response.choices[0].message)

    for tool_call in response.choices[0].message.tool_calls:
        result = kit.execute(tool_call.function.name, tool_call.function.arguments)
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": json.dumps(result, default=str),
        })

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=kit.to_openai_tools(),
    )

print(response.choices[0].message.content)
```

## Anthropic Tool Use

Full tool-use loop with Claude.

```python
import json
import anthropic
from toolsconnector.serve import ToolKit

client = anthropic.Anthropic()
kit = ToolKit(
    ["jira", "slack"],
    credentials={"jira": "jira-api-token", "slack": "xoxb-token"},
)

messages = [{"role": "user", "content": "Create a bug ticket for the login timeout issue"}]

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=messages,
    tools=kit.to_anthropic_tools(),
)

# Process tool calls until stop_reason is "end_turn"
while response.stop_reason == "tool_use":
    # Collect assistant message
    messages.append({"role": "assistant", "content": response.content})

    # Execute each tool call and build result blocks
    tool_results = []
    for block in response.content:
        if block.type == "tool_use":
            result = kit.execute(block.name, block.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, default=str),
            })

    messages.append({"role": "user", "content": tool_results})

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=messages,
        tools=kit.to_anthropic_tools(),
    )

# Final text response
for block in response.content:
    if hasattr(block, "text"):
        print(block.text)
```

## Google Gemini

Generate Gemini-compatible function declarations.

```python
import google.generativeai as genai
from toolsconnector.serve import ToolKit

genai.configure(api_key="your-gemini-api-key")
kit = ToolKit(["gmail"], credentials={"gmail": "ya29.token"})

model = genai.GenerativeModel(
    "gemini-1.5-pro",
    tools=kit.to_gemini_tools(),
)

chat = model.start_chat()
response = chat.send_message("List my unread emails")

# Handle function calls from Gemini
for part in response.parts:
    if fn := part.function_call:
        result = kit.execute(fn.name, dict(fn.args))
        response = chat.send_message(
            genai.protos.Content(parts=[
                genai.protos.Part(function_response=genai.protos.FunctionResponse(
                    name=fn.name,
                    response={"result": result},
                ))
            ])
        )

print(response.text)
```

## LangChain

Convert ToolsConnector actions to LangChain tools.

```python
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from toolsconnector.serve import ToolKit

kit = ToolKit(
    ["github", "slack"],
    credentials={"github": "ghp_token", "slack": "xoxb-token"},
)

# Convert to LangChain tools
tools = kit.to_langchain_tools()

llm = ChatOpenAI(model="gpt-4o")
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant with access to GitHub and Slack."),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

result = executor.invoke({"input": "List open issues in myorg/myrepo"})
print(result["output"])
```

## CrewAI

Use ToolsConnector actions as CrewAI tools.

```python
from crewai import Agent, Task, Crew
from toolsconnector.serve import ToolKit

kit = ToolKit(
    ["github", "jira"],
    credentials={"github": "ghp_token", "jira": "jira-token"},
)

developer = Agent(
    role="Developer",
    goal="Triage and organize incoming bug reports",
    backstory="You are a senior developer responsible for bug triage.",
    tools=kit.to_crewai_tools(),
)

triage_task = Task(
    description="Review the 10 most recent GitHub issues and create Jira tickets for bugs",
    expected_output="A summary of created Jira tickets",
    agent=developer,
)

crew = Crew(agents=[developer], tasks=[triage_task], verbose=True)
result = crew.kickoff()
print(result)
```

## Direct Function Calling (Manual)

When you are not using a framework, call `kit.execute()` directly with the action name and parameter dict.

```python
from toolsconnector.serve import ToolKit

kit = ToolKit(["github"], credentials={"github": "ghp_token"})

# Sync
issues = kit.execute("github_list_issues", {
    "owner": "myorg",
    "repo": "myproject",
    "state": "open",
})

# Async
import asyncio

async def main():
    issues = await kit.aexecute("github_list_issues", {
        "owner": "myorg",
        "repo": "myproject",
        "state": "open",
    })
    return issues

asyncio.run(main())
```

## Schema Format Differences

Each AI provider expects a slightly different schema format. ToolsConnector generates the correct format for each from the same `@action` metadata.

| Method | Output Format | Key Differences |
|--------|--------------|-----------------|
| `to_openai_tools()` | `list[dict]` | Wraps schema in `{"type": "function", "function": {...}}` |
| `to_anthropic_tools()` | `list[dict]` | Uses `input_schema` key, flat structure |
| `to_gemini_tools()` | `list[dict]` | Google's `FunctionDeclaration` format |
| `to_langchain_tools()` | `list[Tool]` | Returns LangChain `StructuredTool` instances |
| `to_crewai_tools()` | `list[Tool]` | Returns CrewAI-compatible tool instances |

All schemas are generated from the same source: the `@action` decorator's parsed type hints and docstrings. Changing a connector's type signature automatically updates every schema format.
