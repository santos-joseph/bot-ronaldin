# cogs/admin.py
import discord
from discord import app_commands
from discord.ext import commands
from utils.webhook_manager import send_webhook

# <<<< IMPORTANTE >>>>
# Coloque seu ID de usuário do Discord aqui para ter acesso aos comandos de dono.
# Para pegar seu ID, ative o Modo Desenvolvedor no Discord, clique com o botão direito no seu nome e "Copiar ID do usuário".
OWNER_ID = 1386337469250666556 # SUBSTITUA ESTE VALOR

class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Função de verificação para saber se o autor é o dono do bot
    async def is_owner(interaction: discord.Interaction) -> bool:
        return interaction.user.id == OWNER_ID

    @app_commands.command(name="setfutcoins", description="[Dono] Define o saldo de FutCoins de um membro.")
    @app_commands.describe(membro="O membro para alterar o saldo.", quantia="O novo saldo de FutCoins.")
    @app_commands.check(is_owner)
    async def setfutcoins_slash(self, interaction: discord.Interaction, membro: discord.Member, quantia: int):
        if quantia < 0:
            return await interaction.response.send_message("A quantia não pode ser negativa.", ephemeral=True)
        
        self.bot.db.set_balance(membro.id, quantia)
        await interaction.response.send_message(f"✅ O saldo de {membro.mention} foi definido para **{quantia}** FutCoins.", ephemeral=True)

    @commands.command(name="setfutcoins")
    @commands.is_owner()
    async def setfutcoins_prefix(self, ctx: commands.Context, membro: discord.Member = None, quantia: int = None):
        if membro is None or quantia is None:
            return await ctx.send(f"Uso: `{ctx.prefix}setfutcoins <@membro> <quantia>`")
        if quantia < 0:
            return await ctx.send("A quantia não pode ser negativa.")
            
        self.bot.db.set_balance(membro.id, quantia)
        await ctx.send(f"✅ O saldo de {membro.mention} foi definido para **{quantia}** FutCoins.")

    @app_commands.command(name="estatisticasusuario", description="[Admin] Mostra as estatísticas de um usuário.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def userstats_slash(self, interaction: discord.Interaction, membro: discord.Member):
        await self._handle_userstats(interaction, membro)

    @commands.command(name="estatisticasusuario", aliases=['userstats'])
    @commands.has_permissions(manage_guild=True)
    async def userstats_prefix(self, ctx: commands.Context, membro: discord.Member = None):
        if membro is None:
            return await ctx.send(f"Uso correto: `{ctx.prefix}estatisticasusuario <@membro>`")
        await self._handle_userstats(ctx, membro)

    async def _handle_userstats(self, ctx_or_i, membro: discord.Member):
        user_data = self.bot.db.get_user_data(membro.id)
        stats = user_data.get("stats", {})

        embed = discord.Embed(title=f"Estatísticas de {membro.display_name}", color=membro.color)
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.add_field(name="💰 Saldo", value=f"`{user_data.get('balance', 0)}` FutCoins", inline=False)
        embed.add_field(name="Apostas Feitas", value=stats.get('bets_made', 0), inline=True)
        embed.add_field(name="Apostas Vencidas", value=stats.get('bets_won', 0), inline=True)
        embed.add_field(name="Total Apostado", value=f"`{stats.get('total_wagered', 0)}` FutCoins", inline=True)
        embed.add_field(name="Total Ganho", value=f"`{stats.get('total_won', 0)}` FutCoins", inline=True)

        if isinstance(ctx_or_i, discord.Interaction):
            await ctx_or_i.response.send_message(embed=embed, ephemeral=True)
        else:
            await send_webhook(ctx_or_i.channel, embed, bot_user=self.bot.user)

    @app_commands.command(name="webhook", description="[Admin] Envia um embed customizado via webhook.")
    @app_commands.describe(canal="O canal para a mensagem.", titulo="O título do embed.", mensagem="O conteúdo do embed.", cor="Cor em HEX (ex: #FFD700).", thumbnail_url="URL da imagem pequena.", image_url="URL da imagem grande.", avatar_url="URL da foto do webhook.")
    @app_commands.checks.has_permissions(administrator=True)
    async def webhook_slash(self, interaction: discord.Interaction, canal: discord.TextChannel, titulo: str, mensagem: str, cor: str = None, thumbnail_url: str = None, image_url: str = None, avatar_url: str = None):
        try:
            embed = discord.Embed(title=titulo, description=mensagem)
            if cor:
                try: embed.color = discord.Color(int(cor.replace("#", ""), 16))
                except ValueError: return await interaction.response.send_message("Formato de cor inválido.", ephemeral=True)
            if thumbnail_url: embed.set_thumbnail(url=thumbnail_url)
            if image_url: embed.set_image(url=image_url)

            await send_webhook(canal, embed, bot_user=self.bot.user, avatar_url=avatar_url)
            await interaction.response.send_message(f"Webhook enviado com sucesso!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Ocorreu um erro: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
