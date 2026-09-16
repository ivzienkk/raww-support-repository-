from __future__ import annotations

import asyncio
import importlib
import logging
import threading
from pathlib import Path

import discord
from discord.ext import commands
from waitress import serve

from .config import load_settings
from .database import Database
from .web.app import DashboardBridge, create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("discord_app")

COGS = ("giveaways", "moderation", "logs", "automod")


class CommunityBot(commands.Bot):
    def __init__(self, db: Database) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents)
        self.db = db
        self.dashboard_bridge = DashboardBridge()
        self.giveaway_cog = None

    async def setup_hook(self) -> None:
        for name in COGS:
            module = importlib.import_module(f"{__package__}.cogs.{name}")
            await module.setup(self)
        if self.giveaway_cog:
            self.dashboard_bridge.create_giveaway_callback = (
                self.giveaway_cog.create_from_dashboard
            )
        synced = await self.tree.sync()
        logger.info("Sincronizados %s comandos slash", len(synced))

    async def on_ready(self) -> None:
        for guild in self.guilds:
            self.db.ensure_guild(guild.id)
        logger.info("Bot conectado como %s en %s servidores", self.user, len(self.guilds))

    async def on_message(self, message: discord.Message) -> None:
        if self.giveaway_cog:
            await self.giveaway_cog.handle_claim_message(message)
        await self.process_commands(message)

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError
    ) -> None:
        if isinstance(error, discord.app_commands.MissingPermissions):
            message = "No tienes permisos suficientes para usar este comando."
        else:
            logger.exception("Error en comando slash", exc_info=error)
            message = "Ocurrió un error al ejecutar el comando."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


def start_dashboard(bot: CommunityBot, settings: object) -> threading.Thread:
    app = create_app(
        bot.db,
        bot.dashboard_bridge,
        getattr(settings, "dashboard_token"),
    )
    thread = threading.Thread(
        target=serve,
        kwargs={
            "app": app,
            "host": getattr(settings, "dashboard_host"),
            "port": getattr(settings, "dashboard_port"),
            "threads": 4,
        },
        daemon=True,
        name="flask-dashboard",
    )
    thread.start()
    return thread


def main() -> None:
    settings = load_settings()
    db = Database(settings.database_path)
    bot = CommunityBot(db)

    async def runner() -> None:
        bot.dashboard_bridge.loop = asyncio.get_running_loop()
        start_dashboard(bot, settings)
        if not settings.discord_token:
            logger.warning(
                "DISCORD_TOKEN no está configurado. Dashboard disponible; bot detenido."
            )
            await asyncio.Event().wait()
        else:
            await bot.start(settings.discord_token)

    asyncio.run(runner())


if __name__ == "__main__":
    main()
