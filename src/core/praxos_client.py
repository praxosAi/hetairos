import praxos_python
import asyncio
import time
from datetime import datetime
from praxos_python.types.message import Message
from typing import Dict, List, Optional, Any
from src.services.token_encryption import decrypt_token
from src.config.settings import settings
from src.utils.logging import (
    praxos_logger,
    log_praxos_connection_start,
    log_praxos_connection_success,
    log_praxos_connection_failed,
    log_praxos_environment_created,
    log_praxos_query_started,
    log_praxos_query_completed,
    log_praxos_query_failed,
    log_praxos_search_anchors_started,
    log_praxos_search_anchors_completed,
    log_praxos_search_anchors_failed,
    log_praxos_add_message_started,
    log_praxos_add_message_completed,
    log_praxos_add_message_failed,
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
    log_praxos_context_details
)

class PraxosClient:
    def __init__(self, environment_name: str = None, api_key: str = None):
        self.api_key = decrypt_token(api_key)
        self.environment_name = environment_name
        self.client = None
        self.env = None
        try:
            self.client = praxos_python.SyncClient(
                api_key=self.api_key,
                timeout=60,
            )
        
            # Get or create environment
            try:
                self.env = self.client.get_environment(name=self.environment_name)
                log_praxos_connection_success(self.environment_name)
            except Exception as env_error:
                # Environment doesn't exist, create it
                log_praxos_environment_created(self.environment_name)
                self.env = self.client.create_environment(
                    name=self.environment_name,
                    description="AI Personal Assistant Environment"
                )
                log_praxos_connection_success(self.environment_name)
            
            
            
        except Exception as e:
            log_praxos_connection_failed(self.environment_name, e,0)
            raise
    
    async def add_conversation(self, user_id: str, source: str, metadata: Dict = None, user_record: Dict[str, Any] = None, messages: List[Dict] = None, conversation_id: str = 'no_conversation_id'):
        """Add a conversation to Praxos memory"""
        if not self.env:
            return {"error": "Environment not initialized"}
        
        start_time = time.time()
        praxos_logger.info(f"Adding conversation for user {user_id} with source {source}")        
        try:
            reformatted_messages = []
            for message in messages:
                time_stamp_str = message['timestamp']
                if not isinstance(time_stamp_str, str):
                    time_stamp_str = time_stamp_str.isoformat()
                if message['role'] == 'user':
                    content_enriched = "Message sent at " + time_stamp_str + " by " + user_record.get('first_name', '') + " " + user_record.get('last_name', '') + ": " + message['content']
                else:
                    content_enriched = "Message sent at " + time_stamp_str + " by Praxos Assistant: " + message['content']
                reformatted_messages.append(Message(content=content_enriched, role=message['role'], timestamp=message['timestamp']))
            # Create unique name to avoid conflicts
            import uuid
            unique_name = f"Message_{user_id}_{source}_{uuid.uuid4().hex}"
                     
            result = self.env.add_conversation(
                messages=reformatted_messages,
                name=unique_name,
                description='message from user with conversation id ' + conversation_id
            ) 
            
            duration = time.time() - start_time
            # SyncSource object has .id attribute, not .get() method
            message_id = getattr(result, 'id', None) if result else None
            praxos_logger.info(f"Conversation added successfully for user {user_id} with source {source} in {duration:.2f}s")
            
            # Return consistent format
            return {
                "success": True,
                "id": message_id,
                "source": result
            }
            
        except Exception as e:
            duration = time.time() - start_time
            praxos_logger.error(f"Error adding conversation for user {user_id} with source {source}: {e}")
            # Also log API error if it's a specific API error
            if hasattr(e, 'status_code'):
                praxos_logger.error(f"Error adding conversation for user {user_id} with source {source}: {e.status_code}")
            return {"error": str(e)}
    
    # Backwards compatibility alias
    async def add_message(self, user_id: str, content: str, source: str, metadata: Dict = None, user_record: Dict[str, Any] = None):
        """Backwards compatibility alias for add_conversation"""
        return await self.add_conversation(user_id, content, source, metadata, user_record)
    
    async def add_email_conversation(self, messages: List, name: str, description: str, metadata: Dict = None, user_record: Dict[str, Any] = None):
        """Add an email as a proper conversation using Message objects"""
        if not self.env:
            return {"error": "Environment not initialized"}
        
        start_time = time.time()
        
        try:
            # Add UUID to name to avoid conflicts
            import uuid
            unique_name = f"{name}_{uuid.uuid4().hex[:8]}"
            
            # Use environment's add_conversation method directly with Message objects
            result = self.env.add_conversation(
                messages=messages,
                name=unique_name,
                description=description,
                user_record=user_record
            )
            
            duration = time.time() - start_time
            # SyncSource object has .id attribute
            source_id = getattr(result, 'id', None) if result else None
            
            praxos_logger.info(f"✅ Email conversation added successfully in {duration:.2f}s (ID: {source_id})")
            
            # Return consistent format
            return {
                "success": True,
                "id": source_id,
                "source": result
            }
            
        except Exception as e:
            duration = time.time() - start_time
            praxos_logger.error(f"❌ Email conversation add failed: {e} (Duration: {duration:.2f}s)")
            if hasattr(e, 'status_code'):
                praxos_logger.error(f"   Status code: {e.status_code}")
            return {"error": str(e)}
    
    async def add_integration_capability(self, user_id: str, integration_type: str, capabilities: List[str]):
        """Add integration capability to Praxos memory as a schema:Integration node"""
        if not self.env:
            return {"error": "Environment not initialized"}
        
        start_time = time.time()
        log_praxos_add_integration_started(user_id, integration_type, capabilities)
        
        try:
            # Add integration as a capability in the knowledge graph
            integration_data = {
                "type": "schema:Integration",
                "user_id": user_id,
                "integration_type": integration_type,
                "capabilities": capabilities,
                "status": "active",
                "added_at": datetime.utcnow().isoformat()
            }
            
            # This would be added as a graph node
            # Placeholder for actual SDK method
            result = self.env.add_data(
                data=integration_data,
                name=f"{integration_type}_integration_{user_id}",
                description=f"{integration_type.title()} integration for user {user_id}"
            )
            
            duration = time.time() - start_time
            integration_id = result.get('id') if result else None
            log_praxos_add_integration_completed(user_id, integration_type, integration_id, duration)
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            log_praxos_add_integration_failed(user_id, integration_type, e, duration)
            if hasattr(e, 'status_code'):
                log_praxos_api_error("add_integration_capability", e.status_code, str(e), getattr(e, 'details', None))
            return {"error": str(e)}
    
    async def add_file(self, file_path: str, name: str, description: str = None):
        """Add a file to Praxos memory from file path"""
        if not self.env:
            return {"error": "Environment not initialized"}
        
        start_time = time.time()
        log_praxos_file_upload_started(file_path, name, description)
        
        try:
            # Use Praxos SDK to add file by path
            result = self.env.add_file(
                path=file_path,
                name=name,
                description=description or f"File: {name}"
            )
            
            duration = time.time() - start_time
            # SyncSource object has id attribute, not .get() method
            file_id = getattr(result, 'id', None) if result else None
            log_praxos_file_upload_completed(file_path, name, file_id, duration)
            
            # Return a dictionary format for consistency with other methods
            return {
                "success": True,
                "id": file_id,
                "source": result
            }
            
        except Exception as e:
            duration = time.time() - start_time
            log_praxos_file_upload_failed(file_path, name, e, duration)
            if hasattr(e, 'status_code'):
                log_praxos_api_error("add_file", e.status_code, str(e), getattr(e, 'details', None))
            return {"error": f"File upload failed: {str(e)}"}
    
    async def add_file_content(self, file_data: bytes, filename: str, mimetype: str = None, description: str = None):
        """Add file content directly to Praxos memory"""
        if not self.env:
            return {"error": "Environment not initialized"}
        
        try:
            # For files that support direct content ingestion
            if mimetype and mimetype.startswith('text/'):
                # Text files can be added as messages
                try:
                    content = file_data.decode('utf-8')
                    return await self.add_conversation(
                        user_id="system",
                        content=f"File content from {filename}:\n{content}",
                        source="file_ingestion",
                        metadata={
                            "filename": filename,
                            "mimetype": mimetype,
                            "file_size": len(file_data),
                            "content_type": "text_file"
                        }
                    )
                except UnicodeDecodeError:
                    pass
            
            # For other file types, save temporarily and use file upload
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as temp_file:
                temp_file.write(file_data)
                temp_file_path = temp_file.name
            
            try:
                # Upload using file path
                result = await self.add_file(
                    file_path=temp_file_path,
                    name=filename,
                    description=description or f"Email attachment: {filename}"
                )
                
                # Clean up temp file
                os.unlink(temp_file_path)
                return result
                
            except Exception as upload_error:
                # Clean up temp file even if upload fails
                os.unlink(temp_file_path)
                
                # Fallback: add file metadata as data source
                file_metadata = {
                    "type": "file_content",
                    "filename": filename,
                    "mimetype": mimetype,
                    "file_size": len(file_data),
                    "description": description,
                    "added_at": datetime.utcnow().isoformat(),
                    "status": "content_available_but_not_uploaded"
                }
                
                return self.env.add_data(
                    data=file_metadata,
                    name=f"file_content_{filename}",
                    description=description or f"File content metadata: {filename}"
                )
                
        except Exception as e:
            praxos_logger.error(f"Error adding file content to Praxos: {e}")
            return {"error": f"File content upload failed: {str(e)}"}
    
    async def search_from_anchors(self, user_id: str, query: str, max_hops: int = 3, top_k: int = 3, node_types: List[str] = None):
        """Search using anchors to find relevant integrations and capabilities"""
        if not self.env:
            return {"error": "Environment not initialized"}
        
        start_time = time.time()
        
        # Search using user identifiers as anchors
        anchors = [{"value": user_id}]
        
        # Add email anchor if available (from settings)
        if hasattr(settings, 'TEST_EMAIL_LUCAS') and settings.TEST_EMAIL_LUCAS and settings.TEST_EMAIL_LUCAS.strip():
            anchors.append({"value": settings.TEST_EMAIL_LUCAS})
        
        # Use node_types if provided, otherwise default to schema:Capability
        node_type = node_types[0] if node_types else 'schema:Capability'
        
        log_praxos_search_anchors_started(user_id, query, anchors, max_hops, top_k, node_types)
        
        try:
            results = self.env.search_from_anchors(
                anchors=anchors,
                query=query,
                max_hops=max_hops,
                node_type=node_type,
                top_k=top_k
            )
            
            duration = time.time() - start_time
            # results is a list, not a dictionary
            results_count = len(results) if results else 0
            anchors_used = len(anchors)
            
            log_praxos_search_anchors_completed(user_id, query, results_count, duration, anchors_used)
            
            # Log detailed context for debugging
            log_praxos_context_details(user_id, query, results)
            
            # Check for slow performance
            if duration > 5.0:  # Log warning if search takes longer than 5 seconds
                log_praxos_performance_warning("search_from_anchors", duration, 5.0)
            
            # Return in consistent format
            return {
                "success": True,
                "results": results,
                "count": results_count
            }
            
        except Exception as e:
            duration = time.time() - start_time
            log_praxos_search_anchors_failed(user_id, query, e, duration)
            
            # Log API error details if available
            if hasattr(e, 'status_code'):
                log_praxos_api_error("search_from_anchors", e.status_code, str(e), getattr(e, 'details', None))
            
            return {"error": str(e)}
    
    async def get_user_integrations(self, user_id: str):
        """Get user's active integrations using anchor search"""
        if not self.env:
            return {"error": "Environment not initialized"}
        
        start_time = time.time()
        log_praxos_get_integrations_started(user_id)
        
        try:
            # Search for integration nodes connected to this user
            results = await self.search_from_anchors(
                user_id=user_id,
                query="find all active integrations for this user",
                max_hops=2,
                top_k=10
            )
            
            # Extract integration nodes
            integration_nodes = []
            nodes_to_id = set()
            
            if 'anchor_connections' in results:
                for result in results:
                    for conn in result.get('anchor_connections', []):
                        for node in conn.get('path_nodes', []):
                            if node.get('type') == 'schema:Integration':
                                nodes_to_id.add(node['id'])
            
            # Fetch full integration details
            if nodes_to_id:
                graph_nodes = self.env.fetch_graph_nodes(list(nodes_to_id))
                integration_nodes = graph_nodes
            
            duration = time.time() - start_time
            integrations_found = len(integration_nodes)
            log_praxos_get_integrations_completed(user_id, integrations_found, duration)
            
            return integration_nodes
            
        except Exception as e:
            duration = time.time() - start_time
            log_praxos_get_integrations_failed(user_id, e, duration)
            if hasattr(e, 'status_code'):
                log_praxos_api_error("get_user_integrations", e.status_code, str(e), getattr(e, 'details', None))
            return {"error": str(e)}
    
    async def query_memory(self, user_id: str, query: str, context_type: str = None):
        """Query memory using anchor-based search"""
        start_time = time.time()
        log_praxos_query_started(user_id, query, "query_memory")
        
        try:
            result = await self.search_from_anchors(user_id, query)
            
            duration = time.time() - start_time
            results_count = len(result.get('results', [])) if result else 0
            log_praxos_query_completed(user_id, query, results_count, duration, "query_memory")
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            log_praxos_query_failed(user_id, query, e, duration, "query_memory")
            raise
    
    async def search_memory(self, query: str, top_k: int = 5, search_modality: str = "node_vec"):
        """Direct search using Praxos search method with score filtering and sentence extraction"""
        if not self.env:
            return {"error": "Environment not initialized"}
        
        start_time = time.time()
        log_praxos_query_started("system", query, "search_memory")
        
        try:
            # Use direct search method as specified by user
            results = self.env.search(query=query, top_k=top_k, search_modality=search_modality)
        
            duration = time.time() - start_time
            
            # Filter results by score > 0.8 and extract sentences
            qualified_results = []
            extracted_sentences = []
            source_ids = set()
            if results and isinstance(results, list):
                for result in results:
                    # Check if result has a score > 0.8
                    score = result.get('score', 0)
                    if score > 0.7:
                        qualified_results.append({'text': result.get('sentence', ''), 'node_id': result.get('node_id')})
                        # Extract sentence field if available
                        sentence = result.get('sentence', '')
                        source_ids.add(result.get('source_id', ''))
                        if sentence:
                            extracted_sentences.append(sentence)
            
            results_count = len(qualified_results)
            sentences_count = len(extracted_sentences)
            
            log_praxos_query_completed("system", query, results_count, duration, "search_memory")
            
            # Return formatted results with extracted sentences for LLM processing
            return {
                "success": True,
                "source_ids": source_ids,
                "results": qualified_results,
                "sentences": extracted_sentences,
                "count": results_count,
                "sentences_count": sentences_count,
                "raw_results": results  # Keep original results for debugging
            }
            
        except Exception as e:
            duration = time.time() - start_time
            log_praxos_query_failed("system", query, e, duration, "search_memory")
            if hasattr(e, 'status_code'):
                log_praxos_api_error("search_memory", e.status_code, str(e), getattr(e, 'details', None))
            return {"error": str(e)}
        
    async def enrich_nodes(self, node_ids: list, k_hops: int = 2):
        """Direct search using Praxos search method with score filtering and sentence extraction"""
        if not self.env:
            return {"error": "Environment not initialized"}
        
        start_time = time.time()
        
        try:
            # Use direct search method as specified by user
            results = self.env.enrich_nodes(node_ids=node_ids, k=k_hops)
            return results
        except Exception as e:
            duration = time.time() - start_time
            praxos_logger.error(f"Error enriching nodes {node_ids}: {e}")
            return {}
    async def setup_trigger(self,trigger_conditional_statement):
        """Setup a trigger in Praxos memory. a trigger is a conditional statement, of form "If I receive an email from X, then do Y"
        Args:
            trigger_conditional_statement: The conditional statement to setup as a trigger. it should be complete and descriptive, in plain english. 
        """
        if not self.env:
            return {"error": "Environment not initialized"}
        
        start_time = time.time()
        
        try:
            # Use direct search method as specified by user
            result = self.env.ingest_trigger(trigger_conditional_statement)
            return result
        except Exception as e:
            duration = time.time() - start_time
            praxos_logger.error(f"Error setting up trigger with condition {trigger_conditional_statement}: {e}")
            return {"error": str(e)}
    async def eval_event(self,event_json, event_type: str = "email_received"):
        """Evaluate an event against the triggers in Praxos memory. 
        Args:
            event_json: The event to evaluate, in JSON format. it should contain all relevant information about the event.
            event_type: The type of the event, e.g. "email_received", "calendar_event", etc.
        """
        if not self.env:
            return {"error": "Environment not initialized"}
        
        start_time = time.time()
        
        try:
            # Use direct search method as specified by user
            result = self.env.evaluate_event(event_json,event_type)
            return result
        except Exception as e:
            duration = time.time() - start_time
            praxos_logger.error(f"Error evaluating event {event_json} of type {event_type}: {e}")
            return {"error": str(e)}
    async def add_business_data(self, data: Dict[str, Any], name: str = None, description: str = None, root_entity_type: str = "schema:Thing", metadata: Dict[str, Any] = None):
      
      """Add business data to Praxos memory using add_business_data method"""
      
      if not self.env:
          return {"error": "Environment not initialized"}

      start_time = time.time()

      try:
          # Use the SDK's add_business_data method directly
          result = self.env.add_business_data(
              data=data,
              name=name,
              description=description,
              root_entity_type=root_entity_type,
              metadata=metadata
          )

          duration = time.time() - start_time

          # Log success (you can add specific logging if needed)
          praxos_logger.info(f"✅ Business data added successfully in {duration:.2f}s")

          # Return consistent format
          return {
              "success": True,
              "id": getattr(result, 'id', None) if result else None,
              "source": result
          }

      except Exception as e:
          duration = time.time() - start_time
          praxos_logger.error(f"❌ Business data add failed: {e} (Duration: {duration:.2f}s)")
          if hasattr(e, 'status_code'):
              praxos_logger.error(f"   Status code: {e.status_code}")
          return {"error": str(e)}
      
          