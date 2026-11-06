# Tools

You can call these tools. The list uses the JSON format of a function definition.

{tools}

To call a tool, write one line in this format and stop:

<tool_call>{"name": "<tool name>", "arguments": {"<argument>": <value>}}</tool_call>

To call more than one tool, write one line for each call. The result of each call comes back in <tool_response></tool_response>. When the task is complete, answer without a tool call.

The user message has the conversation so far in <user> and <assistant> blocks. Write only the next assistant turn. Do not write a <tool_response> block.
