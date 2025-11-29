import discord
import argparse
import json
import os
import logging
from dotenv import load_dotenv
from exporter.collector import Collector
from exporter.detector import QuestionDetector
from exporter.dedupe import DedupeRegistry
from exporter.storage import Storage
from exporter.utils import setup_logging

# Explicitly load .env from the script's directory
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
loaded = load_dotenv(env_path)
if not loaded:
    logging.warning(f"Could not load .env file from {env_path}")

def load_config(config_path: str) -> dict:
    with open(config_path, 'r') as f:
        return json.load(f)

def main():
    parser = argparse.ArgumentParser(description="Discord Question Exporter")
    parser.add_argument("--config", default="config.json", help="Path to config file")
    parser.add_argument("--channels", nargs="+", type=int, help="List of channel IDs to scan")
    parser.add_argument("--all-channels", action="store_true", help="Scan all accessible channels")
    parser.add_argument("--concurrency", type=int, default=3, help="Number of concurrent channels")
    
    args = parser.parse_args()
    
    setup_logging()
    
    
    if not os.path.exists(args.config):
        logging.error(f"Config file {args.config} not found.")
        return

    config = load_config(args.config)
    
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        logging.error("Bot token not found in environment variables.")
        return

    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.messages = True

    client = discord.Client(intents=intents, status=discord.Status.invisible)

    @client.event
    async def on_ready():
        logging.info(f"Logged in as {client.user}")
        
        detector = QuestionDetector(
            language=config.get("language", "sv"),
            extra_keywords=config.get("extra_keywords", []),
            hf_api_key=os.getenv("HUGGINGFACE_API_KEY") ,
            use_ai=config.get("use_ai_detection", False)
        )
        
        registry = DedupeRegistry(config.get("dedupe_registry", "dedupe_registry.json"))
        storage = Storage(config.get("export_path", "export.txt"))
        checkpoint_file = config.get("checkpoint_file", "checkpoints.json")
        
        collector = Collector(client, detector, registry, storage, checkpoint_file)
        
        target_channel_ids = []
        
        if args.channels:
            target_channel_ids = args.channels
        elif args.all_channels:
            for guild in client.guilds:
                for channel in guild.text_channels:
                    target_channel_ids.append(channel.id)
        else:
            target_channel_ids = config.get("channel_ids", [])
            
        if not target_channel_ids:
            logging.warning("No channels specified to scan.")
            await client.close()
            return

        logging.info(f"Targeting {len(target_channel_ids)} channels.")
        
        await collector.collect_from_channels(target_channel_ids, concurrency=args.concurrency)
        
        logging.info("Export completed.")
        await client.close()

    client.run(token)

if __name__ == "__main__":
    main()
