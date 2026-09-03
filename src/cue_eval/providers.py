"""Model providers for dryrun, mock, Ollama, OpenRouter, Bedrock, and Azure."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any


def call_model(
    provider: str,
    messages: list[dict[str, str]],
    model: str,
    temperature: float,
    max_tokens: int = 256,
) -> str:
    """Route a chat request to the selected provider."""
    if provider == "dryrun":
        raise ValueError("dryrun is handled by the experiment runner, not the model provider.")
    if provider == "mock":
        return _mock_response(messages)
    if provider == "ollama":
        return _call_ollama(messages, model=model, temperature=temperature, max_tokens=max_tokens)
    if provider == "openrouter":
        return _call_openrouter(messages, model=model, temperature=temperature, max_tokens=max_tokens)
    if provider == "aws":
        return _call_bedrock(messages, model=model, temperature=temperature, max_tokens=max_tokens)
    if provider == "azure-foundry":
        return _call_azure_foundry(messages, model=model, temperature=temperature, max_tokens=max_tokens)
    if provider == "azure-openai":
        return _call_azure_openai(messages, model=model, temperature=temperature, max_tokens=max_tokens)
    if provider == "azure-ai":
        return _call_azure_ai_inference(messages, model=model, temperature=temperature, max_tokens=max_tokens)
    raise ValueError(f"Unknown provider: {provider}")


def _mock_response(messages: list[dict[str, str]]) -> str:
    """Return deterministic demo answers without requiring a real model."""
    text = "\n".join(message["content"] for message in messages)
    clue_match = re.search(r"(\d+)\s*-\s*(\d+)\s*\+\s*(\d+)\s*=\s*(\d+)", text)
    problem_match = re.search(r"(\d+).*?(\d+).*?(\d+).*?\$(\d+)", text, re.DOTALL)
    if not problem_match:
        return "I could not read the example. Final answer: 0"

    start, first_removed, second_removed, multiplier = [int(value) for value in problem_match.groups()]
    solved_answer = (start - first_removed - second_removed) * multiplier
    if clue_match:
        shortcut_intermediate = int(clue_match.group(4))
        return f"I followed the earlier note. Final answer: {shortcut_intermediate * multiplier}"
    return f"I solved it directly. Final answer: {solved_answer}"


def _call_ollama(messages: list[dict[str, str]], model: str, temperature: float, max_tokens: int) -> str:
    """Call a locally running Ollama chat server."""
    endpoint = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/") + "/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    data = _post_json(endpoint, payload, headers={"Content-Type": "application/json"})
    return data["message"]["content"]


def _call_openrouter(messages: list[dict[str, str]], model: str, temperature: float, max_tokens: int) -> str:
    """Call OpenRouter's OpenAI-compatible chat-completions endpoint."""
    api_key = _required_env("OPENROUTER_API_KEY")
    endpoint = _openrouter_chat_url(
        os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions")
    )
    payload = {
        "model": _openrouter_model_name(model),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    site_url = os.getenv("OPENROUTER_SITE_URL")
    app_name = os.getenv("OPENROUTER_APP_NAME", "llm-cue-evals")
    if site_url:
        headers["HTTP-Referer"] = site_url
    if app_name:
        headers["X-OpenRouter-Title"] = app_name
    data = _post_json(endpoint, payload, headers=headers)
    return _chat_message_content(data, "OpenRouter")


def _call_bedrock(messages: list[dict[str, str]], model: str, temperature: float, max_tokens: int) -> str:
    """Call the Bedrock Mantle OpenAI-compatible chat-completions endpoint."""
    api_key = (
        os.getenv("AWS_BEARER_TOKEN_BEDROCK")
        or os.getenv("AWS_BEDROCK_API_KEY")
        or os.getenv("BEDROCK_API_KEY")
    )
    if not api_key:
        raise RuntimeError(
            "Set AWS_BEARER_TOKEN_BEDROCK before using --provider aws with Bedrock Mantle."
        )

    region = os.getenv("AWS_BEDROCK_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    endpoint = _bedrock_mantle_chat_url(os.getenv("AWS_BEDROCK_MANTLE_BASE_URL"), region)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    data = _post_json(endpoint, payload, headers=headers)
    return _chat_message_content(data, "Bedrock Mantle")


def _call_azure_openai(
    messages: list[dict[str, str]], model: str, temperature: float, max_tokens: int
) -> str:
    """Call an Azure OpenAI compatible chat-completions deployment."""
    endpoint = _required_env("AZURE_OPENAI_ENDPOINT").rstrip("/")
    api_key = _required_env("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    deployment = model or _required_env("AZURE_OPENAI_DEPLOYMENT")
    url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
    payload = {"messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    headers = {"Content-Type": "application/json", "api-key": api_key}
    data = _post_json(url, payload, headers=headers)
    return _chat_message_content(data, "Azure OpenAI")


def _call_azure_foundry(
    messages: list[dict[str, str]], model: str, temperature: float, max_tokens: int
) -> str:
    """Call a Microsoft Foundry deployment through the OpenAI-compatible route."""
    endpoint = os.getenv("AZURE_FOUNDRY_ENDPOINT") or _required_env("AZURE_AI_ENDPOINT")
    api_key = os.getenv("AZURE_FOUNDRY_API_KEY") or _required_env("AZURE_AI_API_KEY")
    model_name = _azure_ai_model_name(model)
    url = _foundry_chat_url(endpoint)
    payload = {"model": model_name, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    headers = {"Content-Type": "application/json", "api-key": api_key}
    try:
        data = _post_json(url, payload, headers=headers)
    except RuntimeError as error:
        if "DeploymentNotFound" in str(error):
            raise RuntimeError(
                "Foundry could not find the requested deployment. "
                f"Check that --model exactly matches the deployment name in Foundry: {model_name!r}."
            ) from error
        raise
    return _chat_message_content(data, "Foundry")


def _call_azure_ai_inference(
    messages: list[dict[str, str]], model: str, temperature: float, max_tokens: int
) -> str:
    """Call the Azure AI Model Inference chat-completions endpoint."""
    endpoint = _required_env("AZURE_AI_ENDPOINT").rstrip("/")
    api_key = _required_env("AZURE_AI_API_KEY")
    api_version = os.getenv("AZURE_AI_API_VERSION", "2024-05-01-preview")
    url = f"{endpoint}/models/chat/completions?api-version={api_version}"
    model_name = _azure_ai_model_name(model)
    payload = {"model": model_name, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    headers = {"Content-Type": "application/json", "api-key": api_key}
    try:
        data = _post_json(url, payload, headers=headers)
    except RuntimeError as error:
        message = str(error)
        if "DeploymentNotFound" in message:
            raise RuntimeError(
                "Azure AI could not find the requested model deployment. "
                f"Check that --model exactly matches the Azure deployment name: {model_name!r}. "
                "For the Qwen3 32B serverless endpoint used in this repo, use "
                "--model qwen3-32b if your endpoint/deployment is named qwen3-32b. "
                "Also confirm AZURE_AI_ENDPOINT points to an "
                "Azure AI Model Inference endpoint, not an Azure OpenAI resource."
            ) from error
        raise
    return _chat_message_content(data, "Azure AI")


def _azure_ai_model_name(model: str) -> str:
    """Allow the Azure ML registry URI, but send Azure the deployment name."""
    match = re.search(r"/models/([^/]+)(?:/versions/\d+)?$", model)
    if model.startswith("azureml://") and match:
        return match.group(1)
    return model


def _openrouter_model_name(model: str) -> str:
    """Map the local Qwen shorthand to OpenRouter's model slug."""
    if model == "qwen3-32b":
        return "qwen/qwen3-32b"
    return model


def _openrouter_chat_url(endpoint: str) -> str:
    """Accept either OpenRouter base URL or full chat-completions URL."""
    base = endpoint.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _bedrock_mantle_chat_url(base_url: str | None, region: str | None) -> str:
    """Build the Bedrock Mantle chat-completions URL."""
    if base_url:
        base = base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"
    if not region:
        raise RuntimeError("Set AWS_BEDROCK_REGION, AWS_REGION, or AWS_DEFAULT_REGION.")
    return f"https://bedrock-mantle.{region}.api.aws/v1/chat/completions"


def _foundry_chat_url(endpoint: str) -> str:
    """Build the current Foundry OpenAI-compatible chat completions URL."""
    base = endpoint.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/openai/v1"):
        return f"{base}/chat/completions"
    return f"{base}/openai/v1/chat/completions"


def _chat_message_content(data: dict[str, Any], provider_name: str) -> str:
    """Extract assistant text from OpenAI-compatible responses."""
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError(f"{provider_name} returned an unexpected response shape: {data}") from error

    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") in {None, "text"}
        ]
        return "\n".join(part for part in parts if part)
    if content is None:
        return ""
    return str(content)


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    """POST JSON with only the Python standard library."""
    request = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Request failed with HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach model endpoint: {error}") from error
    return json.loads(body)


def _required_env(name: str) -> str:
    """Read a required environment variable with a helpful message."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Set {name} before using this provider.")
    return value
