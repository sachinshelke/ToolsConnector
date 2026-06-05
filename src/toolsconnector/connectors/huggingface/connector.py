"""Hugging Face connector -- Inference tasks, chat completion, and Hub metadata.

Uses httpx for direct HTTP calls against two Hugging Face hosts:

- the **Inference Providers router** (``router.huggingface.co``) for
  running hosted models on a task and for the OpenAI-compatible
  ``/v1/chat/completions`` and ``/v1/models`` endpoints. Task inference
  posts to ``/{provider}/models/{model}/pipeline/{task}`` -- the explicit
  ``/pipeline/{task}`` segment pins routing to the requested pipeline
  (the bare ``/models/{model}`` form mis-routes some tasks). The
  ``provider`` defaults to ``hf-inference`` (HF's own serverless CPU/GPU
  pool) and may be switched to a partner provider (e.g. ``fal-ai``) to
  route heavy tasks elsewhere.
- the **Hub API** (``huggingface.co/api``) for model / dataset / Space
  metadata and identity.

Expects a user-access token (``hf_...``) as ``credentials`` (Bring Your
Own Key), sent via the ``Authorization: Bearer`` header on every call.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Optional, Union

import httpx

from toolsconnector.connectors._helpers import raise_typed_for_status
from toolsconnector.runtime import BaseConnector, action
from toolsconnector.spec.connector import (
    ConnectorCategory,
    ProtocolType,
    RateLimitSpec,
)

from . import _parsers as p
from .types import (
    HFChatCompletion,
    HFClassification,
    HFDatasetInfo,
    HFFillMaskToken,
    HFGeneratedText,
    HFImageSegment,
    HFModelInfo,
    HFObjectDetection,
    HFQuestionAnswer,
    HFSpaceInfo,
    HFTableQuestionAnswer,
    HFTokenClassification,
    HFTranscription,
    HFWhoAmI,
    HFZeroShotResult,
)

logger = logging.getLogger("toolsconnector.huggingface")

# The Inference Providers router serves both hosted-model task inference
# (``/{provider}/models/{model}/pipeline/{task}``) and the
# OpenAI-compatible chat endpoint; the Hub API serves metadata.
_ROUTER_BASE = "https://router.huggingface.co"
_HUB_BASE = "https://huggingface.co/api"

# Default inference provider: HF's own serverless pool. Callers may route
# heavy tasks to a partner provider (e.g. ``fal-ai``) per action.
_DEFAULT_PROVIDER = "hf-inference"


class HuggingFace(BaseConnector):
    """Connect to Hugging Face for inference, chat completion, and Hub metadata.

    Supports Bearer token authentication. Pass a user-access token
    (``hf_...``) as ``credentials`` when instantiating. Runs hosted
    models and OpenAI-compatible chat completions via the Inference
    Providers router, and browses model / dataset / Space metadata via
    the Hub API -- all with direct httpx calls.

    Provider coverage. The default ``hf-inference`` provider (HF's own
    serverless pool) serves the lighter "traditional ML" tasks -- chat,
    summarization, translation, fill-mask, text/token/zero-shot
    classification, QA, table-QA, embeddings, sentence-similarity, and
    image classification / detection / segmentation -- which are all
    live-verified end to end. The heavier generative and audio tasks
    (``text_generation`` of large LLMs, ``text_to_image``,
    ``text_to_speech``, ``image_to_text``, ``automatic_speech_recognition``,
    ``audio_classification``) are routed to **partner providers**: pass
    ``provider=`` (e.g. ``'fal-ai'``, ``'replicate'``, ``'together'``) to
    a provider that hosts your chosen model. (For chat-style text
    generation, prefer ``chat_completion``, which auto-routes.) Always use
    a model's canonical org-prefixed repo ID for inference -- the router
    does not resolve legacy aliases the way the Hub API does.
    """

    name = "huggingface"
    display_name = "Hugging Face"
    category = ConnectorCategory.AI_ML
    protocol = ProtocolType.REST
    base_url = _ROUTER_BASE
    description = (
        "Connect to Hugging Face to run hosted model inference across the "
        "full task set (text generation, chat completion, embeddings, "
        "classification, NER, vision, and audio) and to search models, "
        "datasets, and Spaces on the Hub."
    )
    verification_status = "live"
    # Hugging Face's serverless inference is throttled; keep requests modest.
    _rate_limit_config = RateLimitSpec(rate=60, period=60, burst=10)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        """Build the Bearer-authed httpx client, reused across all hosts.

        Reads the token from ``self._credentials`` (BYOK).
        """
        token = self._credentials or ""
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=self._timeout,
            # The Hub 307-redirects legacy repo aliases to their canonical
            # ID (e.g. ``bert-base-uncased`` -> ``google-bert/bert-base-uncased``,
            # ``squad`` -> ``rajpurkar/squad``). Follow redirects so single-repo
            # GETs resolve instead of trying to parse the redirect body as JSON.
            follow_redirects=True,
        )

    async def _teardown(self) -> None:
        """Close the httpx client."""
        if hasattr(self, "_client"):
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        base: str = _ROUTER_BASE,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[Any] = None,
    ) -> Any:
        """Execute an authenticated JSON request against a Hugging Face host.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: API path relative to ``base`` (must start with ``/``).
            base: Host to target -- the Inference Providers router
                (default, ``_ROUTER_BASE``) or the Hub API (``_HUB_BASE``).
            params: Optional query parameters.
            json_body: Optional JSON request body.

        Returns:
            The parsed JSON response (a list or dict; inference shape
            varies by task, Hub calls return a dict or list of dicts).

        Raises:
            toolsconnector.errors.APIError (subclass): On any non-2xx
                response, mapped to a typed exception by status (see
                ``toolsconnector.connectors._helpers.raise_typed_for_status``).
        """
        kwargs: dict[str, Any] = {"method": method, "url": f"{base}{path}"}
        if params:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body

        response = await self._client.request(**kwargs)
        raise_typed_for_status(response, connector=self.name)
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    async def _request_bytes(
        self,
        path: str,
        *,
        json_body: Any,
        base: str = _ROUTER_BASE,
    ) -> bytes:
        """POST to a host and return the raw response bytes.

        Used by binary-output tasks (text-to-image, text-to-speech) whose
        response body is the generated media rather than JSON.

        Args:
            path: API path relative to ``base`` (must start with ``/``).
            json_body: JSON request body.
            base: Host to target (defaults to the router, ``_ROUTER_BASE``).

        Returns:
            The raw response body bytes.

        Raises:
            toolsconnector.errors.APIError (subclass): On any non-2xx response.
        """
        response = await self._client.request("POST", f"{base}{path}", json=json_body)
        raise_typed_for_status(response, connector=self.name)
        return response.content

    @staticmethod
    def _pipeline_path(provider: str, model: str, task: str) -> str:
        """Build the router pipeline path for a task inference call.

        Returns ``/{provider}/models/{model}/pipeline/{task}``. The
        explicit ``/pipeline/{task}`` segment pins routing to the
        requested HF pipeline -- the bare ``/models/{model}`` form
        mis-routes some tasks (e.g. feature-extraction).
        """
        return f"/{provider}/models/{model}/pipeline/{task}"

    async def _infer(
        self,
        model: str,
        inputs: Any,
        task: str,
        parameters: Optional[dict[str, Any]] = None,
        options: Optional[dict[str, Any]] = None,
        provider: str = _DEFAULT_PROVIDER,
    ) -> Any:
        """Run a task on the Inference Providers router; return the payload.

        POSTs to ``{_ROUTER_BASE}/{provider}/models/{model}/pipeline/{task}``
        with the ``{"inputs", "parameters", "options"}`` body, omitting
        empty blocks. Returns the parsed JSON (shape varies by task).

        Args:
            model: Model repo ID to run.
            inputs: Task inputs (shape varies by task).
            task: HF pipeline tag (e.g. ``'text-generation'``,
                ``'feature-extraction'``); pins the routing path.
            parameters: Optional task-specific parameters.
            options: Optional request options (e.g. ``wait_for_model``).
            provider: Inference provider to route through (default
                ``hf-inference``).
        """
        body: dict[str, Any] = {"inputs": inputs}
        if parameters:
            body["parameters"] = parameters
        if options:
            body["options"] = options
        return await self._request(
            "POST", self._pipeline_path(provider, model, task), json_body=body
        )

    async def _infer_bytes(
        self,
        model: str,
        inputs: Any,
        task: str,
        parameters: Optional[dict[str, Any]] = None,
        provider: str = _DEFAULT_PROVIDER,
    ) -> bytes:
        """Run a binary-output task on the router; return raw bytes.

        POSTs to ``{_ROUTER_BASE}/{provider}/models/{model}/pipeline/{task}``
        with the ``{"inputs", "parameters"}`` body, omitting an empty
        ``parameters`` block, and returns the response media bytes.

        Args:
            model: Model repo ID to run.
            inputs: Task inputs (the prompt or text).
            task: HF pipeline tag (e.g. ``'text-to-image'``); pins routing.
            parameters: Optional task-specific parameters.
            provider: Inference provider to route through (default
                ``hf-inference``).
        """
        body: dict[str, Any] = {"inputs": inputs}
        if parameters:
            body["parameters"] = parameters
        return await self._request_bytes(self._pipeline_path(provider, model, task), json_body=body)

    @staticmethod
    def _to_base64(data: Union[bytes, str]) -> str:
        """Normalise binary input to a base64 string for JSON transport.

        Accepts raw ``bytes`` (base64-encoded here) or an already-encoded
        base64 ``str`` (passed through). Vision and audio tasks accept the
        media as a base64 string in the ``inputs`` field.

        Args:
            data: Raw bytes or a base64-encoded string.

        Returns:
            A base64-encoded ASCII string.
        """
        if isinstance(data, bytes):
            return base64.b64encode(data).decode("ascii")
        return data

    @staticmethod
    def _clean(values: dict[str, Any]) -> dict[str, Any]:
        """Drop ``None``-valued entries from a params/body dict.

        Keeps request payloads free of null values so the API applies its
        own defaults for unset optional parameters.
        """
        return {k: v for k, v in values.items() if v is not None}

    @staticmethod
    def _hub_search_params(
        search: Optional[str],
        author: Optional[str],
        filter: Optional[str],
        sort: Optional[str],
        direction: Optional[int],
        limit: Optional[int],
    ) -> dict[str, Any]:
        """Build shared Hub search params, omitting any that are None."""
        return HuggingFace._clean(
            {
                "search": search,
                "author": author,
                "filter": filter,
                "sort": sort,
                "direction": direction,
                "limit": limit,
            }
        )

    # ==================================================================
    # Actions -- Text generation & chat completion
    # ==================================================================

    @action("Generate text from a prompt with a hosted model")
    async def text_generation(
        self,
        model: str,
        inputs: str,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        repetition_penalty: Optional[float] = None,
        do_sample: Optional[bool] = None,
        return_full_text: Optional[bool] = None,
        wait_for_model: Optional[bool] = None,
        provider: str = _DEFAULT_PROVIDER,
    ) -> list[HFGeneratedText]:
        """Run a text-generation model via the Inference Providers router.

        Returns a list of HFGeneratedText (``generated_text`` populated).

        Args:
            model: Model repo ID (e.g. ``'gpt2'``, ``'bigscience/bloom'``).
            inputs: The prompt to continue.
            max_new_tokens: Maximum number of tokens to generate.
            temperature: Sampling temperature (higher is more random).
            top_p: Nucleus-sampling probability mass cutoff.
            top_k: Keep only the top-k most probable tokens when sampling.
            repetition_penalty: Penalty (>1.0) for repeating tokens.
            do_sample: Whether to sample instead of greedy decoding.
            return_full_text: If False, return only the newly generated
                text rather than the prompt plus continuation.
            wait_for_model: If True, block until the model is loaded
                instead of returning a 503 while it warms up.
            provider: Inference provider to route through (default
                ``'hf-inference'``); set to a partner provider (e.g.
                ``'fal-ai'``) to run heavy models elsewhere.
        """
        parameters = self._clean(
            {
                "max_new_tokens": max_new_tokens,
                "temperature": temperature,
                "top_p": top_p,
                "top_k": top_k,
                "repetition_penalty": repetition_penalty,
                "do_sample": do_sample,
                "return_full_text": return_full_text,
            }
        )
        options = {} if wait_for_model is None else {"wait_for_model": wait_for_model}

        data = await self._infer(
            model,
            inputs,
            "text-generation",
            parameters or None,
            options or None,
            provider=provider,
        )
        return p.parse_generated_rows(data, "generated_text")

    @action("Create a chat completion via the OpenAI-compatible router")
    async def chat_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        seed: Optional[int] = None,
        stop: Optional[list[str]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, dict[str, Any]]] = None,
        response_format: Optional[dict[str, Any]] = None,
    ) -> HFChatCompletion:
        """Create a chat completion using the Inference Providers router.

        Calls ``POST https://router.huggingface.co/v1/chat/completions``,
        the drop-in OpenAI-compatible endpoint. Streaming is not exposed;
        ``stream`` is always false. Append a provider/policy suffix to the
        model id to steer routing (e.g. ``':fastest'``, ``':cheapest'``,
        or ``':together'``).

        Args:
            model: Model id, optionally with a routing suffix
                (e.g. ``'openai/gpt-oss-120b'`` or ``'...:fastest'``).
            messages: OpenAI-style message dicts with ``role`` and
                ``content`` keys.
            temperature: Sampling temperature between 0 and 2.
            max_tokens: Maximum number of tokens to generate.
            top_p: Nucleus-sampling probability mass cutoff.
            frequency_penalty: Penalty in [-2, 2] for token frequency.
            presence_penalty: Penalty in [-2, 2] for token presence.
            seed: Seed for deterministic sampling, when supported.
            stop: Up to 4 sequences at which generation stops.
            tools: Tool/function definitions the model may call.
            tool_choice: ``'auto'``, ``'none'``, ``'required'``, or a
                specific ``{"type": "function", ...}`` selector.
            response_format: Structured-output spec (e.g.
                ``{"type": "json_object"}`` or a ``json_schema`` block).
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        payload.update(
            self._clean(
                {
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "top_p": top_p,
                    "frequency_penalty": frequency_penalty,
                    "presence_penalty": presence_penalty,
                    "seed": seed,
                    "stop": stop,
                    "tools": tools,
                    "tool_choice": tool_choice,
                    "response_format": response_format,
                }
            )
        )
        data = await self._request(
            "POST",
            "/v1/chat/completions",
            base=_ROUTER_BASE,
            json_body=payload,
        )
        return p.parse_chat_completion(data)

    # ==================================================================
    # Actions -- Text-to-text (summarize, translate)
    # ==================================================================

    @action("Summarize text with a hosted model")
    async def summarize(
        self,
        model: str,
        inputs: str,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        provider: str = _DEFAULT_PROVIDER,
    ) -> list[HFGeneratedText]:
        """Run a summarization model via the Inference Providers router.

        Returns a list of HFGeneratedText (``summary_text`` populated).

        Args:
            model: Summarization model repo ID (e.g. ``'facebook/bart-large-cnn'``).
            inputs: The text to summarize.
            min_length: Minimum length (in tokens) of the summary.
            max_length: Maximum length (in tokens) of the summary.
            provider: Inference provider to route through (default
                ``'hf-inference'``); set to a partner provider (e.g.
                ``'fal-ai'``) to run heavy models elsewhere.
        """
        parameters = self._clean({"min_length": min_length, "max_length": max_length})
        data = await self._infer(
            model, inputs, "summarization", parameters or None, provider=provider
        )
        return p.parse_generated_rows(data, "summary_text")

    @action("Translate text with a hosted model")
    async def translate(
        self,
        model: str,
        inputs: str,
        src_lang: Optional[str] = None,
        tgt_lang: Optional[str] = None,
        provider: str = _DEFAULT_PROVIDER,
    ) -> list[HFGeneratedText]:
        """Run a translation model via the Inference Providers router.

        Returns a list of HFGeneratedText (``translation_text`` populated).

        Args:
            model: Translation model repo ID (e.g. ``'Helsinki-NLP/opus-mt-en-fr'``).
            inputs: The text to translate.
            src_lang: Source language code, for multilingual models that
                require it (e.g. ``'en_XX'`` for mBART).
            tgt_lang: Target language code, for multilingual models that
                require it (e.g. ``'fr_XX'`` for mBART).
            provider: Inference provider to route through (default
                ``'hf-inference'``); set to a partner provider (e.g.
                ``'fal-ai'``) to run heavy models elsewhere.
        """
        parameters = self._clean({"src_lang": src_lang, "tgt_lang": tgt_lang})
        data = await self._infer(
            model, inputs, "translation", parameters or None, provider=provider
        )
        return p.parse_generated_rows(data, "translation_text")

    # ==================================================================
    # Actions -- Token-level NLP (fill-mask, classification, QA)
    # ==================================================================

    @action("Fill a masked token in text with a hosted model")
    async def fill_mask(
        self,
        model: str,
        inputs: str,
        provider: str = _DEFAULT_PROVIDER,
    ) -> list[HFFillMaskToken]:
        """Fill a masked token via the Inference Providers router.

        Returns HFFillMaskToken candidates ordered by score. The input
        must contain the model's mask token (e.g. ``<mask>`` or ``[MASK]``).

        Args:
            model: Fill-mask model repo ID (e.g.
                ``'google-bert/bert-base-uncased'``). Use the model's
                canonical (org-prefixed) ID -- the router does not resolve
                legacy aliases.
            inputs: Text containing exactly one mask token -- ``[MASK]`` for
                BERT-family models, ``<mask>`` for RoBERTa-family models.
            provider: Inference provider to route through (default
                ``'hf-inference'``); set to a partner provider (e.g.
                ``'fal-ai'``) to run heavy models elsewhere.
        """
        data = await self._infer(model, inputs, "fill-mask", provider=provider)
        return p.parse_fill_mask(data)

    @action("Classify text with a hosted model")
    async def text_classification(
        self,
        model: str,
        inputs: str,
        provider: str = _DEFAULT_PROVIDER,
    ) -> list[HFClassification]:
        """Classify text via the Inference Providers router.

        Returns HFClassification (label, score) pairs.

        Args:
            model: Classification model repo ID, e.g.
                ``'distilbert/distilbert-base-uncased-finetuned-sst-2-english'``.
            inputs: The text to classify.
            provider: Inference provider to route through (default
                ``'hf-inference'``); set to a partner provider (e.g.
                ``'fal-ai'``) to run heavy models elsewhere.
        """
        # The API nests results one level for single inputs; parse_classification flattens.
        data = await self._infer(model, inputs, "text-classification", provider=provider)
        return p.parse_classification(data)

    @action("Tag tokens in text (NER / part-of-speech)")
    async def token_classification(
        self,
        model: str,
        inputs: str,
        aggregation_strategy: Optional[str] = None,
        provider: str = _DEFAULT_PROVIDER,
    ) -> list[HFTokenClassification]:
        """Tag tokens via the Inference Providers router.

        Returns HFTokenClassification spans. Useful for named-entity
        recognition and part-of-speech tagging.

        Args:
            model: Token-classification model repo ID (e.g.
                ``'dslim/bert-base-NER'``).
            inputs: The text to tag.
            aggregation_strategy: How to group sub-word tokens into
                entities -- one of ``'none'``, ``'simple'``, ``'first'``,
                ``'average'``, or ``'max'``.
            provider: Inference provider to route through (default
                ``'hf-inference'``); set to a partner provider (e.g.
                ``'fal-ai'``) to run heavy models elsewhere.
        """
        parameters = self._clean({"aggregation_strategy": aggregation_strategy})
        data = await self._infer(
            model, inputs, "token-classification", parameters or None, provider=provider
        )
        return p.parse_token_classification(data)

    @action("Classify text against candidate labels without training")
    async def zero_shot_classification(
        self,
        model: str,
        inputs: str,
        candidate_labels: list[str],
        multi_label: Optional[bool] = None,
        provider: str = _DEFAULT_PROVIDER,
    ) -> HFZeroShotResult:
        """Run zero-shot classification via the Inference Providers router.

        Returns HFZeroShotResult; ``labels`` and ``scores`` are
        index-aligned.

        Args:
            model: Zero-shot model repo ID (e.g. ``'facebook/bart-large-mnli'``).
            inputs: The text to classify.
            candidate_labels: Candidate labels to score the text against.
            multi_label: If True, scores are independent per label rather
                than forming a single distribution.
            provider: Inference provider to route through (default
                ``'hf-inference'``); set to a partner provider (e.g.
                ``'fal-ai'``) to run heavy models elsewhere.
        """
        parameters: dict[str, Any] = {"candidate_labels": candidate_labels}
        if multi_label is not None:
            parameters["multi_label"] = multi_label

        data = await self._infer(
            model, inputs, "zero-shot-classification", parameters, provider=provider
        )
        return p.parse_zero_shot(data)

    @action("Answer a question from a context passage")
    async def question_answering(
        self,
        model: str,
        question: str,
        context: str,
        provider: str = _DEFAULT_PROVIDER,
    ) -> HFQuestionAnswer:
        """Run extractive QA via the Inference Providers router.

        Returns HFQuestionAnswer (answer span, score, offsets).

        Args:
            model: QA model repo ID (e.g. ``'deepset/roberta-base-squad2'``).
            question: The question to answer.
            context: The passage to extract the answer from.
            provider: Inference provider to route through (default
                ``'hf-inference'``); set to a partner provider (e.g.
                ``'fal-ai'``) to run heavy models elsewhere.
        """
        data = await self._infer(
            model,
            {"question": question, "context": context},
            "question-answering",
            provider=provider,
        )
        return p.parse_question_answer(data)

    @action("Answer a question about a table")
    async def table_question_answering(
        self,
        model: str,
        query: str,
        table: dict[str, list[str]],
        provider: str = _DEFAULT_PROVIDER,
    ) -> HFTableQuestionAnswer:
        """Run table QA via the Inference Providers router.

        Answers a query over a column-oriented table; returns
        HFTableQuestionAnswer.

        Args:
            model: Table-QA model repo ID (e.g. ``'google/tapas-base-finetuned-wtq'``).
            query: The question to answer about the table.
            table: The table as a dict mapping each column name to its
                list of cell values (all values are strings). Every column
                must have the same number of rows.
            provider: Inference provider to route through (default
                ``'hf-inference'``); set to a partner provider (e.g.
                ``'fal-ai'``) to run heavy models elsewhere.
        """
        data = await self._infer(
            model, {"query": query, "table": table}, "table-question-answering", provider=provider
        )
        return p.parse_table_question_answer(data)

    # ==================================================================
    # Actions -- Embeddings & similarity
    # ==================================================================

    @action("Extract embedding vectors from text", idempotent=True)
    async def feature_extraction(
        self,
        model: str,
        inputs: str,
        provider: str = _DEFAULT_PROVIDER,
    ) -> list[list[float]]:
        """Extract embeddings via the Inference Providers router.

        Embedding shape is model-specific, so raw nested float lists are
        returned. A flat ``list[float]`` is normalised to a single-row
        ``list[list[float]]`` for a consistent return type.

        Args:
            model: Embedding model repo ID, e.g.
                ``'sentence-transformers/all-MiniLM-L6-v2'``.
            inputs: The text to embed.
            provider: Inference provider to route through (default
                ``'hf-inference'``); set to a partner provider (e.g.
                ``'fal-ai'``) to run heavy models elsewhere.
        """
        data = await self._infer(model, inputs, "feature-extraction", provider=provider)
        if isinstance(data, list) and data and isinstance(data[0], (int, float)):
            return [[float(x) for x in data]]
        return data

    @action("Score a sentence against candidates for similarity", idempotent=True)
    async def sentence_similarity(
        self,
        model: str,
        source_sentence: str,
        sentences: list[str],
        provider: str = _DEFAULT_PROVIDER,
    ) -> list[float]:
        """Score sentence similarity via the Inference Providers router.

        Returns a similarity score per candidate, index-aligned with
        ``sentences`` (cosine similarity in [0, 1], higher is more similar).

        Args:
            model: Sentence-similarity model repo ID, e.g.
                ``'sentence-transformers/all-MiniLM-L6-v2'``.
            source_sentence: The sentence to compare against.
            sentences: Candidate sentences to score for similarity.
            provider: Inference provider to route through (default
                ``'hf-inference'``); set to a partner provider (e.g.
                ``'fal-ai'``) to run heavy models elsewhere.
        """
        data = await self._infer(
            model,
            {"source_sentence": source_sentence, "sentences": sentences},
            "sentence-similarity",
            provider=provider,
        )
        if isinstance(data, list):
            return [float(x) for x in data]
        return []

    # ==================================================================
    # Actions -- Vision (text-to-image, image-to-text, classification, ...)
    # ==================================================================

    @action("Generate an image from a text prompt")
    async def text_to_image(
        self,
        model: str,
        inputs: str,
        negative_prompt: Optional[str] = None,
        guidance_scale: Optional[float] = None,
        num_inference_steps: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        seed: Optional[int] = None,
        provider: str = _DEFAULT_PROVIDER,
    ) -> bytes:
        """Generate an image via the Inference Providers router.

        Returns the rendered image as raw bytes (e.g. a PNG), unchanged
        for the caller to save or re-encode. Heavy diffusion models are
        often best routed to a partner provider via ``provider``.

        Args:
            model: Text-to-image model repo ID (e.g.
                ``'black-forest-labs/FLUX.1-schnell'``).
            inputs: The text prompt describing the desired image.
            negative_prompt: A prompt describing what to avoid.
            guidance_scale: How strongly to follow the prompt (higher is
                closer but may over-saturate).
            num_inference_steps: Number of denoising steps (higher is
                usually higher quality but slower).
            width: Output image width in pixels.
            height: Output image height in pixels.
            seed: Seed for the random number generator (for reproducibility).
            provider: Inference provider to route through (default
                ``'hf-inference'``); set to a partner provider (e.g.
                ``'fal-ai'``) to run heavy models elsewhere.
        """
        parameters = self._clean(
            {
                "negative_prompt": negative_prompt,
                "guidance_scale": guidance_scale,
                "num_inference_steps": num_inference_steps,
                "width": width,
                "height": height,
                "seed": seed,
            }
        )
        return await self._infer_bytes(
            model, inputs, "text-to-image", parameters or None, provider=provider
        )

    @action("Generate a caption for an image")
    async def image_to_text(
        self,
        model: str,
        image: Union[bytes, str],
        provider: str = _DEFAULT_PROVIDER,
    ) -> list[HFGeneratedText]:
        """Caption an image via the Inference Providers router.

        Returns HFGeneratedText (``generated_text`` populated).

        Args:
            model: Image-to-text model repo ID (e.g.
                ``'Salesforce/blip-image-captioning-large'``).
            image: The image to caption, as raw ``bytes`` or a
                base64-encoded string.
            provider: Inference provider to route through (default
                ``'hf-inference'``); set to a partner provider (e.g.
                ``'fal-ai'``) to run heavy models elsewhere.
        """
        data = await self._infer(model, self._to_base64(image), "image-to-text", provider=provider)
        return p.parse_generated_rows(data, "generated_text")

    @action("Classify an image into labels")
    async def image_classification(
        self,
        model: str,
        image: Union[bytes, str],
        top_k: Optional[int] = None,
        provider: str = _DEFAULT_PROVIDER,
    ) -> list[HFClassification]:
        """Classify an image via the Inference Providers router.

        Returns HFClassification (label, score) pairs.

        Args:
            model: Image-classification model repo ID (e.g.
                ``'google/vit-base-patch16-224'``).
            image: The image to classify, as raw ``bytes`` or a
                base64-encoded string.
            top_k: Limit the output to the top-k most probable classes.
            provider: Inference provider to route through (default
                ``'hf-inference'``); set to a partner provider (e.g.
                ``'fal-ai'``) to run heavy models elsewhere.
        """
        parameters = self._clean({"top_k": top_k})
        data = await self._infer(
            model,
            self._to_base64(image),
            "image-classification",
            parameters or None,
            provider=provider,
        )
        return p.parse_classification(data)

    @action("Detect objects and bounding boxes in an image")
    async def object_detection(
        self,
        model: str,
        image: Union[bytes, str],
        threshold: Optional[float] = None,
        provider: str = _DEFAULT_PROVIDER,
    ) -> list[HFObjectDetection]:
        """Detect objects via the Inference Providers router.

        Returns HFObjectDetection rows with bounding boxes.

        Args:
            model: Object-detection model repo ID (e.g.
                ``'facebook/detr-resnet-50'``).
            image: The image to analyse, as raw ``bytes`` or a
                base64-encoded string.
            threshold: Minimum confidence required to report a detection.
            provider: Inference provider to route through (default
                ``'hf-inference'``); set to a partner provider (e.g.
                ``'fal-ai'``) to run heavy models elsewhere.
        """
        parameters = self._clean({"threshold": threshold})
        data = await self._infer(
            model, self._to_base64(image), "object-detection", parameters or None, provider=provider
        )
        return p.parse_object_detection(data)

    @action("Segment an image into labelled masks")
    async def image_segmentation(
        self,
        model: str,
        image: Union[bytes, str],
        mask_threshold: Optional[float] = None,
        threshold: Optional[float] = None,
        subtask: Optional[str] = None,
        provider: str = _DEFAULT_PROVIDER,
    ) -> list[HFImageSegment]:
        """Segment an image via the Inference Providers router.

        Returns HFImageSegment rows; each segment carries a base64-encoded
        black-and-white PNG mask.

        Args:
            model: Image-segmentation model repo ID (e.g.
                ``'facebook/mask2former-swin-large-coco-panoptic'``).
            image: The image to segment, as raw ``bytes`` or a
                base64-encoded string.
            mask_threshold: Threshold for binarising predicted masks.
            threshold: Probability threshold to filter predicted masks.
            subtask: Segmentation subtask -- ``'instance'``,
                ``'panoptic'``, or ``'semantic'``.
            provider: Inference provider to route through (default
                ``'hf-inference'``); set to a partner provider (e.g.
                ``'fal-ai'``) to run heavy models elsewhere.
        """
        parameters = self._clean(
            {
                "mask_threshold": mask_threshold,
                "threshold": threshold,
                "subtask": subtask,
            }
        )
        data = await self._infer(
            model,
            self._to_base64(image),
            "image-segmentation",
            parameters or None,
            provider=provider,
        )
        return p.parse_image_segments(data)

    # ==================================================================
    # Actions -- Audio (ASR, classification, text-to-speech)
    # ==================================================================

    @action("Transcribe speech audio to text")
    async def automatic_speech_recognition(
        self,
        model: str,
        audio: Union[bytes, str],
        return_timestamps: Optional[bool] = None,
        provider: str = _DEFAULT_PROVIDER,
    ) -> HFTranscription:
        """Transcribe speech via the Inference Providers router.

        Runs an ASR (speech-to-text) model; returns HFTranscription.

        Args:
            model: ASR model repo ID (e.g. ``'openai/whisper-large-v3'``).
            audio: The audio to transcribe, as raw ``bytes`` or a
                base64-encoded string.
            return_timestamps: If True, also return per-chunk timestamps.
            provider: Inference provider to route through (default
                ``'hf-inference'``); set to a partner provider (e.g.
                ``'fal-ai'``) to run heavy models elsewhere.
        """
        parameters = self._clean({"return_timestamps": return_timestamps})
        data = await self._infer(
            model,
            self._to_base64(audio),
            "automatic-speech-recognition",
            parameters or None,
            provider=provider,
        )
        return p.parse_transcription(data)

    @action("Classify audio into labels")
    async def audio_classification(
        self,
        model: str,
        audio: Union[bytes, str],
        top_k: Optional[int] = None,
        provider: str = _DEFAULT_PROVIDER,
    ) -> list[HFClassification]:
        """Classify audio via the Inference Providers router.

        Returns HFClassification (label, score) pairs.

        Args:
            model: Audio-classification model repo ID (e.g.
                ``'superb/hubert-large-superb-er'``).
            audio: The audio to classify, as raw ``bytes`` or a
                base64-encoded string.
            top_k: Limit the output to the top-k most probable classes.
            provider: Inference provider to route through (default
                ``'hf-inference'``); set to a partner provider (e.g.
                ``'fal-ai'``) to run heavy models elsewhere.
        """
        parameters = self._clean({"top_k": top_k})
        data = await self._infer(
            model,
            self._to_base64(audio),
            "audio-classification",
            parameters or None,
            provider=provider,
        )
        return p.parse_classification(data)

    @action("Synthesize speech audio from text")
    async def text_to_speech(
        self,
        model: str,
        inputs: str,
        provider: str = _DEFAULT_PROVIDER,
    ) -> bytes:
        """Synthesize speech via the Inference Providers router.

        Returns the audio as raw bytes (e.g. a FLAC or WAV payload),
        unchanged.

        Args:
            model: Text-to-speech model repo ID (e.g.
                ``'espnet/kan-bayashi_ljspeech_vits'``).
            inputs: The text to synthesize into speech.
            provider: Inference provider to route through (default
                ``'hf-inference'``); set to a partner provider (e.g.
                ``'fal-ai'``) to run heavy models elsewhere.
        """
        return await self._infer_bytes(model, inputs, "text-to-speech", provider=provider)

    # ==================================================================
    # Actions -- Hub: models
    # ==================================================================

    @action("Search models on the Hugging Face Hub", idempotent=True)
    async def list_models(
        self,
        search: Optional[str] = None,
        author: Optional[str] = None,
        filter: Optional[str] = None,
        sort: Optional[str] = None,
        direction: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[HFModelInfo]:
        """List or search models on the Hub; returns HFModelInfo metadata.

        Args:
            search: Free-text search query over model IDs.
            author: Restrict to a given author/organisation.
            filter: Filter tag (e.g. ``'text-classification'``, ``'pytorch'``).
            sort: Field to sort by (e.g. ``'downloads'``, ``'likes'``).
            direction: Sort direction; ``-1`` for descending.
            limit: Maximum number of models to return.
        """
        params = self._hub_search_params(search, author, filter, sort, direction, limit)
        data = await self._request("GET", "/models", base=_HUB_BASE, params=params or None)
        rows = data if isinstance(data, list) else []
        return [p.parse_model_info(m) for m in rows]

    @action("Get metadata for a model on the Hub", idempotent=True)
    async def get_model(self, model_id: str) -> HFModelInfo:
        """Retrieve metadata for a single model on the Hub (HFModelInfo).

        Args:
            model_id: Model repo ID (e.g. ``'bert-base-uncased'``).
        """
        data = await self._request("GET", f"/models/{model_id}", base=_HUB_BASE)
        return p.parse_model_info(data)

    # ==================================================================
    # Actions -- Hub: datasets
    # ==================================================================

    @action("Search datasets on the Hugging Face Hub", idempotent=True)
    async def list_datasets(
        self,
        search: Optional[str] = None,
        author: Optional[str] = None,
        filter: Optional[str] = None,
        sort: Optional[str] = None,
        direction: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[HFDatasetInfo]:
        """List or search datasets on the Hub; returns HFDatasetInfo metadata.

        Args:
            search: Free-text search query over dataset IDs.
            author: Restrict to a given author/organisation.
            filter: Filter tag (e.g. ``'task_categories:translation'``).
            sort: Field to sort by (e.g. ``'downloads'``, ``'likes'``).
            direction: Sort direction; ``-1`` for descending.
            limit: Maximum number of datasets to return.
        """
        params = self._hub_search_params(search, author, filter, sort, direction, limit)
        data = await self._request("GET", "/datasets", base=_HUB_BASE, params=params or None)
        rows = data if isinstance(data, list) else []
        return [p.parse_dataset_info(d) for d in rows]

    @action("Get metadata for a dataset on the Hub", idempotent=True)
    async def get_dataset(self, dataset_id: str) -> HFDatasetInfo:
        """Retrieve metadata for a single dataset on the Hub (HFDatasetInfo).

        Args:
            dataset_id: Dataset repo ID (e.g. ``'squad'``).
        """
        data = await self._request("GET", f"/datasets/{dataset_id}", base=_HUB_BASE)
        return p.parse_dataset_info(data)

    # ==================================================================
    # Actions -- Hub: Spaces
    # ==================================================================

    @action("Search Spaces on the Hugging Face Hub", idempotent=True)
    async def list_spaces(
        self,
        search: Optional[str] = None,
        author: Optional[str] = None,
        filter: Optional[str] = None,
        sort: Optional[str] = None,
        direction: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[HFSpaceInfo]:
        """List or search Spaces on the Hub; returns HFSpaceInfo metadata.

        Args:
            search: Free-text search query over Space IDs.
            author: Restrict to a given author/organisation.
            filter: Filter tag (e.g. ``'gradio'``, ``'streamlit'``).
            sort: Field to sort by (e.g. ``'likes'``).
            direction: Sort direction; ``-1`` for descending.
            limit: Maximum number of Spaces to return.
        """
        params = self._hub_search_params(search, author, filter, sort, direction, limit)
        data = await self._request("GET", "/spaces", base=_HUB_BASE, params=params or None)
        rows = data if isinstance(data, list) else []
        return [p.parse_space_info(s) for s in rows]

    @action("Get metadata for a Space on the Hub", idempotent=True)
    async def get_space(self, space_id: str) -> HFSpaceInfo:
        """Retrieve metadata for a single Space on the Hub (HFSpaceInfo).

        Args:
            space_id: Space repo ID (e.g. ``'huggingface/diffuse-the-rest'``).
        """
        data = await self._request("GET", f"/spaces/{space_id}", base=_HUB_BASE)
        return p.parse_space_info(data)

    # ==================================================================
    # Actions -- Hub: identity
    # ==================================================================

    @action("Get the authenticated Hugging Face identity", idempotent=True)
    async def whoami(self) -> HFWhoAmI:
        """Return the identity for the supplied token (HFWhoAmI).

        Useful as a lightweight token-validity check.
        """
        data = await self._request("GET", "/whoami-v2", base=_HUB_BASE)
        return p.parse_whoami(data)
