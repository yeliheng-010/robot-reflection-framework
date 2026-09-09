import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from reflection.adapters import DemoSimulator
from reflection.contracts import Action, State
from reflection.http_reflector import HttpReflector
from reflection.reflectors import RuleReflector


class HttpTests(unittest.TestCase):
    def invoke_endpoint(self, response_factory):
        captured = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                captured.update(body)
                response = response_factory(body)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        state = State()
        action = Action(state_ref=state.state_id)
        feedback = DemoSimulator().preview(action, state)
        env = {"REFLECTION_API_URL": f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
               "REFLECTION_MODEL": "test-model", "REFLECTION_API_KEY": ""}
        try:
            with patch.dict(os.environ, env):
                result = HttpReflector().reflect(action, feedback)
            return result, captured
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_actual_local_http_request_and_typed_response(self):
        def response(body):
            context = json.loads(body["messages"][1]["content"])
            from reflection.contracts import Feedback
            proposal = RuleReflector().reflect(
                Action.model_validate(context["action"]), Feedback.model_validate(context["feedback"]))
            return {"choices": [{"message": {"content": proposal.model_dump_json()}}]}
        result, request = self.invoke_endpoint(response)
        self.assertEqual("revise", result.decision)
        self.assertEqual("test-model", request["model"])
        self.assertEqual(0.03, result.new_speed_m_s)

    def test_invalid_response_envelope_rejected(self):
        with self.assertRaises(ValueError):
            self.invoke_endpoint(lambda _: {"choices": []})

    def test_invalid_model_json_rejected(self):
        with self.assertRaises(ValueError):
            self.invoke_endpoint(lambda _: {"choices": [{"message": {"content": "not json"}}]})

    def test_external_plain_http_rejected(self):
        with patch.dict(os.environ, {"REFLECTION_API_URL": "http://example.com/v1/chat/completions",
                                     "REFLECTION_MODEL": "test"}):
            with self.assertRaises(ValueError):
                HttpReflector()
