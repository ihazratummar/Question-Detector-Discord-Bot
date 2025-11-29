import json
import hashlib
import os
import logging
from typing import Set

class DedupeRegistry:
    def __init__(self, registry_path: str):
        self.registry_path = registry_path
        self.hashes: Set[str] = set()
        self.load()

    def load(self):
        """Loads the registry from disk."""
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.hashes = set(data)
                    else:
                        logging.warning("Registry file format invalid, starting fresh.")
            except Exception as e:
                logging.error(f"Failed to load registry: {e}")

    def save(self):
        """Saves the registry to disk atomically."""
        temp_path = self.registry_path + ".tmp"
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(list(self.hashes), f)
            os.replace(temp_path, self.registry_path)
        except Exception as e:
            logging.error(f"Failed to save registry: {e}")

    def is_duplicate(self, content: str, channel_id: int) -> bool:
        """
        Checks if the content is a duplicate.
        Uses a hash of channel_id + content.
        """
        # We include channel_id in the hash to allow same questions in different channels
        # if that's desired. If we want global dedupe, remove channel_id.
        # The roadmap says "deduplicates them using hash-based registry", 
        # usually for training data we want unique questions globally or per context.
        # Let's assume global uniqueness for the content itself is better for training data,
        # BUT the roadmap example hash is `f"{channel.id}|{normalized_text}|{language}"`.
        # So I will follow that.
        
        canonical = f"{channel_id}|{content}"
        content_hash = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
        
        if content_hash in self.hashes:
            return True
        
        self.hashes.add(content_hash)
        return False
