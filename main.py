# main.py
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from utils.database import Database

# --- CONFIGURAÇÃO INICIAL ---
load_dotenv()
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class RonaldinBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="r!", intents=intents)
        self.db = Database()

    async def setup_hook(self):
        print("Carregando módulos (Cogs)...")
        cogs_folder = "./cogs"
        for filename in os.listdir(cogs_folder):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"[+] Módulo '{filename}' carregado.")
                except Exception as e:
                    print(f"[!] Falha ao carregar '{filename}': {e}")
        
        # <<<< CORREÇÃO AQUI >>>>
        # Lógica para limpar comandos antigos e evitar duplicação.
        guild_id = os.getenv("GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.clear_commands(guild=guild) # Limpa comandos antigos
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"Slash commands sincronizados com o servidor {guild_id}.")
        else:
            print("AVISO: GUILD_ID não definido no .env. Slash commands podem demorar para aparecer.")

    async def on_ready(self):
        print('------')
        print(f'Bot Online: {self.user.name}')
        print('------')

bot = RonaldinBot()

# --- TRATAMENTO DE ERRO GLOBAL ---
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"Comando não encontrado! Digite `{ctx.prefix}help` para ver a lista de comandos.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Está faltando um argumento! Verifique o uso correto com `{ctx.prefix}help {ctx.command.name}`.")
    else:
        print(f"Erro em um comando de prefixo: {error}")
        await ctx.send("Ocorreu um erro ao executar este comando.")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    # Trata o erro de permissão de forma mais amigável
    if isinstance(error, discord.app_commands.MissingRole):
        await interaction.response.send_message(f"Você não tem o cargo necessário para usar este comando.", ephemeral=True)
        return
        
    print(f"Erro em um slash command: {error}")
    if not interaction.response.is_done():
        await interaction.response.send_message("Ocorreu um erro ao executar este comando.", ephemeral=True)
    else:
        await interaction.followup.send("Ocorreu um erro ao executar este comando.", ephemeral=True)


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("ERRO CRÍTICO: DISCORD_TOKEN não encontrado no arquivo .env.")
    else:
        bot.run(token)
