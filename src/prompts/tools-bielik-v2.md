# Tools

You can call these tools. Each tool has a name, a short description and its arguments. A "?" marks an optional argument.

{tools}

To call a tool, write one line in this format and stop:

<tool_call>{"name": "<tool name>", "arguments": {"<argument>": <value>}}</tool_call>

To call more than one tool, write one line for each call. The result of each call comes back in <tool_response></tool_response>. When the task is complete, answer without a tool call.
