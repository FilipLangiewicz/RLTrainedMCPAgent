# Tools

You can call these tools. Each line is one tool in JSON: the name, the description and the arguments.

{tools}

To call a tool, write one line in this format and stop:

<tool_call>{"name": "<tool name>", "arguments": {"<argument>": <value>}}</tool_call>

To call more than one tool, write one line for each call. The result of each call comes back in <tool_response></tool_response>. When the task is complete, answer without a tool call.
