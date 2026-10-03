import json
from typing import Any, Dict, List, Optional, Tuple

def normalize_gemini_schema(val: Any) -> Any:
    """Recursively converts uppercase Gemini schema types (STRING, OBJECT, etc.) to lowercase OpenAPI types."""
    if isinstance(val, dict):
        new_dict = {}
        for k, v in val.items():
            if k == "type" and isinstance(v, str):
                new_dict[k] = v.lower()
            else:
                new_dict[k] = normalize_gemini_schema(v)
        if new_dict.get("type") == "object" and "properties" not in new_dict:
            new_dict["properties"] = {}
        return new_dict
    elif isinstance(val, list):
        return [normalize_gemini_schema(item) for item in val]
    return val

def smart_compact_tool_response(name: str, content_str: str, args: Dict[str, Any]) -> str:
    """
    Intelligently compacts large tool responses in historical turns.
    Preserves exact file paths, line ranges, commands, cwd, and search results
    so the agent maintains full situational awareness without context bloat.
    """
    if len(content_str) < 500:
        return content_str

    import re
    lines = content_str.splitlines()
    total_lines = len(lines)

    # 1. view_file
    if name == "view_file":
        path = args.get("AbsolutePath") or args.get("path") or ""
        start_line = args.get("StartLine", 1)
        end_line = args.get("EndLine", total_lines)
        if total_lines > 10:
            head = "\n".join(lines[:3])
            tail = "\n".join(lines[-3:])
            hidden_count = total_lines - 6
            marker = f"\n... [Контекст оптимизирован: скрыто {hidden_count} строк кода. Полный файл доступен по пути: {path} (строки {start_line}-{end_line})] ...\n"
            return f"{head}\n{marker}\n{tail}"

    # 2. run_command
    elif name == "run_command":
        cmd = args.get("CommandLine") or ""
        cwd = args.get("Cwd") or ""
        if total_lines > 8:
            head = "\n".join(lines[:2])
            tail = "\n".join(lines[-2:])
            hidden_count = total_lines - 4
            marker = f"\n... [Контекст оптимизирован: скрыто {hidden_count} строк вывода. Выполненная команда: `{cmd}` в `{cwd}`] ...\n"
            return f"{head}\n{marker}\n{tail}"

    # 3. grep_search
    elif name == "grep_search":
        query = args.get("Query") or ""
        search_path = args.get("SearchPath") or ""
        files = re.findall(r'"Filename":\s*"([^"]+)"', content_str)
        unique_files = list(dict.fromkeys(files))
        if unique_files:
            file_summary = ", ".join(unique_files[:8])
            if len(unique_files) > 8:
                file_summary += f" и еще {len(unique_files) - 8} файлов"
            return f"[Контекст оптимизирован: поиск '{query}' в '{search_path}' нашел {len(files)} совпадений в: {file_summary}]"

    # 4. list_dir
    elif name == "list_dir":
        dir_path = args.get("DirectoryPath") or ""
        if total_lines > 10:
            head = "\n".join(lines[:3])
            tail = "\n".join(lines[-2:])
            hidden_count = total_lines - 5
            marker = f"\n... [Контекст оптимизирован: скрыто {hidden_count} строк листинга. Директория: {dir_path}] ...\n"
            return f"{head}\n{marker}\n{tail}"

    # 5. Generic fallback for large text outputs
    if total_lines > 8:
        head = "\n".join(lines[:2])
        tail = "\n".join(lines[-2:])
        hidden_count = total_lines - 4
        marker = f"\n... [Контекст оптимизирован: скрыто {hidden_count} строк вывода {name}] ...\n"
        return f"{head}\n{marker}\n{tail}"
    elif len(content_str) > 600:
        return content_str[:250] + f"\n... [Контекст оптимизирован: скрыто {len(content_str) - 500} символов вывода {name}] ...\n" + content_str[-250:]

    return content_str

def repair_json_string(s: str) -> Dict[str, Any]:
    """Attempts multiple strategies to parse or repair potentially truncated or malformed JSON."""
    if not s or not s.strip():
        return {}

    import re
    raw = s.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()

    # 1. Direct parse attempt
    try:
        res = json.loads(raw)
        if isinstance(res, dict):
            return res
    except Exception:
        pass

    # 2. Fix unescaped Windows backslashes: e.g. K:\Project -> K:\\Project
    fixed_slashes = re.sub(r'\\([^"\\/bfnrtu])', r'\\\\\1', raw)
    try:
        res = json.loads(fixed_slashes)
        if isinstance(res, dict):
            return res
    except Exception:
        pass

    # 3. Balance unclosed quotes and braces
    candidate = fixed_slashes
    unescaped_quotes = len(re.findall(r'(?<!\\)"', candidate))
    if unescaped_quotes % 2 != 0:
        candidate += '"'

    open_braces = candidate.count("{")
    close_braces = candidate.count("}")
    if open_braces > close_braces:
        candidate += "}" * (open_braces - close_braces)

    try:
        res = json.loads(candidate)
        if isinstance(res, dict):
            return res
    except Exception:
        pass

    # 4. Regex key-value extraction fallback
    extracted = {}
    pattern = r'"(\w+)"\s*:\s*("(?:[^"\\]|\\.)*"|\d+|true|false|null)'
    for match in re.finditer(pattern, raw):
        k, v = match.group(1), match.group(2)
        try:
            extracted[k] = json.loads(v)
        except Exception:
            extracted[k] = v.strip('"')

    return extracted

def is_tool_call_operable(tool_name: str, args: Dict[str, Any]) -> bool:
    """Verifies that mandatory operative arguments are present and non-empty."""
    if not isinstance(args, dict):
        return False
    if tool_name == "run_command":
        cmd = args.get("CommandLine") or ""
        return bool(isinstance(cmd, str) and cmd.strip())
    elif tool_name in ("view_file", "view_image"):
        path = args.get("AbsolutePath") or ""
        return bool(isinstance(path, str) and path.strip())
    elif tool_name in ("write_to_file", "replace_file_content"):
        path = args.get("TargetFile") or ""
        return bool(isinstance(path, str) and path.strip())
    elif tool_name == "search_web":
        q = args.get("query") or ""
        return bool(isinstance(q, str) and q.strip())
    elif tool_name == "read_url_content":
        u = args.get("Url") or ""
        return bool(isinstance(u, str) and u.strip())
    elif tool_name == "call_mcp_tool":
        server = args.get("ServerName") or ""
        tool = args.get("ToolName") or ""
        return bool(isinstance(server, str) and server.strip() and isinstance(tool, str) and tool.strip())
    elif tool_name == "send_message":
        rec = args.get("Recipient") or ""
        msg = args.get("Message") or ""
        return bool(isinstance(rec, str) and rec.strip() and isinstance(msg, str) and msg.strip())
    elif tool_name == "schedule":
        prompt = args.get("Prompt") or ""
        return bool(isinstance(prompt, str) and prompt.strip())
    return True

def extract_generation_params(gemini_request: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts temperature, max_tokens, and top_p from Gemini generationConfig."""
    cfg = gemini_request.get("generationConfig") or {}
    params = {}
    if "temperature" in cfg:
        try:
            params["temperature"] = float(cfg["temperature"])
        except (ValueError, TypeError):
            pass
    if "maxOutputTokens" in cfg:
        try:
            params["max_tokens"] = int(cfg["maxOutputTokens"])
        except (ValueError, TypeError):
            pass
    if "topP" in cfg:
        try:
            params["top_p"] = float(cfg["topP"])
        except (ValueError, TypeError):
            pass
    return params

def enforce_context_token_budget(messages: List[Dict[str, Any]], max_chars: int = 150000) -> List[Dict[str, Any]]:
    """
    Guarantees the prompt fits comfortably within the local engine context window (131k tokens).
    Preserves system message (index 0), first user request, and the most recent messages.
    Ensures slices do not orphan tool responses from assistant tool_calls.
    """
    if not messages:
        return messages

    def get_msg_len(m: Optional[Dict[str, Any]]) -> int:
        if not m:
            return 0
        c = m.get("content")
        if isinstance(c, str):
            return len(c)
        elif isinstance(c, list):
            return sum(len(x.get("text", "")) for x in c if isinstance(x, dict))
        return 0

    total_len = sum(get_msg_len(m) for m in messages)
    if total_len <= max_chars:
        return messages

    system_msg = messages[0] if messages[0].get("role") == "system" else None
    remaining_msgs = messages[1:] if system_msg else messages[:]

    # Find the original first user message to preserve the core goal
    first_user_msg = None
    for m in remaining_msgs:
        if m.get("role") == "user":
            first_user_msg = m
            break

    budget = max_chars - get_msg_len(system_msg)
    if first_user_msg:
        budget -= get_msg_len(first_user_msg)
    budget = max(budget, 20000)

    kept_rev = []
    current_len = 0

    for m in reversed(remaining_msgs):
        m_len = get_msg_len(m)
        if current_len + m_len > budget and len(kept_rev) >= 4:
            break
        kept_rev.append(m)
        current_len += m_len

    kept = list(reversed(kept_rev))

    # Clean boundary: never start with an orphaned 'tool' role message
    while kept and kept[0].get("role") == "tool":
        kept.pop(0)

    result = []
    if system_msg:
        result.append(system_msg)
    if first_user_msg and (not kept or first_user_msg not in kept):
        result.append(first_user_msg)
    result.extend(kept)
    return result

def emergency_compact_messages(messages: List[Dict[str, Any]], keep_recent: int = 10) -> List[Dict[str, Any]]:
    """
    Aggressive compaction called if llama-swap throws a 400 context overflow error.
    Keeps system prompt, first user request, and the most recent `keep_recent` messages with clean boundaries.
    """
    if not messages:
        return messages

    system_msg = messages[0] if messages[0].get("role") == "system" else None
    remaining = messages[1:] if system_msg else messages[:]

    first_user_msg = None
    for m in remaining:
        if m.get("role") == "user":
            first_user_msg = m
            break

    recent = remaining[-keep_recent:] if len(remaining) > keep_recent else remaining[:]
    while recent and recent[0].get("role") == "tool":
        recent.pop(0)

    result = []
    if system_msg:
        result.append(system_msg)
    if first_user_msg and (not recent or first_user_msg not in recent):
        result.append(first_user_msg)
    result.extend(recent)
    return result

def validate_and_fill_tool_args(tool_name: str, parsed_args: Dict[str, Any], tool_schemas: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures arguments strictly adhere to tool schema: removes disallowed properties and injects missing required fields."""
    schema = tool_schemas.get(tool_name) or {}
    properties = schema.get("properties") or {}
    required = schema.get("required") or []

    if not properties:
        return parsed_args

    clean_args = {}
    for k, v in parsed_args.items():
        if k in properties:
            clean_args[k] = v

    for req_field in required:
        if req_field not in clean_args:
            prop_type = properties.get(req_field, {}).get("type", "string").lower()
            if req_field == "WaitMsBeforeAsync":
                clean_args[req_field] = 5000
            elif req_field == "toolAction":
                clean_args[req_field] = f"Executing {tool_name}"
            elif req_field == "toolSummary":
                clean_args[req_field] = f"{tool_name} execution"
            elif req_field == "Cwd":
                clean_args[req_field] = "K:\\Project"
            elif prop_type in ("integer", "number"):
                clean_args[req_field] = 0
            elif prop_type == "boolean":
                clean_args[req_field] = False
            elif prop_type == "array":
                clean_args[req_field] = []
            elif prop_type == "object":
                clean_args[req_field] = {}
            else:
                clean_args[req_field] = ""

    return clean_args

def gemini_to_openai_messages(gemini_request: Dict[str, Any], compact_history: bool = True) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Translates Google Gemini/CCPA GenerateContentRequest into standard OpenAI Chat messages, tools, and schemas.
    Supports text, inline images, function calls, and smart-compacted function responses.
    """
    messages = []
    
    # 1. System instructions
    sys_inst = gemini_request.get("systemInstruction") or {}
    sys_parts = sys_inst.get("parts") or []
    sys_text_pieces = []
    for part in sys_parts:
        if "text" in part:
            sys_text_pieces.append(part["text"])
    if sys_text_pieces:
        messages.append({"role": "system", "content": "\n\n".join(sys_text_pieces)})
        
    # 2. Build map of tool arguments from model calls so responses can refer to paths/commands
    contents = gemini_request.get("contents") or []
    total_contents = len(contents)
    recent_threshold = 8
    
    tool_args_history: Dict[str, Dict[str, Any]] = {}
    pending_tool_call_ids: Dict[str, List[str]] = {}
    for content in contents:
        for part in content.get("parts") or []:
            if "functionCall" in part:
                fc = part["functionCall"]
                name = fc.get("name", "")
                args = fc.get("args") or {}
                if name:
                    tool_args_history[name] = args

    # 3. Conversation contents with smart compaction
    global_tool_call_counter = 0
    for idx, content in enumerate(contents):
        is_recent = (total_contents - idx) <= recent_threshold
        role = content.get("role")
        openai_role = "user" if role == "user" else "assistant"
        parts = content.get("parts") or []
        
        text_parts = []
        image_parts = []
        tool_calls = []
        function_responses = []
        
        for part in parts:
            if "text" in part:
                text_parts.append(part["text"])
            elif "inlineData" in part:
                id_data = part["inlineData"]
                mime = id_data.get("mimeType", "image/jpeg")
                b64 = id_data.get("data", "")
                if b64:
                    image_parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"}
                    })
            elif "functionCall" in part:
                fc = part["functionCall"]
                fn_name = fc.get("name", "tool")
                call_id = f"call_{fn_name}_{global_tool_call_counter}"
                global_tool_call_counter += 1
                tool_calls.append({
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": fn_name,
                        "arguments": json.dumps(fc.get("args") or {})
                    }
                })
                pending_tool_call_ids.setdefault(fn_name, []).append(call_id)
            elif "functionResponse" in part:
                fr = part["functionResponse"]
                function_responses.append({
                    "name": fr.get("name", ""),
                    "response": fr.get("response", {})
                })
                
        if function_responses:
            for fr in function_responses:
                t_name = fr["name"]
                resp_obj = fr["response"]
                resp_content = resp_obj.get("content") if isinstance(resp_obj, dict) and "content" in resp_obj else resp_obj
                
                # Check for nested output field
                if isinstance(resp_content, dict) and "output" in resp_content and isinstance(resp_content["output"], str):
                    raw_text = resp_content["output"]
                    if compact_history and not is_recent:
                        args = tool_args_history.get(t_name) or {}
                        resp_content["output"] = smart_compact_tool_response(t_name, raw_text, args)
                    formatted_content = json.dumps(resp_content, ensure_ascii=False)
                elif isinstance(resp_content, str):
                    if compact_history and not is_recent:
                        args = tool_args_history.get(t_name) or {}
                        formatted_content = smart_compact_tool_response(t_name, resp_content, args)
                    else:
                        formatted_content = resp_content
                else:
                    raw_str = json.dumps(resp_content, ensure_ascii=False)
                    if compact_history and not is_recent:
                        args = tool_args_history.get(t_name) or {}
                        formatted_content = smart_compact_tool_response(t_name, raw_str, args)
                    else:
                        formatted_content = raw_str

                # Resolve matching tool_call_id
                t_queue = pending_tool_call_ids.get(t_name, [])
                resolved_id = t_queue.pop(0) if t_queue else f"call_{t_name}_0"

                messages.append({
                    "role": "tool",
                    "name": t_name,
                    "tool_call_id": resolved_id,
                    "content": formatted_content
                })
        else:
            msg = {"role": openai_role}
            combined_text = "\n".join(text_parts)
            
            if image_parts:
                content_list = []
                if combined_text:
                    content_list.append({"type": "text", "text": combined_text})
                content_list.extend(image_parts)
                msg["content"] = content_list
            else:
                msg["content"] = combined_text if combined_text else ""

            if tool_calls:
                msg["tool_calls"] = tool_calls
            messages.append(msg)
            
    # 4. Tools definitions & schema map
    tools = []
    tool_schemas = {}
    gemini_tools = gemini_request.get("tools") or []
    for t in gemini_tools:
        for fd in t.get("functionDeclarations") or []:
            name = fd.get("name", "")
            raw_params = fd.get("parameters") or {"type": "object", "properties": {}}
            norm_params = normalize_gemini_schema(raw_params)
            tool_schemas[name] = norm_params
            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": fd.get("description", ""),
                    "parameters": norm_params
                }
            })
            
    # 5. Enforce context budget guard for local inference
    messages = enforce_context_token_budget(messages)
    return messages, tools, tool_schemas

def format_gemini_sse_thought_chunk(thought_text: str) -> str:
    """Format single reasoning/thinking chunk for Gemini CCPA SSE (rendered as collapsible Thinking box)."""
    payload = {
        "response": {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [{"thought": True, "text": thought_text}]
                    }
                }
            ]
        }
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

def format_gemini_sse_text_chunk(text: str) -> str:
    """Format single regular text chunk for Gemini CCPA SSE."""
    payload = {
        "response": {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [{"text": text}]
                    }
                }
            ]
        }
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

def format_gemini_sse_function_call(name: str, args_dict: Dict[str, Any]) -> str:
    """Format functionCall chunk for Gemini CCPA SSE."""
    payload = {
        "response": {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {
                                "functionCall": {
                                    "name": name,
                                    "args": args_dict
                                }
                            }
                        ]
                    }
                }
            ]
        }
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

def format_gemini_sse_finish(finish_reason: str = "STOP") -> str:
    """Format stream finish chunk for Gemini CCPA SSE."""
    payload = {
        "response": {
            "candidates": [
                {
                    "finishReason": finish_reason
                }
            ]
        }
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
