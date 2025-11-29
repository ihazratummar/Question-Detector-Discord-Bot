import flet as ft
import asyncio
import logging
import os
import json
import discord
from dotenv import load_dotenv
from exporter.collector import Collector
from exporter.detector import QuestionDetector
from exporter.dedupe import DedupeRegistry
from exporter.storage import Storage

# --- Logging Setup ---
class FletHandler(logging.Handler):
    def __init__(self, log_widget):
        super().__init__()
        self.log_widget = log_widget

    def emit(self, record):
        log_entry = self.format(record)
        self.log_widget.controls.append(ft.Text(log_entry, font_family="Consolas", size=12))
        self.log_widget.update()

# --- Discord Manager ---
class DiscordManager:
    def __init__(self):
        self.client = None
        self.is_connected = False
        self.collector = None
        
    async def start_bot(self, token, on_ready_callback):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.messages = True
        
        self.client = discord.Client(intents=intents, status=discord.Status.invisible)

        @self.client.event
        async def on_ready():
            self.is_connected = True
            logging.info(f"Logged in as {self.client.user}")
            if on_ready_callback:
                await on_ready_callback()

        try:
            await self.client.login(token)
            await self.client.connect()
        except Exception as e:
            logging.error(f"Connection failed: {e}")
            self.is_connected = False

    async def stop_bot(self):
        if self.client:
            await self.client.close()
            self.is_connected = False
            logging.info("Bot disconnected.")

    def get_guilds(self):
        if self.client:
            return self.client.guilds
        return []

    def get_text_channels(self, guild_id):
        if self.client:
            logging.info(f"Fetching channels for guild ID: {guild_id}")
            guild = self.client.get_guild(guild_id)
            if guild:
                logging.info(f"Found guild: {guild.name}")
                channels = [c for c in guild.text_channels]
                logging.info(f"Found {len(channels)} text channels.")
                return channels
            else:
                logging.warning(f"Guild with ID {guild_id} not found in client cache.")
        else:
            logging.error("Client is not initialized.")
        return []

    async def stop_export(self):
        if self.collector:
            self.collector.stop_event.set()
            # Ensure we unpause so the loop can check the stop flag
            self.collector.pause_event.set()
            logging.info("Stop signal sent to collector.")

    def toggle_pause(self):
        if self.collector:
            if self.collector.pause_event.is_set():
                self.collector.pause_event.clear()
                logging.info("Export paused.")
                return True # Paused
            else:
                self.collector.pause_event.set()
                logging.info("Export resumed.")
                return False # Resumed
        return False
        
    def clear_cache(self):
        try:
            files = ["checkpoints.json", "dedupe_registry.json"]
            deleted = []
            for f in files:
                if os.path.exists(f):
                    os.remove(f)
                    deleted.append(f)
            return deleted
        except Exception as e:
            logging.error(f"Error clearing cache: {e}")
            return []

    def clear_history(self):
        try:
            import glob
            files = glob.glob("export_*.txt")
            deleted = []
            for f in files:
                os.remove(f)
                deleted.append(f)
            return deleted
        except Exception as e:
            logging.error(f"Error clearing history: {e}")
            return []

    async def start_export(self, channel_ids, config, progress_callback=None):
        if not self.client or not self.is_connected:
            logging.error("Bot not connected.")
            return

        logging.info(f"Starting export for {len(channel_ids)} channels...")
        
        # Initialize components
        detector = QuestionDetector(
            language=config.get("language", "sv"),
            extra_keywords=config.get("extra_keywords", []),
            hf_api_key=os.getenv("HUGGINGFACE_API_KEY"),
            use_ai=config.get("use_ai_detection", False)
        )
        
        registry = DedupeRegistry(config.get("dedupe_registry", "dedupe_registry.json"))
        
        # Use unique filename if specified in config, otherwise use default
        export_path = config.get("export_path", "export.txt")
        storage = Storage(export_path)
        
        checkpoint_file = config.get("checkpoint_file", "checkpoints.json")
        
        self.collector = Collector(self.client, detector, registry, storage, checkpoint_file)
        
        await self.collector.collect_from_channels(channel_ids, concurrency=3, progress_callback=progress_callback)
        logging.info("Export completed!")

# --- Main UI ---
def main(page: ft.Page):
    page.title = "Discord Question Exporter"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 1000
    page.window_height = 900
    page.padding = 30
    page.bgcolor = ft.Colors.BLUE_GREY_900

    # State
    discord_manager = DiscordManager()
    token_value = os.getenv("DISCORD_BOT_TOKEN", "")
    
    # Load config for defaults
    config = {}
    if os.path.exists("config.json"):
        with open("config.json", "r") as f:
            config = json.load(f)

    # Components
    header = ft.Text("Discord Question Exporter", size=32, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
    status_text = ft.Text("Status: Stopped", color=ft.Colors.RED_400, size=16)

    # Logs
    log_column = ft.Column(scroll=ft.ScrollMode.ALWAYS, expand=True, auto_scroll=True)
    log_container = ft.Container(
        content=log_column,
        border=ft.border.all(1, ft.Colors.OUTLINE),
        border_radius=8,
        padding=15,
        height=200,
        bgcolor=ft.Colors.BLACK26
    )
    
    # Setup Logging
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    # Remove existing handlers to avoid duplicates if re-run
    for h in logger.handlers[:]:
        logger.removeHandler(h)
    
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    flet_handler = FletHandler(log_column)
    flet_handler.setFormatter(formatter)
    logger.addHandler(flet_handler)
    
    # Also add console handler for debugging
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # --- Channel Selection ---
    channel_checkboxes = ft.Column(scroll=ft.ScrollMode.AUTO)
    channel_container = ft.Container(
        content=channel_checkboxes,
        border=ft.border.all(1, ft.Colors.OUTLINE),
        border_radius=8,
        padding=15,
        visible=False,
        height=300, 
        bgcolor=ft.Colors.BLACK26
    )

    # --- Server Selection ---
    def on_server_change(e):
        try:
            logging.info(f"Server selection changed to: {server_dropdown.value}")
            guild_id = int(server_dropdown.value)
            channels = discord_manager.get_text_channels(guild_id)
            logging.info(f"Retrieved {len(channels)} channels for UI.")
            
            channel_checkboxes.controls.clear()
            
            # Header for channels
            channel_checkboxes.controls.append(ft.Text("Select Channels:", weight=ft.FontWeight.BOLD, size=16))

            def update_export_button():
                any_checked = False
                for c in channel_checkboxes.controls:
                    if isinstance(c, ft.Checkbox) and c.label != "Select All" and c.value:
                        any_checked = True
                        break
                start_export_btn.disabled = not any_checked
                start_export_btn.update()

            def on_checkbox_change(e):
                update_export_button()

            # Add "Select All" option
            def toggle_all(e):
                for c in channel_checkboxes.controls:
                    if isinstance(c, ft.Checkbox) and c.label != "Select All":
                        c.value = e.control.value
                channel_checkboxes.update()
                update_export_button()

            channel_checkboxes.controls.append(
                ft.Checkbox(label="Select All", on_change=toggle_all)
            )

            for ch in channels:
                channel_checkboxes.controls.append(
                    ft.Checkbox(label=f"#{ch.name}", value=False, data=ch.id, on_change=on_checkbox_change)
                )
            
            channel_container.visible = True
            channel_container.update()
            channel_checkboxes.update()
            
            # Reset button state
            start_export_btn.disabled = True
            start_export_btn.update()
            
            page.update()
        except Exception as ex:
            logging.error(f"Error in on_server_change: {ex}")

    server_dropdown = ft.Dropdown(
        label="Select Server",
        width=400,
        options=[],
        on_change=on_server_change,
        border_radius=8
    )

    # --- Connection ---
    async def on_connect_click(e):
        logging.info("Connect button clicked.")
        token = os.getenv("DISCORD_BOT_TOKEN")
        if not token:
            logging.error("No token found in .env")
            return

        logging.info("Token found. Connecting...")
        status_text.value = "Status: Connecting..."
        status_text.color = ft.Colors.ORANGE_400
        page.update()

        async def on_ready():
            status_text.value = "Status: Connected"
            status_text.color = ft.Colors.GREEN_400
            
            guilds = discord_manager.get_guilds()
            server_dropdown.options = [ft.dropdown.Option(str(g.id), g.name) for g in guilds]
            server_dropdown.update()
            page.update()

        await discord_manager.start_bot(token, on_ready)

    connect_btn = ft.ElevatedButton("Connect Bot", on_click=on_connect_click, icon=ft.Icons.LOGIN, height=50)

    # --- Export Actions ---
    async def on_start_export_click(e):
        # This is now handled by the wrapper
        pass

    async def on_stop_export_click(e):
        logging.info("Stop button clicked.")
        await discord_manager.stop_export()
        status_text.value = "Status: Stopping..."
        status_text.color = ft.Colors.ORANGE_400
        page.update()

    def on_pause_click(e):
        is_paused = discord_manager.toggle_pause()
        if is_paused:
            pause_btn.text = "Resume Export"
            pause_btn.icon = ft.Icons.PLAY_ARROW
            status_text.value = "Status: Paused"
            status_text.color = ft.Colors.AMBER_400
        else:
            pause_btn.text = "Pause Export"
            pause_btn.icon = ft.Icons.PAUSE
            status_text.value = "Status: Exporting..."
            status_text.color = ft.Colors.BLUE_400
        pause_btn.update()
        status_text.update()
        
    def on_clear_cache_click(e):
        deleted = discord_manager.clear_cache()
        if deleted:
            msg = f"Cleared cache: {', '.join(deleted)}"
            logging.info(msg)
            page.snack_bar = ft.SnackBar(ft.Text(msg))
        else:
            msg = "Cache is already empty."
            logging.info(msg)
            page.snack_bar = ft.SnackBar(ft.Text(msg))
        page.snack_bar.open = True
        page.update()

    def on_clear_history_click(e):
        deleted = discord_manager.clear_history()
        if deleted:
            msg = f"Deleted {len(deleted)} export files."
            logging.info(msg)
            page.snack_bar = ft.SnackBar(ft.Text(msg))
        else:
            msg = "No export history found."
            logging.info(msg)
            page.snack_bar = ft.SnackBar(ft.Text(msg))
        page.snack_bar.open = True
        page.update()

    start_export_btn = ft.ElevatedButton(
        text="Start Export", 
        icon=ft.Icons.DOWNLOAD, 
        disabled=True,
        bgcolor=ft.Colors.BLUE_600,
        color=ft.Colors.WHITE,
        height=50
    )
    
    stop_export_btn = ft.ElevatedButton(
        text="Stop Export", 
        icon=ft.Icons.STOP, 
        bgcolor=ft.Colors.RED_600, 
        color=ft.Colors.WHITE,
        on_click=on_stop_export_click,
        disabled=True,
        height=50
    )

    pause_btn = ft.ElevatedButton(
        text="Pause Export",
        icon=ft.Icons.PAUSE,
        on_click=on_pause_click,
        disabled=True,
        height=50
    )
    
    clear_cache_btn = ft.ElevatedButton(
        text="Clear Cache",
        icon=ft.Icons.DELETE_OUTLINE,
        on_click=on_clear_cache_click,
        bgcolor=ft.Colors.GREY_800,
        color=ft.Colors.WHITE70,
        height=40
    )
    
    clear_history_btn = ft.ElevatedButton(
        text="Clear History",
        icon=ft.Icons.DELETE_SWEEP,
        on_click=on_clear_history_click,
        bgcolor=ft.Colors.GREY_800,
        color=ft.Colors.WHITE70,
        height=40
    )

    # --- File Picker & Save ---
    import shutil
    
    def on_file_result(e: ft.FilePickerResultEvent):
        if not e.path:
            return
        
        destination_path = e.path
        logging.info(f"Selected save path: {destination_path}")
        
        try:
            source_file = config.get("export_path", "export.txt")
            if not os.path.exists(source_file):
                logging.error(f"Source file not found: {source_file}")
                page.snack_bar = ft.SnackBar(ft.Text(f"Error: Source file {source_file} not found!"))
                page.snack_bar.open = True
                page.update()
                return

            import shutil
            shutil.copy2(source_file, destination_path)
            logging.info(f"File saved to: {destination_path}")
            
            page.snack_bar = ft.SnackBar(ft.Text(f"Successfully saved to {destination_path}"))
            page.snack_bar.open = True
            page.update()
            
        except Exception as ex:
            logging.error(f"Error saving file: {ex}")
            page.snack_bar = ft.SnackBar(ft.Text(f"Error saving file: {ex}"))
            page.snack_bar.open = True
            page.update()

    file_picker = ft.FilePicker(on_result=on_file_result)
    page.overlay.append(file_picker)
    page.update() # Ensure overlay is updated

    def on_save_click(e):
        logging.info("Save button clicked. Opening save file dialog...")
        current_filename = config.get("export_path", "export.txt")
        file_picker.save_file(
            dialog_title="Save Export As", 
            file_name=current_filename,
            allowed_extensions=["txt"]
        )

    save_btn = ft.ElevatedButton(
        text="Save Export",
        icon=ft.Icons.SAVE,
        on_click=on_save_click,
        disabled=True, # Disabled until export is complete
        height=50
    )
    
    # --- Open Folder Fallback ---
    import subprocess
    import platform
    
    def on_open_folder_click(e):
        try:
            path = config.get("export_path", "export.txt")
            folder_path = os.path.dirname(os.path.abspath(path))
            
            logging.info(f"Opening folder: {folder_path}")
            
            if platform.system() == "Windows":
                os.startfile(folder_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.call(["open", folder_path])
            else:  # Linux
                subprocess.call(["xdg-open", folder_path])
                
        except Exception as ex:
            logging.error(f"Error opening folder: {ex}")
            page.snack_bar = ft.SnackBar(ft.Text(f"Error opening folder: {ex}"))
            page.snack_bar.open = True
            page.update()

    open_folder_btn = ft.ElevatedButton(
        text="Open Output Folder",
        icon=ft.Icons.FOLDER_OPEN,
        on_click=on_open_folder_click,
        disabled=True, # Disabled until export is complete
        height=50
    )

    # --- AI Toggle ---
    ai_switch = ft.Switch(
        label="Use AI Detection (HuggingFace)", 
        value=config.get("use_ai_detection", False),
        active_color=ft.Colors.GREEN_400
    )

    # --- Layout Components ---
    
    # Configuration Row
    config_row = ft.Row([
        server_dropdown,
        ai_switch
    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True)
    
    # Maintenance Row
    maintenance_row = ft.Row([
        clear_cache_btn,
        clear_history_btn
    ], alignment=ft.MainAxisAlignment.END, wrap=True, spacing=10)

    # Export Actions Row
    actions_row = ft.Row([
        start_export_btn, 
        pause_btn,
        stop_export_btn,
        save_btn,
        open_folder_btn
    ], alignment=ft.MainAxisAlignment.START, wrap=True, spacing=10)

    # --- Progress UI ---
    progress_text = ft.Text("Ready", size=16, weight=ft.FontWeight.W_500)
    progress_bar = ft.ProgressBar(width=None, color="amber", bgcolor="#eeeeee", visible=False) # width=None expands

    # Layout
    page.add(
        ft.Column([
            header,
            status_text,
            ft.Divider(height=20, color=ft.Colors.GREY_800),
            ft.Row([connect_btn], alignment=ft.MainAxisAlignment.START),
            ft.Divider(height=20, color=ft.Colors.GREY_800),
            ft.Row([
                ft.Text("Configuration", size=22, weight=ft.FontWeight.BOLD),
                maintenance_row
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            config_row,
            ft.Divider(height=20, color=ft.Colors.GREY_800),
            ft.Text("Channels", size=22, weight=ft.FontWeight.BOLD),
            channel_container, 
            ft.Divider(height=20, color=ft.Colors.GREY_800),
            actions_row,
            ft.Divider(height=20, color=ft.Colors.GREY_800),
            ft.Text("Progress", size=22, weight=ft.FontWeight.BOLD),
            progress_text,
            progress_bar,
            ft.Divider(height=20, color=ft.Colors.GREY_800),
            ft.Text("Logs", size=22, weight=ft.FontWeight.BOLD),
            log_container
        ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=15)
    )
    
    # Update start_export to use current config
    async def on_start_export_click_wrapper(e):
        logging.info("Export wrapper called.")
        # Update config from UI elements
        config["use_ai_detection"] = ai_switch.value
        
        # Generate unique filename
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"export_{timestamp}.txt"
        config["export_path"] = unique_filename
        
        # Disable save button during export
        save_btn.disabled = True
        open_folder_btn.disabled = True
        start_export_btn.disabled = True
        
        # Enable control buttons
        stop_export_btn.disabled = False
        pause_btn.disabled = False
        pause_btn.text = "Pause Export"
        pause_btn.icon = ft.Icons.PAUSE
        
        stop_export_btn.update()
        pause_btn.update()
        
        # Reset progress
        progress_text.value = "Starting export..."
        progress_bar.visible = True
        progress_bar.value = None # Indeterminate
        
        status_text.value = "Status: Exporting..."
        status_text.color = ft.Colors.BLUE_400
        status_text.update()
        
        page.update()
        
        # Progress callback
        def update_progress(processed, found):
            progress_text.value = f"Processed: {processed} messages | Found: {found} questions"
            progress_bar.value = None # Keep indeterminate as we don't know total
            page.update()

        # Call start_export with unique filename and callback
        selected_channels = []
        for c in channel_checkboxes.controls:
            if isinstance(c, ft.Checkbox) and c.data and c.value:
                selected_channels.append(c.data)
        
        if not selected_channels:
            page.snack_bar = ft.SnackBar(ft.Text("Please select at least one channel!"))
            page.snack_bar.open = True
            page.update()
            start_export_btn.disabled = False
            stop_export_btn.disabled = True
            pause_btn.disabled = True
            progress_bar.visible = False
            progress_text.value = "Ready"
            page.update()
            return

        await discord_manager.start_export(selected_channels, config, progress_callback=update_progress)
        
        logging.info("Export finished in wrapper. Enabling save button.")
        # Enable save button after export
        save_btn.disabled = False
        save_btn.update() 
        
        open_folder_btn.disabled = False
        open_folder_btn.update()
        
        start_export_btn.disabled = False
        stop_export_btn.disabled = True
        pause_btn.disabled = True
        
        progress_text.value = f"Export Complete! Saved to {unique_filename}"
        progress_bar.visible = False
        
        status_text.value = "Status: Idle"
        status_text.color = ft.Colors.GREY_400
        status_text.update()
        
        page.update()

    start_export_btn.on_click = on_start_export_click_wrapper

if __name__ == "__main__":
    import sys
    # Determine path to .env based on execution mode (frozen/executable or script)
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        base_dir = os.path.dirname(sys.executable)
    else:
        # Running as script
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
    env_path = os.path.join(base_dir, ".env")
    
    # Also check parent dir if not found (useful for dev)
    if not os.path.exists(env_path):
        parent_env = os.path.join(os.path.dirname(base_dir), ".env")
        if os.path.exists(parent_env):
            env_path = parent_env
            
    print(f"Loading .env from: {env_path}") # Print to console for debug
    load_dotenv(env_path)
    
    ft.app(target=main)
