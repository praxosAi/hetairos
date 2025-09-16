#!/usr/bin/env python3
"""
Export all messages from Azure Service Bus queue before recreating with sessions,
then reimport them with session IDs.
"""
import asyncio
import json
from datetime import datetime
from azure.servicebus.aio import ServiceBusClient
from azure.servicebus import ServiceBusMessage
from src.config.settings import settings

async def export_all_messages():
    """Export all messages from the queue to a JSON file"""
    messages = []
    
    async with ServiceBusClient.from_connection_string(settings.AZURE_SERVICEBUS_CONNECTION_STRING) as client:
        receiver = client.get_queue_receiver(settings.AZURE_SERVICEBUS_QUEUE_NAME)
        
        async with receiver:
            print("Draining messages from queue...")
            message_count = 0
            
            # Process messages in batches with timeout
            while True:
                try:
                    # Receive batch of messages with 30 second timeout
                    batch = await receiver.receive_messages(max_message_count=10, max_wait_time=30)
                    
                    if not batch:
                        print("No more messages found")
                        break
                    
                    for msg in batch:
                        try:
                            # Parse message content
                            event = json.loads(str(msg))
                            
                            # Add metadata about the message
                            message_data = {
                                'content': event,
                                'message_id': msg.message_id,
                                'enqueued_time': msg.enqueued_time_utc.isoformat() if msg.enqueued_time_utc else None,
                                'delivery_count': msg.delivery_count,
                                'exported_at': datetime.utcnow().isoformat()
                            }
                            
                            messages.append(message_data)
                            message_count += 1
                            
                            # Complete the message (removes it from queue)
                            await receiver.complete_message(msg)
                            print(f"Exported message {message_count}: {event.get('source', 'unknown')} from user {event.get('user_id', 'unknown')}")
                            
                        except Exception as e:
                            print(f"Error processing message: {e}")
                            # Abandon message so it stays in queue
                            await receiver.abandon_message(msg)
                
                except Exception as e:
                    print(f"Error receiving batch: {e}")
                    break
    
    # Save to file
    export_filename = f"queue_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    
    export_data = {
        'export_timestamp': datetime.utcnow().isoformat(),
        'total_messages': len(messages),
        'messages': messages
    }
    
    with open(export_filename, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    
    print(f"\nExport complete!")
    print(f"- Messages exported: {len(messages)}")
    print(f"- File saved: {export_filename}")
    
    return export_filename, len(messages)

def _generate_session_id(event: dict) -> str:
    """Generate a session ID based on event data (same logic as AzureEventQueue)"""
    # Generate session based on user and source for grouping
    user_id = event.get('user_id')
    source = event.get('source', 'unknown')
    
    if user_id:
        return f"{source}_{user_id}"
    else:
        # Fallback for system/non-user events
        return f"system_{source}"

async def reimport_messages(export_filename: str):
    """Reimport messages to the new session-enabled queue"""
    print(f"\nReimporting messages from {export_filename}...")
    
    with open(export_filename, 'r', encoding='utf-8') as f:
        export_data = json.load(f)
    
    messages = export_data['messages']
    imported_count = 0
    
    async with ServiceBusClient.from_connection_string(settings.AZURE_SERVICEBUS_CONNECTION_STRING) as client:
        sender = client.get_queue_sender(settings.AZURE_SERVICEBUS_QUEUE_NAME)
        async with sender:
            for msg_data in messages:
                try:
                    event = msg_data['content']
                    
                    # Generate session ID for this event
                    session_id = _generate_session_id(event)
                    
                    # Create new message with session
                    message_body = json.dumps(event)
                    message = ServiceBusMessage(message_body)
                    message.session_id = session_id
                    
                    await sender.send_messages(message)
                    imported_count += 1
                    
                    print(f"Reimported message {imported_count}/{len(messages)}: session={session_id}, source={event.get('source', 'unknown')}")
                    
                except Exception as e:
                    print(f"Error reimporting message: {e}")
                    print(f"Message data: {msg_data}")
    
    print(f"\nReimport complete!")
    print(f"- Messages reimported: {imported_count}/{len(messages)}")
    return imported_count

async def export_and_reimport():
    """Full export and reimport process"""
    print("=== Step 1: Export existing messages ===")
    export_filename, exported_count = await export_all_messages()
    
    if exported_count == 0:
        print("No messages to reimport")
        return
    
    print("\n=== Step 2: Recreate queue with sessions enabled ===")
    print("Please go to Azure Portal and:")
    print("1. Delete the current queue")
    print("2. Create a new queue with the same name")
    print("3. Enable 'Sessions' in the queue configuration")
    
    input("Press Enter when you've recreated the queue with sessions enabled...")
    
    print("\n=== Step 3: Reimport messages with sessions ===")
    imported_count = await reimport_messages(export_filename)
    
    print(f"\n=== Process complete! ===")
    print(f"Exported: {exported_count} messages")
    print(f"Reimported: {imported_count} messages")

if __name__ == "__main__":
    asyncio.run(export_and_reimport())