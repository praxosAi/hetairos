"""Async HTTP client for the mypraxos-backend ``/internal/praxos/*`` bridge.

All calls go through mypraxos-backend (subnet-trusted) which forwards to
search-service or trigger-ingestor via its in-process ``PraxosGraphClient``.
There is no API key — auth is handled by the Function App's network rules.

Construction:
    client = PraxosClient(user_id=..., environment_id=...)

``user_id`` and ``environment_id`` are bound at construction so each method
call automatically includes them in the request body / query string.
"""

import json
import mimetypes
import os
import time
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import httpx

try:
    from bson import ObjectId
except ImportError:  # bson is a transitive dep but guard anyway
    ObjectId = None  # type: ignore[assignment]


class _PraxosJSONEncoder(json.JSONEncoder):
    """Handles types httpx's default json= encoder rejects: datetime, ObjectId."""

    def default(self, o: Any) -> Any:
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if ObjectId is not None and isinstance(o, ObjectId):
            return str(o)
        return super().default(o)

from src.config.settings import settings
from src.utils.logging import (
    praxos_logger,
    log_praxos_query_started,
    log_praxos_query_completed,
    log_praxos_query_failed,
    log_praxos_search_anchors_started,
    log_praxos_search_anchors_completed,
    log_praxos_search_anchors_failed,
    log_praxos_add_integration_started,
    log_praxos_add_integration_completed,
    log_praxos_add_integration_failed,
    log_praxos_file_upload_started,
    log_praxos_file_upload_completed,
    log_praxos_file_upload_failed,
    log_praxos_get_integrations_started,
    log_praxos_get_integrations_completed,
    log_praxos_get_integrations_failed,
    log_praxos_api_error,
    log_praxos_performance_warning,
    log_praxos_context_details,
)


class PraxosBridgeError(Exception):
    """Raised when the backend bridge returns a non-2xx response."""

    def __init__(self, status_code: int, message: str, payload: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.payload = payload or {}


class PraxosClient:
    """HTTP client that targets mypraxos-backend's ``/api/internal/praxos/*`` routes."""

    def __init__(
        self,
        user_id: str,
        environment_id: str,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
    ):
        self.user_id = str(user_id)
        self.environment_id = str(environment_id)
        resolved = base_url or settings.MYPRAXOS_BACKEND_URL
        if not resolved:
            raise RuntimeError(
                "MYPRAXOS_BACKEND_URL is not configured (set env var or pass base_url)"
            )
        self.base_url = resolved.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    # Compatibility shim — older callers expected a truthy `.env` to know
    # the client was initialized. Kept so we don't have to touch every
    # callsite that does `if praxos.env: ...`.
    @property
    def env(self) -> bool:
        return True

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "PraxosClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/internal/praxos/{path.lstrip('/')}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[dict] = None,
        params: Optional[dict] = None,
        files: Optional[dict] = None,
        data: Optional[dict] = None,
    ) -> Any:
        kwargs: Dict[str, Any] = {}
        if json_body is not None:
            # httpx's default `json=` chokes on datetime/ObjectId. Pre-encode through
            # our JSONEncoder so callers can pass these types straight through.
            kwargs["content"] = json.dumps(json_body, cls=_PraxosJSONEncoder).encode("utf-8")
            kwargs["headers"] = {"Content-Type": "application/json"}
        if params is not None:
            kwargs["params"] = params
        if files is not None:
            kwargs["files"] = files
        if data is not None:
            kwargs["data"] = data

        resp = await self._client.request(method, self._url(path), **kwargs)
        if resp.status_code >= 400:
            try:
                payload = resp.json()
            except ValueError:
                payload = {"error": resp.text}
            raise PraxosBridgeError(
                resp.status_code,
                payload.get("error", "upstream error"),
                payload,
            )
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text

    # ------------------------------------------------------------------
    # Source creation: conversation / business-data / file
    # ------------------------------------------------------------------

    async def add_conversation(
        self,
        user_id: str,
        source: str,
        metadata: Dict = None,
        user_record: Dict[str, Any] = None,
        messages: List[Dict] = None,
        conversation_id: str = "no_conversation_id",
    ):
        """Add a conversation to Praxos memory (POST /sources/conversation)."""
        start_time = time.time()
        praxos_logger.info(
            f"Adding conversation for user {user_id} with source {source}"
        )
        try:
            reformatted: List[Dict[str, Any]] = []
            for message in messages or []:
                ts = message["timestamp"]
                if not isinstance(ts, str):
                    ts = ts.isoformat()
                if message["role"] == "user":
                    first = (user_record or {}).get("first_name", "")
                    last = (user_record or {}).get("last_name", "")
                    content_enriched = (
                        f"Message sent at {ts} by {first} {last}: {message['content']}"
                    )
                else:
                    content_enriched = (
                        f"Message sent at {ts} by Praxos Assistant: {message['content']}"
                    )
                reformatted.append(
                    {
                        "role": message["role"],
                        "content": content_enriched,
                        "timestamp": ts,
                    }
                )

            unique_name = f"Message_{user_id}_{source}_{uuid.uuid4().hex}"
            body = {
                "user_id": self.user_id,
                "environment_id": self.environment_id,
                "messages": reformatted,
                "name": unique_name,
                "description": f"message from user with conversation id {conversation_id}",
                "metadata": metadata or {},
            }
            result = await self._request("POST", "sources/conversation", json_body=body)

            duration = time.time() - start_time
            praxos_logger.info(
                f"Conversation added for user {user_id} with source {source} in {duration:.2f}s"
            )
            return {"success": True, "id": result.get("id") if result else None, "source": result}
        except PraxosBridgeError as e:
            praxos_logger.error(
                f"Error adding conversation (status={e.status_code}): {e.message}"
            )
            return {"error": e.message}
        except Exception as e:
            praxos_logger.error(f"Error adding conversation: {e}", exc_info=True)
            return {"error": str(e)}

    # Backwards compatibility alias
    async def add_message(
        self,
        user_id: str,
        content: str,
        source: str,
        metadata: Dict = None,
        user_record: Dict[str, Any] = None,
    ):
        return await self.add_conversation(user_id, content, source, metadata, user_record)

    async def add_email_conversation(
        self,
        messages: List,
        name: str,
        description: str,
        metadata: Dict = None,
        user_record: Dict[str, Any] = None,
    ):
        """Add an email as a conversation (POST /sources/conversation)."""
        start_time = time.time()
        try:
            normalized: List[Dict[str, Any]] = []
            for m in messages or []:
                if isinstance(m, dict):
                    msg = dict(m)
                else:
                    ts = getattr(m, "timestamp", None)
                    msg = {
                        "role": getattr(m, "role", "user"),
                        "content": getattr(m, "content", ""),
                        "timestamp": ts,
                    }
                if msg.get("timestamp") and not isinstance(msg["timestamp"], str):
                    msg["timestamp"] = msg["timestamp"].isoformat()
                normalized.append(msg)

            unique_name = f"{name}_{uuid.uuid4().hex[:8]}"
            body = {
                "user_id": self.user_id,
                "environment_id": self.environment_id,
                "messages": normalized,
                "name": unique_name,
                "description": description,
                "metadata": metadata or {},
            }
            result = await self._request("POST", "sources/conversation", json_body=body)
            duration = time.time() - start_time
            source_id = result.get("id") if result else None
            praxos_logger.info(
                f"✅ Email conversation added in {duration:.2f}s (ID: {source_id})"
            )
            return {"success": True, "id": source_id, "source": result}
        except PraxosBridgeError as e:
            praxos_logger.error(f"❌ Email conversation add failed: {e.message}")
            return {"error": e.message}
        except Exception as e:
            praxos_logger.error(f"❌ Email conversation add failed: {e}")
            return {"error": str(e)}

    async def add_integration_capability(
        self, user_id: str, integration_type: str, capabilities: List[str]
    ):
        """Add integration as business-data (POST /sources/business-data)."""
        start_time = time.time()
        log_praxos_add_integration_started(user_id, integration_type, capabilities)
        try:
            integration_data = {
                "type": "schema:Integration",
                "user_id": user_id,
                "integration_type": integration_type,
                "capabilities": capabilities,
                "status": "active",
                "added_at": datetime.utcnow().isoformat(),
            }
            body = {
                "user_id": self.user_id,
                "environment_id": self.environment_id,
                "data": integration_data,
                "name": f"{integration_type}_integration_{user_id}",
                "description": f"{integration_type.title()} integration for user {user_id}",
                "root_entity_type": "schema:Integration",
            }
            result = await self._request("POST", "sources/business-data", json_body=body)
            duration = time.time() - start_time
            integration_id = result.get("id") if result else None
            log_praxos_add_integration_completed(
                user_id, integration_type, integration_id, duration
            )
            return result
        except PraxosBridgeError as e:
            duration = time.time() - start_time
            log_praxos_add_integration_failed(user_id, integration_type, e, duration)
            log_praxos_api_error(
                "add_integration_capability", e.status_code, e.message, e.payload
            )
            return {"error": e.message}
        except Exception as e:
            duration = time.time() - start_time
            log_praxos_add_integration_failed(user_id, integration_type, e, duration)
            return {"error": str(e)}

    async def add_business_data(
        self,
        data: Dict[str, Any],
        name: str = None,
        description: str = None,
        root_entity_type: str = "schema:Thing",
        metadata: Dict[str, Any] = None,
    ):
        """Add business data (POST /sources/business-data)."""
        start_time = time.time()
        try:
            body = {
                "user_id": self.user_id,
                "environment_id": self.environment_id,
                "data": data,
                "name": name,
                "description": description,
                "root_entity_type": root_entity_type,
                "metadata": metadata or {},
            }
            result = await self._request("POST", "sources/business-data", json_body=body)
            duration = time.time() - start_time
            praxos_logger.info(f"✅ Business data added in {duration:.2f}s")
            return {
                "success": True,
                "id": result.get("id") if result else None,
                "source": result,
            }
        except PraxosBridgeError as e:
            praxos_logger.error(f"❌ Business data add failed: {e.message}")
            return {"error": e.message}
        except Exception as e:
            praxos_logger.error(f"❌ Business data add failed: {e}")
            return {"error": str(e)}

    async def _post_file(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Any:
        ct = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        files = {"files": (filename, file_bytes, ct)}
        form: Dict[str, Any] = {}
        if name:
            form["name"] = name
        if description:
            form["description"] = description
        if metadata:
            form["metadata"] = json.dumps(metadata)
        params = {"user_id": self.user_id, "environment_id": self.environment_id}
        return await self._request(
            "POST", "sources/file", params=params, files=files, data=form
        )

    async def add_file(
        self,
        file_path: str,
        name: str,
        description: str = None,
        metadata: dict = None,
    ):
        """Add a file from disk (POST /sources/file, multipart)."""
        start_time = time.time()
        log_praxos_file_upload_started(file_path, name, description)
        try:
            with open(file_path, "rb") as fh:
                file_bytes = fh.read()
            filename = os.path.basename(file_path)
            result = await self._post_file(
                file_bytes,
                filename,
                content_type=mimetypes.guess_type(filename)[0],
                name=name,
                description=description or f"File: {name}",
                metadata=metadata,
            )
            duration = time.time() - start_time
            file_id = result.get("id") if result else None
            log_praxos_file_upload_completed(file_path, name, file_id, duration)
            return {"success": True, "id": file_id, "source": result}
        except PraxosBridgeError as e:
            duration = time.time() - start_time
            log_praxos_file_upload_failed(file_path, name, e, duration)
            log_praxos_api_error("add_file", e.status_code, e.message, e.payload)
            return {"error": f"File upload failed: {e.message}"}
        except Exception as e:
            duration = time.time() - start_time
            log_praxos_file_upload_failed(file_path, name, e, duration)
            return {"error": f"File upload failed: {str(e)}"}

    async def add_file_content(
        self,
        file_data: bytes,
        filename: str,
        mimetype: str = None,
        description: str = None,
    ):
        """Add file content directly (POST /sources/file, multipart)."""
        try:
            if mimetype and mimetype.startswith("text/"):
                try:
                    content = file_data.decode("utf-8")
                    return await self.add_conversation(
                        user_id="system",
                        source="file_ingestion",
                        metadata={
                            "filename": filename,
                            "mimetype": mimetype,
                            "file_size": len(file_data),
                            "content_type": "text_file",
                        },
                        messages=[
                            {
                                "role": "user",
                                "content": f"File content from {filename}:\n{content}",
                                "timestamp": datetime.utcnow().isoformat(),
                            }
                        ],
                    )
                except UnicodeDecodeError:
                    pass

            try:
                result = await self._post_file(
                    file_data,
                    filename,
                    content_type=mimetype,
                    name=filename,
                    description=description or f"Email attachment: {filename}",
                )
                return {
                    "success": True,
                    "id": result.get("id") if result else None,
                    "source": result,
                }
            except PraxosBridgeError as upload_error:
                file_metadata = {
                    "type": "file_content",
                    "filename": filename,
                    "mimetype": mimetype,
                    "file_size": len(file_data),
                    "description": description,
                    "added_at": datetime.utcnow().isoformat(),
                    "status": "content_available_but_not_uploaded",
                    "upload_error": upload_error.message,
                }
                return await self.add_business_data(
                    data=file_metadata,
                    name=f"file_content_{filename}",
                    description=description or f"File content metadata: {filename}",
                )
        except Exception as e:
            praxos_logger.error(f"Error adding file content to Praxos: {e}")
            return {"error": f"File content upload failed: {str(e)}"}

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search_from_anchors(
        self,
        user_id: str,
        query: str,
        max_hops: int = 3,
        top_k: int = 3,
        node_types: List[str] = None,
    ):
        """Anchor search via POST /search."""
        start_time = time.time()
        anchors = [{"value": user_id}]
        if (
            hasattr(settings, "TEST_EMAIL_LUCAS")
            and settings.TEST_EMAIL_LUCAS
            and settings.TEST_EMAIL_LUCAS.strip()
        ):
            anchors.append({"value": settings.TEST_EMAIL_LUCAS})

        node_type = node_types[0] if node_types else "schema:Capability"
        log_praxos_search_anchors_started(
            user_id, query, anchors, max_hops, top_k, node_types
        )
        try:
            search_query = {
                "query": query,
                "top_k": top_k,
                "node_type": node_type,
                "known_anchors": anchors,
                "anchor_max_hops": max_hops,
            }
            body = {"search_query": search_query, "user_id": self.user_id}
            results = await self._request("POST", "search", json_body=body)
            results = results if isinstance(results, list) else (results or [])

            duration = time.time() - start_time
            results_count = len(results)
            log_praxos_search_anchors_completed(
                user_id, query, results_count, duration, len(anchors)
            )
            log_praxos_context_details(user_id, query, results)
            if duration > 5.0:
                log_praxos_performance_warning("search_from_anchors", duration, 5.0)
            return {"success": True, "results": results, "count": results_count}
        except PraxosBridgeError as e:
            duration = time.time() - start_time
            log_praxos_search_anchors_failed(user_id, query, e, duration)
            log_praxos_api_error("search_from_anchors", e.status_code, e.message, e.payload)
            return {"error": e.message}
        except Exception as e:
            duration = time.time() - start_time
            log_praxos_search_anchors_failed(user_id, query, e, duration)
            return {"error": str(e)}

    async def get_user_integrations(self, user_id: str):
        """Composite: anchor-search → fetch_graph_nodes."""
        start_time = time.time()
        log_praxos_get_integrations_started(user_id)
        try:
            results = await self.search_from_anchors(
                user_id=user_id,
                query="find all active integrations for this user",
                max_hops=2,
                top_k=10,
            )
            integration_nodes: List[Any] = []
            nodes_to_id = set()
            raw = results.get("results") if isinstance(results, dict) else results
            for result in raw or []:
                for conn in result.get("anchor_connections", []) if isinstance(result, dict) else []:
                    for node in conn.get("path_nodes", []):
                        if node.get("type") == "schema:Integration":
                            nodes_to_id.add(node["id"])

            if nodes_to_id:
                fetch_body = {
                    "node_ids": list(nodes_to_id),
                    "user_id": self.user_id,
                    "environment_id": self.environment_id,
                }
                integration_nodes = await self._request(
                    "POST", "extract/fetch-graph-nodes", json_body=fetch_body
                ) or []

            duration = time.time() - start_time
            log_praxos_get_integrations_completed(user_id, len(integration_nodes), duration)
            return integration_nodes
        except PraxosBridgeError as e:
            duration = time.time() - start_time
            log_praxos_get_integrations_failed(user_id, e, duration)
            log_praxos_api_error("get_user_integrations", e.status_code, e.message, e.payload)
            return {"error": e.message}
        except Exception as e:
            duration = time.time() - start_time
            log_praxos_get_integrations_failed(user_id, e, duration)
            return {"error": str(e)}

    async def query_memory(self, user_id: str, query: str, context_type: str = None):
        start_time = time.time()
        log_praxos_query_started(user_id, query, "query_memory")
        try:
            result = await self.search_from_anchors(user_id, query)
            duration = time.time() - start_time
            results_count = len(result.get("results", [])) if isinstance(result, dict) else 0
            log_praxos_query_completed(user_id, query, results_count, duration, "query_memory")
            return result
        except Exception as e:
            duration = time.time() - start_time
            log_praxos_query_failed(user_id, query, e, duration, "query_memory")
            raise

    async def search_memory(
        self,
        query: str,
        top_k: int = 5,
        search_modality: str = "node_vec",
        exclude_seen: List[str] = None,
    ):
        """Direct search via POST /search with score filtering."""
        start_time = time.time()
        log_praxos_query_started("system", query, "search_memory")
        try:
            search_query = {
                "query": query,
                "top_k": top_k,
                "search_modality": search_modality,
                "exclude_nodes": exclude_seen or [],
            }
            body = {"search_query": search_query, "user_id": self.user_id}
            results = await self._request("POST", "search", json_body=body)
            duration = time.time() - start_time

            qualified_results: List[Dict[str, Any]] = []
            extracted_sentences: List[str] = []
            source_ids: set = set()
            if isinstance(results, list):
                for result in results:
                    score = result.get("score", 0)
                    if score > 0.7:
                        qualified_results.append(
                            {
                                "text": result.get("sentence", ""),
                                "node_id": result.get("node_id"),
                            }
                        )
                        sentence = result.get("sentence", "")
                        source_ids.add(result.get("source_id", ""))
                        if sentence:
                            extracted_sentences.append(sentence)

            log_praxos_query_completed(
                "system", query, len(qualified_results), duration, "search_memory"
            )
            return {
                "success": True,
                "source_ids": source_ids,
                "results": qualified_results,
                "sentences": extracted_sentences,
                "count": len(qualified_results),
                "sentences_count": len(extracted_sentences),
                "raw_results": results,
            }
        except PraxosBridgeError as e:
            duration = time.time() - start_time
            log_praxos_query_failed("system", query, e, duration, "search_memory")
            log_praxos_api_error("search_memory", e.status_code, e.message, e.payload)
            return {"error": e.message}
        except Exception as e:
            duration = time.time() - start_time
            log_praxos_query_failed("system", query, e, duration, "search_memory")
            return {"error": str(e)}

    async def file_search(
        self,
        query: str,
        top_k: int = 10,
        source_id: Optional[str] = None,
    ):
        """Semantic search over file content chunks (the embedding-only path).

        Hits the per-user ``{user_id}_files`` Qdrant collection populated by
        ``sync_file_for_semantic_search``. Returns chunk-level matches grouped
        by source_id so the caller can pick a file to retrieve.
        """
        start_time = time.time()
        log_praxos_query_started("system", query, "file_search")
        try:
            body: Dict[str, Any] = {
                "query": query,
                "user_id": self.user_id,
                "top_k": top_k,
            }
            if source_id:
                body["source_id"] = source_id
            if self.environment_id:
                body["environment_id"] = self.environment_id
            hits = await self._request("POST", "search/file", json_body=body)
            duration = time.time() - start_time

            if not isinstance(hits, list):
                hits = []

            grouped: Dict[str, Dict[str, Any]] = {}
            for hit in hits:
                src = hit.get("source_id") or ""
                existing = grouped.get(src)
                if existing is None or hit.get("score", 0) > existing.get("top_score", 0):
                    grouped[src] = {
                        "source_id": src or None,
                        "file_name": hit.get("file_name"),
                        "description": hit.get("description"),
                        "top_score": hit.get("score", 0),
                        "best_snippet": hit.get("text_snippet"),
                        "best_chunk_index": hit.get("chunk_index"),
                        "total_chunks": hit.get("total_chunks"),
                        "environment_id": hit.get("environment_id"),
                        "timestamp": hit.get("timestamp"),
                    }
                grouped[src].setdefault("chunks", []).append(
                    {
                        "score": hit.get("score"),
                        "chunk_index": hit.get("chunk_index"),
                        "text_snippet": hit.get("text_snippet"),
                    }
                )

            files = sorted(
                grouped.values(), key=lambda f: f.get("top_score", 0), reverse=True
            )
            log_praxos_query_completed(
                "system", query, len(files), duration, "file_search"
            )
            return {
                "success": True,
                "files": files,
                "raw_hits": hits,
                "count": len(files),
                "hit_count": len(hits),
            }
        except PraxosBridgeError as e:
            duration = time.time() - start_time
            log_praxos_query_failed("system", query, e, duration, "file_search")
            log_praxos_api_error("file_search", e.status_code, e.message, e.payload)
            return {"error": e.message}
        except Exception as e:
            duration = time.time() - start_time
            log_praxos_query_failed("system", query, e, duration, "file_search")
            return {"error": str(e)}

    async def extract_intelligent(
        self,
        query: str,
        strategy: str = "entity_extraction",
        max_results: int = 20,
    ):
        start_time = time.time()
        praxos_logger.info(
            f"Starting intelligent extraction: query='{query}', strategy={strategy}"
        )
        try:
            body = {
                "query": query,
                "user_id": self.user_id,
                "environment_id": self.environment_id,
                "strategy": strategy,
                "max_results": max_results,
            }
            result = await self._request("POST", "extract/intelligent", json_body=body)
            duration = time.time() - start_time
            hits_count = len(result.get("hits", [])) if isinstance(result, dict) else 0
            praxos_logger.info(
                f"Intelligent extraction completed in {duration:.2f}s, found {hits_count} items"
            )
            return result
        except PraxosBridgeError as e:
            praxos_logger.error(f"Intelligent extraction failed: {e.message}")
            return {"error": e.message}
        except Exception as e:
            praxos_logger.error(f"Intelligent extraction failed: {e}")
            return {"error": str(e)}

    async def get_nodes_by_type(
        self,
        type_name: str,
        include_literals: bool = True,
        max_results: int = 100,
    ):
        """List nodes of a given type via POST /search/type."""
        start_time = time.time()
        praxos_logger.info(f"Getting nodes by type: {type_name}")
        try:
            body = {
                "description": type_name,
                "user_id": self.user_id,
                "environment_id": self.environment_id,
                "limit": max_results,
                "kind": "literal" if include_literals else "entity",
            }
            results = await self._request("POST", "search/type", json_body=body)
            duration = time.time() - start_time
            count = len(results) if isinstance(results, list) else 0
            praxos_logger.info(
                f"Found {count} nodes of type {type_name} in {duration:.2f}s"
            )
            return results
        except PraxosBridgeError as e:
            praxos_logger.error(f"Get nodes by type failed: {e.message}")
            return {"error": e.message}
        except Exception as e:
            praxos_logger.error(f"Get nodes by type failed: {e}")
            return {"error": str(e)}

    async def enrich_nodes(self, node_ids: list, k_hops: int = 2):
        try:
            body = {
                "node_ids": node_ids,
                "user_id": self.user_id,
                "k": k_hops,
            }
            return await self._request("POST", "enrich", json_body=body)
        except Exception as e:
            praxos_logger.error(f"Error enriching nodes {node_ids}: {e}")
            return {}

    # ------------------------------------------------------------------
    # Trigger / habit
    # ------------------------------------------------------------------

    async def setup_trigger(self, trigger_conditional_statement: str):
        try:
            body = {
                "text": trigger_conditional_statement,
                "user_id": self.user_id,
                "environment_id": self.environment_id,
            }
            return await self._request("POST", "triggers/ingest", json_body=body)
        except PraxosBridgeError as e:
            praxos_logger.error(f"Error setting up trigger: {e.message}")
            return {"error": e.message}
        except Exception as e:
            praxos_logger.error(
                f"Error setting up trigger with condition {trigger_conditional_statement}: {e}"
            )
            return {"error": str(e)}

    async def eval_event(
        self,
        event_json,
        event_type: str = "email_received",
        adapter_kwargs: dict = None,
    ):
        try:
            body = {
                "event_json": event_json,
                "user_id": self.user_id,
                "environment_id": self.environment_id,
                "provider": event_type,
                "adapter_kwargs": adapter_kwargs,
            }
            return await self._request("POST", "triggers/evaluate-event", json_body=body)
        except PraxosBridgeError as e:
            praxos_logger.error(f"Error evaluating event ({event_type}): {e.message}")
            return {"error": e.message}
        except Exception as e:
            praxos_logger.error(
                f"Error evaluating event {event_json} of type {event_type}: {e}"
            )
            return {"error": str(e)}

    async def evaluate_user_message(
        self,
        message_json,
        source: str,
        output_type: str = None,
        output_chat_id: str = None,
    ):
        try:
            body = {
                "message_json": message_json,
                "user_id": self.user_id,
                "environment_id": self.environment_id,
                "source": source,
                "output_type": output_type,
                "output_chat_id": output_chat_id,
            }
            return await self._request(
                "POST", "triggers/evaluate-user-message", json_body=body
            )
        except PraxosBridgeError as e:
            praxos_logger.error(
                f"Error evaluating user message from {source}: {e.message}"
            )
            return {"error": e.message}
        except Exception as e:
            praxos_logger.error(f"Error evaluating user message from {source}: {e}")
            return {"error": str(e)}

    async def setup_habit(self, habit_conditional_statement: str):
        try:
            body = {
                "text": habit_conditional_statement,
                "user_id": self.user_id,
                "environment_id": self.environment_id,
            }
            return await self._request("POST", "habits/ingest", json_body=body)
        except PraxosBridgeError as e:
            praxos_logger.error(f"Error setting up habit: {e.message}")
            return {"error": e.message}
        except Exception as e:
            praxos_logger.error(
                f"Error setting up habit with statement {habit_conditional_statement}: {e}"
            )
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # File sync helpers
    # ------------------------------------------------------------------

    async def sync_file_to_knowledge_graph(
        self,
        blob_path: str,
        file_name: str,
        mime_type: str,
        description: str = None,
        metadata: dict = None,
        container_name: str = None,
    ) -> dict:
        """Pull file bytes from blob, then upload via /sources/file."""
        from src.utils.blob_utils import download_from_blob_storage

        start_time = time.time()
        log_praxos_file_upload_started(blob_path, file_name, description)
        try:
            data = await download_from_blob_storage(
                blob_path, container_name=container_name
            )
            result = await self._post_file(
                data,
                file_name,
                content_type=mime_type,
                name=file_name,
                description=description
                or f"File synced to knowledge graph: {file_name}",
                metadata=metadata,
            )
            source_id = result.get("id") if isinstance(result, dict) else None
            duration = time.time() - start_time
            log_praxos_file_upload_completed(blob_path, file_name, source_id, duration)
            return {
                "success": True,
                "sync_type": "knowledge_graph",
                "source_id": source_id,
            }
        except PraxosBridgeError as e:
            duration = time.time() - start_time
            log_praxos_file_upload_failed(blob_path, file_name, e, duration)
            return {"error": f"Knowledge-graph sync failed: {e.message}"}
        except Exception as e:
            duration = time.time() - start_time
            log_praxos_file_upload_failed(blob_path, file_name, e, duration)
            return {"error": f"Knowledge-graph sync failed: {str(e)}"}

    async def sync_file_for_semantic_search(
        self,
        blob_path: str,
        file_name: str,
        mime_type: str,
        description: str = None,
        metadata: dict = None,
        container_name: str = None,
    ) -> dict:
        """Pull bytes from blob, forward to /sources/file-embedding (Qdrant only)."""
        from src.utils.blob_utils import download_from_blob_storage

        start_time = time.time()
        try:
            data = await download_from_blob_storage(
                blob_path, container_name=container_name
            )
            files = {
                "files": (
                    file_name,
                    data,
                    mime_type or mimetypes.guess_type(file_name)[0] or "application/octet-stream",
                )
            }
            form: Dict[str, Any] = {}
            if file_name:
                form["name"] = file_name
            if description:
                form["description"] = description or f"File synced for semantic search: {file_name}"
            if metadata:
                form["metadata"] = json.dumps(metadata)
            params = {"user_id": self.user_id, "environment_id": self.environment_id}
            result = await self._request(
                "POST",
                "sources/file-embedding",
                params=params,
                files=files,
                data=form,
            )
            duration = time.time() - start_time
            sync_ref = None
            if isinstance(result, dict):
                sync_ref = (
                    result.get("sync_ref")
                    or result.get("id")
                    or result.get("collection")
                )
            praxos_logger.info(
                f"Semantic sync of '{file_name}' done in {duration:.2f}s (ref={sync_ref})"
            )
            return {
                "success": True,
                "sync_type": "embedding",
                "sync_ref": sync_ref,
                "raw": result,
            }
        except PraxosBridgeError as e:
            duration = time.time() - start_time
            praxos_logger.error(
                f"Semantic sync failed for '{file_name}' after {duration:.2f}s: {e.message}"
            )
            return {"error": f"Semantic sync failed: {e.message}"}
        except Exception as e:
            duration = time.time() - start_time
            praxos_logger.error(
                f"Semantic sync failed for '{file_name}' after {duration:.2f}s: {e}"
            )
            return {"error": f"Semantic sync failed: {str(e)}"}

    # ------------------------------------------------------------------
    # Graph CRUD
    # ------------------------------------------------------------------

    async def create_entity_in_kg(
        self,
        entity_type: str,
        label: str,
        properties: List[Dict[str, Any]],
        nested_entities: Dict = None,
    ):
        start_time = time.time()
        praxos_logger.info(f"Creating entity in KG: type={entity_type}, label={label}")
        try:
            body = {
                "entity_type": entity_type,
                "label": label,
                "properties": properties,
                "user_id": self.user_id,
                "environment_id": self.environment_id,
                "nested_entities": nested_entities,
                "auto_type": True,
            }
            result = await self._request("POST", "graph/entity", json_body=body)
            duration = time.time() - start_time
            nodes_created = (
                result.get("nodes_created", 0) if isinstance(result, dict) else 0
            )
            praxos_logger.info(
                f"Created entity '{label}' with {nodes_created} nodes in {duration:.2f}s"
            )
            return result
        except PraxosBridgeError as e:
            praxos_logger.error(f"Failed to create entity: {e.message}")
            return {"error": e.message}
        except Exception as e:
            praxos_logger.error(f"Failed to create entity: {e}")
            return {"error": str(e)}

    async def update_literal_value(
        self, node_id: str, new_value: Any, new_type: str = None
    ):
        start_time = time.time()
        praxos_logger.info(f"Updating literal {node_id} to value: {new_value}")
        try:
            body = {
                "value": new_value,
                "user_id": self.user_id,
                "new_type": new_type,
            }
            result = await self._request(
                "PUT", f"graph/nodes/{node_id}/literal", json_body=body
            )
            duration = time.time() - start_time
            praxos_logger.info(f"Updated literal {node_id} in {duration:.2f}s")
            return result
        except PraxosBridgeError as e:
            praxos_logger.error(f"Failed to update literal: {e.message}")
            return {"error": e.message}
        except Exception as e:
            praxos_logger.error(f"Failed to update literal: {e}")
            return {"error": str(e)}

    async def update_entity_properties(
        self,
        node_id: str,
        properties: List[Dict[str, Any]],
        replace_all: bool = False,
    ):
        start_time = time.time()
        praxos_logger.info(
            f"Updating entity {node_id} with {len(properties)} properties (replace_all={replace_all})"
        )
        try:
            body = {
                "properties": properties,
                "user_id": self.user_id,
                "environment_id": self.environment_id,
                "replace_all": replace_all,
            }
            result = await self._request(
                "PUT", f"graph/nodes/{node_id}/entity", json_body=body
            )
            duration = time.time() - start_time
            nodes_modified = (
                result.get("nodes_modified", 0) if isinstance(result, dict) else 0
            )
            praxos_logger.info(
                f"Updated entity {node_id}, modified {nodes_modified} nodes in {duration:.2f}s"
            )
            return result
        except PraxosBridgeError as e:
            praxos_logger.error(f"Failed to update entity: {e.message}")
            return {"error": e.message}
        except Exception as e:
            praxos_logger.error(f"Failed to update entity: {e}")
            return {"error": str(e)}

    async def delete_node_from_kg(
        self, node_id: str, cascade: bool = True, force: bool = False
    ):
        start_time = time.time()
        praxos_logger.info(
            f"Deleting node {node_id} (cascade={cascade}, force={force})"
        )
        try:
            params = {
                "user_id": self.user_id,
                "cascade": "true" if cascade else "false",
                "force": "true" if force else "false",
            }
            result = await self._request(
                "DELETE", f"graph/nodes/{node_id}", params=params
            )
            duration = time.time() - start_time
            nodes_deleted = (
                result.get("nodes_deleted", 0) if isinstance(result, dict) else 0
            )
            praxos_logger.info(
                f"Deleted node {node_id}, removed {nodes_deleted} nodes in {duration:.2f}s"
            )
            return result
        except PraxosBridgeError as e:
            praxos_logger.error(f"Failed to delete node: {e.message}")
            return {"error": e.message}
        except Exception as e:
            praxos_logger.error(f"Failed to delete node: {e}")
            return {"error": str(e)}

    async def add_knowledge_chunk(
        self,
        text: str,
        source: str,
        metadata: Dict[str, Any] = None,
    ):
        """Add a chunk of text via /sources/business-data.

        The previous implementation wrote a temp .txt file and posted via
        add_file. The new bridge restricts /sources/file to pdf/doc/docx/json,
        so chunks now ride the business-data path: the chunk text + source +
        metadata are wrapped as a JSON document and run through graph-creator.
        """
        start_time = time.time()
        try:
            data = {
                "type": "knowledge_chunk",
                "text": text,
                "source": source,
                "metadata": metadata or {},
            }
            safe_source = "".join(
                c for c in source if c.isalnum() or c in (" ", "_", "-")
            ).strip()
            chunk_id = abs(hash(text))
            name = f"chunk_{safe_source}_{chunk_id}"
            result = await self.add_business_data(
                data=data,
                name=name,
                description=f"Knowledge chunk from {source}",
                root_entity_type="schema:Thing",
                metadata=metadata,
            )
            duration = time.time() - start_time
            praxos_logger.info(
                f"Ingested knowledge chunk from {source} in {duration:.2f}s"
            )
            return result
        except Exception as e:
            praxos_logger.error(f"Failed to ingest knowledge chunk: {e}")
            return {"error": str(e)}
