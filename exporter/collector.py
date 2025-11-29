import discord
import logging
import json
import os
from typing import List, Dict, Optional
from .detector import QuestionDetector
from .dedupe import DedupeRegistry
from .storage import Storage
from .utils import exponential_backoff
import asyncio

class Collector:
    def __init__(
        self,
        client: discord.Client,
        detector: QuestionDetector,
        registry: DedupeRegistry,
        storage: Storage,
        checkpoint_file: str
    ):
        self.client = client
        self.detector = detector
        self.registry = registry
        self.storage = storage
        self.checkpoint_file = checkpoint_file
        self.checkpoints: Dict[str, int] = self._load_checkpoints()

    def _load_checkpoints(self) -> Dict[str, int]:
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Failed to load checkpoints: {e}")
        return {}

    def _save_checkpoints(self):
        try:
            with open(self.checkpoint_file, 'w') as f:
                json.dump(self.checkpoints, f)
        except Exception as e:
            logging.error(f"Failed to save checkpoints: {e}")

    async def process_channel(self, channel: discord.TextChannel, limit: Optional[int] = None):
        logging.info(f"Starting processing for channel: {channel.name} ({channel.id})")
        
        last_id = self.checkpoints.get(str(channel.id))
        after = discord.Object(id=last_id) if last_id else None
        
        count = 0
        processed_count = 0
        
        batch_size = 32
        message_buffer = []
        
        try:
            # We use history(after=...) to resume. 
            # oldest_first=True is important to process in chronological order.
            async for message in channel.history(limit=limit, after=after, oldest_first=True):
                processed_count += 1
                
                if message.author.bot:
                    continue
                
                content = message.content
                if not content:
                    continue

                message_buffer.append(message)
                
                if len(message_buffer) >= batch_size:
                    questions_found = await self._process_batch(message_buffer, channel)
                    count += questions_found
                    
                    # Update checkpoint
                    self.checkpoints[str(channel.id)] = message.id
                    self._save_checkpoints()
                    self.registry.save()
                    message_buffer = []
            
            # Process remaining buffer
            if message_buffer:
                questions_found = await self._process_batch(message_buffer, channel)
                count += questions_found
                self.checkpoints[str(channel.id)] = message_buffer[-1].id
                self._save_checkpoints()
                self.registry.save()

            logging.info(f"Finished channel {channel.name}. Found {count} new questions. Processed {processed_count} messages.")

        except discord.Forbidden:
            logging.warning(f"Missing permissions for channel {channel.name}")
        except Exception as e:
            logging.error(f"Error processing channel {channel.name}: {e}")

    async def _process_batch(self, messages: List[discord.Message], channel: discord.TextChannel) -> int:
        contents = [m.content for m in messages]
        is_questions = await self.detector.detect_batch(contents)
        
        found = 0
        for message, is_q in zip(messages, is_questions):
            if is_q:
                normalized = self.detector.normalize(message.content)
                if not self.registry.is_duplicate(normalized, channel.id):
                    await self.storage.write_question(channel.name, message.created_at, message.content)
                    found += 1
        return found

    async def collect_from_channels(self, channel_ids: List[int], concurrency: int = 3):
        channels = []
        for cid in channel_ids:
            ch = self.client.get_channel(cid)
            if ch and isinstance(ch, discord.TextChannel):
                channels.append(ch)
            else:
                logging.warning(f"Channel {cid} not found or not a text channel.")

        semaphore = asyncio.Semaphore(concurrency)

        async def worker(channel):
            async with semaphore:
                await self.process_channel(channel)

        await asyncio.gather(*(worker(ch) for ch in channels))
