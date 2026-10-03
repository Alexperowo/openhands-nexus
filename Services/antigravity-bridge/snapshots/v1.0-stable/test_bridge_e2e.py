import os
import sys
import json
import time
import socket
import urllib.request
import threading
import unittest

from upstream_detector import get_upstream_proxy, _is_proxy_alive
from auth_vault import get_auth_fallback, save_auth_cache
from model_catalog import inject_local_model, get_models_fallback, LOCAL_MODEL_ID
from converter import (
    gemini_to_openai_messages,
    format_gemini_sse_thought_chunk,
    format_gemini_sse_text_chunk,
    format_gemini_sse_finish
)
from bridge import ThreadedHTTPServer, AntigravityBridgeHandler

TEST_PORT = 18007

class TestBridgeSuite(unittest.TestCase):
    def test_01_peb_proxy_detection(self):
        """Verify PEB-based live proxy detection."""
        proxy = get_upstream_proxy()
        print(f"\n[TEST 1] Detected live proxy: {proxy}")
        self.assertIsNotNone(proxy, "Expected live agy-unlock proxy to be found")
        self.assertTrue(proxy.startswith("http://"), "Expected valid HTTP proxy URL")
        # Check port connectivity
        host_port = proxy.split("@")[-1].replace("http://", "")
        host, port_str = host_port.split(":")
        self.assertTrue(_is_proxy_alive(host, int(port_str)), f"Proxy port {port_str} should be listening")

    def test_02_auth_vault_resilience(self):
        """Verify Auth Vault guarantees 200 OK fallback profiles."""
        lca = get_auth_fallback("/v1internal:loadCodeAssist")
        self.assertTrue("currentTier" in lca or "userTier" in lca)
        self.assertIn("cloudaicompanionProject", lca)

        ui = get_auth_fallback("/v1internal:fetchUserInfo")
        self.assertTrue("userSettings" in ui or "userEmail" in ui)

    def test_03_model_catalog_injection(self):
        """Verify station-local is injected with correct metadata."""
        sample_catalog = {
            "models": {
                "gemini-3.8-flash": {"displayName": "Gemini 3.8 Flash"}
            },
            "agentModelSorts": [
                {"groups": [{"modelIds": ["gemini-3.8-flash"]}]}
            ]
        }
        merged = inject_local_model(sample_catalog)
        self.assertIn(LOCAL_MODEL_ID, merged["models"])
        spec = merged["models"][LOCAL_MODEL_ID]
        self.assertEqual(spec["displayName"], "Локальная модель")
        self.assertEqual(spec["tagTitle"], "Station Local")
        self.assertEqual(spec["tagDescription"], "Dual-GPU (5060Ti + 2080Ti) / llama-swap")
        self.assertEqual(spec["maxTokens"], 131072)
        self.assertEqual(spec["maxOutputTokens"], 8192)
        # Check priority sort
        self.assertEqual(merged["agentModelSorts"][0]["groups"][0]["modelIds"][0], LOCAL_MODEL_ID)

    def test_04_converter_thought_sse(self):
        """Verify native thought: true and text SSE formatting."""
        thought_chunk = format_gemini_sse_thought_chunk("Рассуждаю о плане...")
        self.assertTrue(thought_chunk.startswith("data: "))
        parsed = json.loads(thought_chunk[5:].strip())
        candidate_parts = parsed["response"]["candidates"][0]["content"]["parts"]
        self.assertTrue(candidate_parts[0].get("thought"), "Expected thought: True")
        self.assertEqual(candidate_parts[0].get("text"), "Рассуждаю о плане...")

        text_chunk = format_gemini_sse_text_chunk("Ответ пользователю.")
        parsed_text = json.loads(text_chunk[5:].strip())
        parts = parsed_text["response"]["candidates"][0]["content"]["parts"]
        self.assertNotIn("thought", parts[0], "Regular text must not contain thought: True")
        self.assertEqual(parts[0]["text"], "Ответ пользователю.")

    def test_05_converter_messages_and_images(self):
        """Verify multimodal and tools conversion to OpenAI format."""
        gemini_req = {
            "systemInstruction": {"parts": [{"text": "Ты полезный ассистент."}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": "Посмотри на картинку"},
                        {"inlineData": {"mimeType": "image/png", "data": "iVBORw0KGgoAAAANSUhEUg=="}}
                    ]
                }
            ],
            "tools": [
                {
                    "functionDeclarations": [
                        {
                            "name": "run_command",
                            "description": "Run terminal command",
                            "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}}
                        }
                    ]
                }
            ]
        }
        messages, tools, tool_schemas = gemini_to_openai_messages(gemini_req)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertIsInstance(messages[1]["content"], list)
        self.assertEqual(messages[1]["content"][0]["type"], "text")
        self.assertEqual(messages[1]["content"][1]["type"], "image_url")
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["function"]["name"], "run_command")
        self.assertIn("run_command", tool_schemas)

    def test_06_live_http_server_endpoints(self):
        """Start isolated HTTP server on TEST_PORT and verify endpoints."""
        server = ThreadedHTTPServer(("127.0.0.1", TEST_PORT), AntigravityBridgeHandler)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        time.sleep(0.5)

        try:
            # 1. Test loadCodeAssist (must return 200 OK without valid auth token)
            req = urllib.request.Request(
                f"http://127.0.0.1:{TEST_PORT}/v1internal:loadCodeAssist",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode("utf-8"))
                self.assertTrue("currentTier" in body or "userTier" in body)
                print(f"[TEST 6.1] loadCodeAssist returned 200 OK (tier: {body.get('currentTier') or body.get('userTier')})")

            # 2. Test fetchUserInfo (must return 200 OK)
            req = urllib.request.Request(
                f"http://127.0.0.1:{TEST_PORT}/v1internal:fetchUserInfo",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode("utf-8"))
                self.assertTrue("userSettings" in body or "userEmail" in body)
                print(f"[TEST 6.2] fetchUserInfo returned 200 OK (body: {body})")

            # 3. Test fetchAvailableModels (must inject station-local)
            req = urllib.request.Request(
                f"http://127.0.0.1:{TEST_PORT}/v1internal:fetchAvailableModels",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode("utf-8"))
                self.assertIn(LOCAL_MODEL_ID, body["models"])
                spec = body["models"][LOCAL_MODEL_ID]
                self.assertEqual(spec["displayName"], "Локальная модель")
                print(f"[TEST 6.3] fetchAvailableModels returned 200 OK with '{spec['displayName']}'")

            # 4. Test live streamGenerateContent with llama-swap:8080 (Dual-GPU Qwen 3.8)
            payload = {
                "model": LOCAL_MODEL_ID,
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": "Ответь одним коротким предложением: подтверди готовность станции."}]
                    }
                ]
            }
            req = urllib.request.Request(
                f"http://127.0.0.1:{TEST_PORT}/v1internal:streamGenerateContent",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            received_chunks = []
            thought_received = False
            with urllib.request.urlopen(req, timeout=60) as resp:
                self.assertEqual(resp.status, 200)
                for line in resp:
                    s = line.decode("utf-8").strip()
                    if s.startswith("data:"):
                        chunk_json = json.loads(s[5:].strip())
                        received_chunks.append(chunk_json)
                        cands = chunk_json.get("response", {}).get("candidates", [])
                        if cands and "content" in cands[0]:
                            parts = cands[0]["content"].get("parts", [])
                            for p in parts:
                                if p.get("thought"):
                                    thought_received = True

            self.assertGreater(len(received_chunks), 1, "Expected streaming SSE chunks")
            finish_chunk = received_chunks[-1]
            self.assertEqual(
                finish_chunk.get("response", {}).get("candidates", [{}])[0].get("finishReason"),
                "STOP"
            )
            # 5. Test chunked Transfer-Encoding on streamGenerateContent
            import http.client
            conn = http.client.HTTPConnection("127.0.0.1", TEST_PORT)
            conn.putrequest("POST", "/v1internal:streamGenerateContent")
            conn.putheader("Transfer-Encoding", "chunked")
            conn.putheader("Content-Type", "application/json")
            conn.endheaders()
            chunk_data = json.dumps(payload).encode("utf-8")
            chunk_hex = f"{len(chunk_data):x}\r\n".encode()
            conn.send(chunk_hex + chunk_data + b"\r\n0\r\n\r\n")
            chunked_resp = conn.getresponse()
            self.assertEqual(chunked_resp.status, 200)
            chunked_lines = chunked_resp.read().decode("utf-8").split("\n")
            data_lines = [l for l in chunked_lines if l.startswith("data:")]
            self.assertGreater(len(data_lines), 1, "Expected SSE chunks from chunked request")
            print(f"[TEST 6.5] Chunked Transfer-Encoding streamGenerateContent returned {len(data_lines)} SSE chunks [DONE]")
            conn.close()

        finally:
            server.shutdown()
            server.server_close()

    def test_07_smart_context_compaction(self):
        """Verify that older large tool outputs are intelligently compacted while preserving paths and commands."""
        from converter import smart_compact_tool_response

        # Test view_file compaction
        fake_code = "\n".join([f"line_{i} = do_something({i})" for i in range(100)])
        compacted_file = smart_compact_tool_response("view_file", fake_code, {"AbsolutePath": "K:/Project/test.py", "StartLine": 1, "EndLine": 100})
        self.assertIn("K:/Project/test.py", compacted_file)
        self.assertIn("Контекст оптимизирован", compacted_file)
        self.assertIn("line_0", compacted_file)
        self.assertIn("line_99", compacted_file)
        self.assertLess(len(compacted_file), len(fake_code) // 3)

        # Test run_command compaction
        fake_log = "Build started...\n" + "\n".join([f"Compiling module_{i}..." for i in range(80)]) + "\nBuild finished with exit code 0."
        compacted_cmd = smart_compact_tool_response("run_command", fake_log, {"CommandLine": "npm run build", "Cwd": "K:/Project/web"})
        self.assertIn("npm run build", compacted_cmd)
        self.assertIn("K:/Project/web", compacted_cmd)
        self.assertIn("Build started", compacted_cmd)
        self.assertIn("exit code 0", compacted_cmd)
        self.assertLess(len(compacted_cmd), len(fake_log) // 3)

    def test_08_tool_argument_repair_and_validation(self):
        """Verify that broken JSON strings and missing required parameters are repaired without 'raw' fallback."""
        from converter import repair_json_string, validate_and_fill_tool_args

        # 1. Truncated JSON without closing brace and with Windows backslashes
        broken_json = '{"CommandLine":"Get-Content \\"K:\\\\Project\\\\bridge.log\\" -Tail 40","Cwd":"K:\\\\Project"'
        repaired = repair_json_string(broken_json)
        self.assertIn("CommandLine", repaired)
        self.assertIn("Cwd", repaired)

        # 2. Schema validation and injection of required fields
        schema = {
            "type": "object",
            "properties": {
                "CommandLine": {"type": "string"},
                "Cwd": {"type": "string"},
                "WaitMsBeforeAsync": {"type": "integer"},
                "toolAction": {"type": "string"},
                "toolSummary": {"type": "string"}
            },
            "required": ["CommandLine", "Cwd", "WaitMsBeforeAsync", "toolAction", "toolSummary"]
        }
        validated = validate_and_fill_tool_args("run_command", repaired, {"run_command": schema})
        self.assertIn("WaitMsBeforeAsync", validated)
        self.assertIn("toolAction", validated)
        self.assertIn("toolSummary", validated)
        self.assertNotIn("raw", validated)
        self.assertEqual(validated["WaitMsBeforeAsync"], 5000)

    def test_09_hollow_tool_call_filtering(self):
        """Verify that inoperable / hollow tool calls are strictly caught and rejected."""
        from converter import is_tool_call_operable

        # Empty CommandLine
        self.assertFalse(is_tool_call_operable("run_command", {"CommandLine": "", "Cwd": "K:\\Project"}))
        self.assertFalse(is_tool_call_operable("run_command", {"CommandLine": "   "}))
        self.assertTrue(is_tool_call_operable("run_command", {"CommandLine": "git status"}))

        # Empty AbsolutePath
        self.assertFalse(is_tool_call_operable("view_file", {"AbsolutePath": ""}))
        self.assertTrue(is_tool_call_operable("view_file", {"AbsolutePath": "K:\\Project\\bridge.py"}))

        # Empty TargetFile
        self.assertFalse(is_tool_call_operable("write_to_file", {"TargetFile": ""}))
        self.assertTrue(is_tool_call_operable("write_to_file", {"TargetFile": "K:\\Project\\test.txt"}))

    def test_10_context_token_budget_and_emergency_compaction(self):
        """Verify token budget enforcement and emergency compaction preserves system message and boundaries."""
        from converter import enforce_context_token_budget, emergency_compact_messages

        # Build simulated long conversation
        messages = [
            {"role": "system", "content": "System prompt instructions"},
            {"role": "user", "content": "Primary user goal: build station bridge"},
        ]
        for i in range(50):
            messages.append({"role": "assistant", "content": f"Step {i}: executing tool", "tool_calls": [{"id": f"call_{i}", "type": "function", "function": {"name": "run_cmd", "arguments": "{}"}}]})
            messages.append({"role": "tool", "name": "run_cmd", "tool_call_id": f"call_{i}", "content": f"Result {i} " * 200})

        # Test budget enforcement
        budgeted = enforce_context_token_budget(messages, max_chars=10000)
        self.assertEqual(budgeted[0]["role"], "system")
        self.assertEqual(budgeted[1]["content"], "Primary user goal: build station bridge")
        # Boundary check: ensure no leading tool role without assistant
        self.assertNotEqual(budgeted[2]["role"], "tool")

        # Test emergency compaction
        emergency = emergency_compact_messages(messages, keep_recent=6)
        self.assertEqual(emergency[0]["role"], "system")
        self.assertEqual(emergency[1]["content"], "Primary user goal: build station bridge")
        self.assertLessEqual(len(emergency), 8)
        self.assertNotEqual(emergency[2]["role"], "tool")

    def test_11_auxiliary_endpoints_resilience(self):
        """Verify auxiliary analytics endpoints return instant 200 OK {}."""
        server = ThreadedHTTPServer(("127.0.0.1", TEST_PORT), AntigravityBridgeHandler)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        time.sleep(0.5)

        try:
            for ep in ["/v1internal:recordTrajectoryAnalytics", "/v1internal:listExperiments"]:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{TEST_PORT}{ep}",
                    data=b'{"dummy": true}',
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read().decode("utf-8"))
                    self.assertIsInstance(body, dict)
                    print(f"[TEST 11] {ep} returned 200 OK: {body}")
        finally:
            server.shutdown()
            server.server_close()

if __name__ == "__main__":
    unittest.main()

