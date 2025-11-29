import aiofiles
import os
from datetime import datetime

class Storage:
    def __init__(self, export_path: str):
        self.export_path = export_path

    async def write_question(self, channel_name: str, created_at: datetime, content: str):
        """
        Appends a question to the export file.
        Format: [Channel Name] - [YYYY-MM-DD] Question text...
        """
        date_str = created_at.strftime("%Y-%m-%d")
        # Clean newlines in content to keep it one line per question if possible, 
        # or just ensure it doesn't break the format too badly.
        # The roadmap suggests: [Channel Name] - [YYYY-MM-DD] Question text...
        # If content has newlines, it might be better to replace them or keep them.
        # Let's replace newlines with spaces for a cleaner text file export.
        clean_content = content.replace('\n', ' ').strip()
        
        line = f"[{channel_name}] - [{date_str}] {clean_content}\n"
        
        async with aiofiles.open(self.export_path, mode='a', encoding='utf-8') as f:
            await f.write(line)
