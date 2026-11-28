"""Reading a real reply: the SDK talks to a stand-in endpoint, not a mock (issue #50).

The SDK's ``parse`` validated the reply itself and rejected a fenced one before pr-inspector
could read it, so tests that mocked ``parse`` never saw the real behaviour. These tests send
real HTTP requests and read real responses.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from openai import OpenAI

from pr_inspector.domain.entities import FileDiff, PRReviewResult
from pr_inspector.domain.exceptions import ReviewExecutionError
from pr_inspector.infrastructure.llm.openai_client import (
    SCHEMA_FAILURE_MESSAGE,
    OpenAICompatibleLLMReviewer,
)

REVIEW = {"summary": "One problem.", "risk_level": "LOW", "issues": []}


class StandInEndpoint:
    """Answers each chat-completion request with the next reply content, and keeps the bodies."""

    def __init__(self, *contents: str | None) -> None:
        self.contents = list(contents)
        self.bodies: list[dict] = []
        endpoint = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                endpoint.bodies.append(
                    json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                )
                message = {"role": "assistant", "content": endpoint.contents.pop(0)}
                choice = {"index": 0, "message": message, "finish_reason": "stop"}
                usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
                body = {"id": "c", "object": "chat.completion", "created": 0, "model": "m"}
                data = json.dumps({**body, "choices": [choice], "usage": usage}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self.base_url = f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def endpoint_with():
    endpoints = []

    def start(*contents: str | None) -> StandInEndpoint:
        endpoints.append(StandInEndpoint(*contents))
        return endpoints[-1]

    yield start
    for endpoint in endpoints:
        endpoint.close()


def review(endpoint: StandInEndpoint) -> PRReviewResult:
    reviewer = OpenAICompatibleLLMReviewer(base_url=endpoint.base_url, api_key="k", model="m")
    result, _ = reviewer.review([FileDiff(file_path="a.py")])
    return result


def test_the_request_is_the_one_the_sdk_parse_sends(endpoint_with):
    # The reviewer no longer calls ``parse``, but the endpoint must see the same request:
    # local models are deterministic, and earlier benchmark results depend on it.
    ours = endpoint_with(json.dumps(REVIEW))
    review(ours)
    sdks = endpoint_with(json.dumps(REVIEW))
    OpenAI(base_url=sdks.base_url, api_key="k").beta.chat.completions.parse(
        model="m",
        messages=ours.bodies[0]["messages"],
        response_format=PRReviewResult,
        temperature=0.0,
    )

    assert ours.bodies[0] == sdks.bodies[0]


def test_a_fenced_reply_is_parsed_with_one_request(endpoint_with):
    endpoint = endpoint_with("```json\n" + json.dumps(REVIEW) + "\n```")

    assert review(endpoint).summary == "One problem."
    assert len(endpoint.bodies) == 1


@pytest.mark.parametrize("empty", ["", None])
def test_an_empty_reply_is_retried_once(endpoint_with, empty):
    endpoint = endpoint_with(empty, json.dumps(REVIEW))

    assert review(endpoint).summary == "One problem."
    assert len(endpoint.bodies) == 2


def test_two_empty_replies_fail_the_review(endpoint_with):
    endpoint = endpoint_with(None, None)

    with pytest.raises(ReviewExecutionError) as caught:
        review(endpoint)

    assert str(caught.value) == SCHEMA_FAILURE_MESSAGE
    assert len(endpoint.bodies) == 2
