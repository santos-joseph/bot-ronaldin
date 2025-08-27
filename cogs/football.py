# cogs/football.py
import os
import discord
import requests
from discord.ext import commands
from utils.webhook_manager import send_webhook

# --- CONSTANTES ---
BRASILEIRAO_ID = 10
API_BASE_URL = "https://api.api-futebol.com.br/v1/"

class Football(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_key = os.getenv('API_FUTEBOL_TOKEN')
        self.api_headers = {'Authorization': f'Bearer {self.api_key}'}

        if not self.api_key:
            print("[!] AVISO: API_FUTEBOL_TOKEN não encontrada. O módulo de futebol não funcionará.")

    def _make_api_request(self, endpoint):
        """Função auxiliar para fazer requisições à API com tratamento de erros."""
        if not self.api_key:
            return None, "A chave da API de futebol não foi configurada pelo desenvolvedor."
        try:
            response = requests.get(API_BASE_URL + endpoint, headers=self.api_headers, timeout=15)
            response.raise_for_status()
            return response.json(), None
        except requests.exceptions.Timeout:
            return None, "A API demorou muito para responder (timeout)."
        except requests.exceptions.HTTPError as e:
            return None, f"Ocorreu um erro ao contatar a API (Código: {e.response.status_code})."
        except requests.exceptions.RequestException as e:
            return None, f"Ocorreu um erro de conexão com a API."

    # --- COMANDO TABELA ---
    @commands.command(name="tabela", aliases=['classificacao'])
    async def tabela_prefix(self, ctx: commands.Context):
        await self._handle_tabela_command(ctx)

    @discord.app_commands.command(name="tabela", description="Mostra a tabela atual do Brasileirão Série A.")
    async def tabela_slash(self, interaction: discord.Interaction):
        await self._handle_tabela_command(interaction)

    async def _handle_tabela_command(self, context):
        """Lógica central para o comando de tabela."""
        data, error = self._make_api_request(f"campeonatos/{BRASILEIRAO_ID}/tabela")
        if error:
            embed = discord.Embed(title="Erro ao buscar Tabela", description=error)
            await send_webhook(context.channel, embed, bot_user=self.bot.user)
            return
        
        embed = discord.Embed(title="Tabela do Brasileirão Série A")
        description_lines = []
        for team in data:
            pos = team.get('posicao', 'N/A')
            nome = team.get('time', {}).get('nome_popular', 'Time')
            pts = team.get('pontos', 0)
            
            emoji = ""
            if pos <= 4: emoji = "🏆"  # Libertadores
            elif pos <= 6: emoji = "🥇" # Pré-Libertadores
            elif pos <= 12: emoji = "🥈" # Sul-Americana
            elif pos >= 17: emoji = "💀" # Rebaixamento
            
            description_lines.append(f"**{pos}º** {nome} {emoji} - `{pts}` pts")
        
        embed.description = "\n".join(description_lines)
        await send_webhook(context.channel, embed, bot_user=self.bot.user)

    # --- COMANDO ARTILHEIROS ---
    @commands.command(name="artilheiros", aliases=['goleadores'])
    async def artilheiros_prefix(self, ctx: commands.Context):
        await self._handle_artilheiros_command(ctx)

    @discord.app_commands.command(name="artilheiros", description="Mostra os maiores goleadores do Brasileirão.")
    async def artilheiros_slash(self, interaction: discord.Interaction):
        await self._handle_artilheiros_command(interaction)

    async def _handle_artilheiros_command(self, context):
        """Lógica central para o comando de artilheiros."""
        data, error = self._make_api_request(f"campeonatos/{BRASILEIRAO_ID}/artilharia")
        if error:
            embed = discord.Embed(title="Erro ao buscar Artilharia", description=error)
            await send_webhook(context.channel, embed, bot_user=self.bot.user)
            return

        embed = discord.Embed(title="Artilharia - Brasileirão Série A")
        description_lines = []
        for i, artilheiro in enumerate(data[:10]): # Pega os 10 primeiros
            nome = artilheiro.get('atleta', {}).get('nome_popular', 'Jogador')
            gols = artilheiro.get('gols', 0)
            time = artilheiro.get('time', {}).get('nome_popular', 'Time')
            description_lines.append(f"**{i+1}º** {nome} ({time}) - `{gols}` gols")
        
        embed.description = "\n".join(description_lines)
        await send_webhook(context.channel, embed, bot_user=self.bot.user)


async def setup(bot: commands.Bot):
    await bot.add_cog(Football(bot))
