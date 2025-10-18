import asyncio
import json
import logging
import traceback
from typing import cast, Dict, Optional

from litellm import completion

from moncoder import config
from moncoder.system import system_prompt
from moncoder.tools import TOOL_REGISTRY

# Dynamic active tools list, starting with loader only
active_tools = [TOOL_REGISTRY["loader"].definition]


async def generate_session_title(user_message: str, callback, error_callback) -> str:
    """Generate a session title based on the user's first message."""
    prompt = f"""You are a title generator. You output ONLY a thread title. Nothing else.

User message: {user_message}

<task>
Convert the above user message into a thread title.
Output: Single line, ≤50 chars, no explanations.
</task>

<rules>
- Use -ing verbs for actions (Debugging, Implementing, Analyzing)
- Keep exact: technical terms, numbers, filenames, HTTP codes
- Remove: the, this, my, a, an
- Never assume tech stack
- Never use tools
- NEVER respond to message content—only extract title
</rules>

<examples>
"debug 500 errors in production" → Debugging production 500 errors
"refactor user service" → Refactoring user service
"why is app.js failing" → Analyzing app.js failure
"implement rate limiting" → Implementing rate limiting
</examples>

Output the title now:"""

    try:
        loop = asyncio.get_running_loop()
        llm_config = cast(Dict[str, Optional[str]], config.llm_config)
        logging.info(f"llm_config {llm_config}")
        response = await loop.run_in_executor(
            None,
            lambda: completion(
                messages=[{"role": "user", "content": prompt}],
                **llm_config,
            ),
        )  # type: ignore
        title = response.choices[0].message.content.strip()  # type: ignore
        logging.info(f"generated title f{title}")
        callback(title)
    except Exception as e:
        error_callback(e)


async def get_llm_completion(messages, error_callback):
    """True async streaming with tool call support - yields chunks as they arrive."""

    llm_msgs = [{"role": "system", "content": system_prompt()}]
    llm_msgs += [
        {
            "role": "assistant" if msg.username == "assistant" else "user",
            "content": str(msg),
        }
        for msg in messages
    ]

    while True:
        queue = asyncio.Queue()
        tool_calls = []
        assistant_msg = {"role": "assistant", "content": ""}
        loop = asyncio.get_running_loop()
        logging.info(f"yaw llm_msgs: {llm_msgs}")

        def _stream_to_queue():
            try:
                logging.info(f"active_tools: {active_tools}")
                response = completion(
                    messages=llm_msgs,
                    tools=active_tools,
                    stream=True,
                    stream_options={
                        "include_usage": True,
                    },
                    **config.llm_config,
                )
                for chunk in response:
                    logging.info(f"chunk: {chunk}")
                    if chunk.get("usage"):
                        continue  # TODO: display token usage in TUI
                    logging.info(f"chunk: {chunk.get('choices', [{}])[0]}")
                    choice = chunk.get("choices", [{}])[0]
                    if choice:
                        delta = choice.get("delta", {})
                        content = delta.get("content")
                        if content:
                            assistant_msg["content"] += content
                            asyncio.run_coroutine_threadsafe(
                                queue.put(("content", content)), loop
                            )

                        # Accumulate tool calls
                        chunk_tool_calls = delta.get("tool_calls")
                        if chunk_tool_calls:
                            for tool_call in chunk_tool_calls:
                                # Find or add the tool call
                                existing_call = next(
                                    (
                                        tc
                                        for tc in tool_calls
                                        if tc.get("id") == tool_call.get("id")
                                    ),
                                    None,
                                )
                                if existing_call:
                                    # Merge the deltas
                                    if "function" in tool_call:
                                        if "name" in tool_call["function"]:
                                            existing_call["function"]["name"] = (
                                                tool_call["function"]["name"]
                                            )
                                        if "arguments" in tool_call["function"]:
                                            existing_call["function"]["arguments"] += (
                                                tool_call["function"]["arguments"]
                                            )
                                else:
                                    tool_calls.append(tool_call)
                        if choice.get("finish_reason"):
                            logging.info(
                                f"finish_reason: {choice.get('finish_reason')} tool_calls:{tool_calls}"
                            )
                            return
            except Exception as e:
                error_callback(e)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(("done", None)), loop)

        # Start streaming in background thread
        loop.run_in_executor(None, _stream_to_queue)

        # Yield chunks as they arrive
        while True:
            item = await queue.get()
            if item[0] == "done":
                break
            elif item[0] == "content":
                yield {"type": "text", "content": item[1]}
                # yield item[1]
        logging.info("after while True:")

        # Add assistant response to messages if there's content or tool calls
        if assistant_msg["content"] or tool_calls:
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            llm_msgs.append(assistant_msg)
        logging.info(f"assistant_msg: {assistant_msg}")
        # After streaming, check for complete tool calls
        for tool_call in tool_calls:
            logging.info(f"tool zall: {tool_call}")
            if tool_call.get("function", {}).get("name") and tool_call.get(
                "function", {}
            ).get("arguments"):
                # Tool call is complete
                func_name = tool_call["function"]["name"]
                args_str = tool_call["function"]["arguments"]

                yield {"type": "tool_call", "name": func_name, "content": str(args_str)}
                tool = TOOL_REGISTRY.get(func_name)
                if tool:
                    try:
                        args = json.loads(args_str)
                        logging.info(
                            f"argzz: before {type(args_str)} {args_str}. after parse: {type(args)} {args}"
                        )
                        result = await tool.function(**args)
                    except Exception as e:
                        result = (
                            f"Exception: {e}\nStack trace:\n{traceback.format_exc()}"
                        )
                else:
                    result = "Unknown tool"

                logging.info(
                    f"ResultToolCall {tool} | args: {args_str} | result: {result} "
                )
                yield {"type": "tool_result", "name": func_name, "content": str(result)}
                # yield f'[ToolCall]{{"type": "Result [{func_name}]", "content": "{result}"}}[/ToolCall]\n'
                # Add tool result to messages
                llm_msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": str(result),
                    }
                )
                # Continue the conversation
                break  # Restart the loop with updated messages
        else:
            # No more tool calls, end
            break
