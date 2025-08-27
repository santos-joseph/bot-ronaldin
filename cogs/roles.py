# cogs/roles.py
import discord
from discord import ui, app_commands
from discord.ext import commands
from datetime import datetime

# --- CONSTANTES ---
LOG_CHANNEL_ID = 1408151499565043822

TEAM_ROLES = {
    "Flamengo": 1407710978530869308, "Palmeiras": 1407710525328199800,
    "Cruzeiro": 1407710666885828751, "Bahia": 1407710737303863397,
    "Botafogo": 1407710857806352468, "Mirassol": 1407710917898010684,
    "São Paulo": 1407710172108816434, "Fluminense": 1407711160135974972,
    "Bragantino": 1407711284266401862, "Ceará SC": 1407711448393580604,
    "Atlético-MG": 1407711504182022324, "Internacional": 1407711572284932167,
    "Corinthians": 1407711645576204368, "Santos": 1407711893531136010,
    "Vasco da Gama": 1407711942759546890, "Vitória": 1407711986460131398,
    "Juventude": 1407712045247500348, "Fortaleza": 1407712110900805742,
    "Sport Recife": 1407712159416455280,
}

# --- FUNÇÃO DE LOG ---
async def log_role_change(bot: commands.Bot, interaction: discord.Interaction, old_role: discord.Role, new_role: discord.Role):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        print(f"Canal de log com ID {LOG_CHANNEL_ID} não encontrado.")
        return

    member = interaction.user
    embed = discord.Embed(title="🔄 Troca de Cargo de Time", color=discord.Color.blue(), timestamp=datetime.utcnow())
    embed.set_author(name=f"{member.display_name} ({member.id})", icon_url=member.display_avatar.url)

    old_role_text = old_role.mention if old_role else "Nenhum"
    new_role_text = new_role.mention if new_role else "Nenhum"

    embed.add_field(name="Cargo Anterior", value=old_role_text, inline=True)
    embed.add_field(name="Novo Cargo", value=new_role_text, inline=True)

    await log_channel.send(embed=embed)

# --- COMPONENTES DE UI ---

class TeamSelect(ui.Select):
    def __init__(self, bot_ref):
        self.bot = bot_ref
        options = [discord.SelectOption(label=team) for team in TEAM_ROLES.keys()]
        super().__init__(placeholder='Escolha seu time do coração...', options=options, custom_id="team_role_select")

    async def callback(self, interaction: discord.Interaction):
        member = interaction.user
        guild = interaction.guild
        
        # Identifica o cargo antigo
        old_role = next((r for r in member.roles if r.id in TEAM_ROLES.values()), None)

        # Identifica o novo cargo
        team_name = self.values[0]
        new_role_id = TEAM_ROLES[team_name]
        new_role = guild.get_role(new_role_id)

        if not new_role:
            return await interaction.response.send_message(f"⚠️ Cargo para '{team_name}' não encontrado!", ephemeral=True)

        # Evita ações desnecessárias se o usuário já tiver o cargo
        if old_role and old_role.id == new_role.id:
            return await interaction.response.send_message(f"Você já possui o cargo do **{new_role.name}**.", ephemeral=True)

        if old_role:
            await member.remove_roles(old_role, reason="Troca de time de coração")
        
        await member.add_roles(new_role, reason=f"Escolheu torcer para {team_name}")
        
        # Envia o log
        await log_role_change(self.bot, interaction, old_role, new_role)
        
        await interaction.response.send_message(f"🎉 Agora você é um torcedor(a) do **{new_role.name}**!", ephemeral=True)


class RemoveRoleButton(ui.Button):
    def __init__(self, bot_ref):
        self.bot = bot_ref
        super().__init__(label="Remover Cargo de Time", style=discord.ButtonStyle.danger, custom_id="remove_team_role_btn")

    async def callback(self, interaction: discord.Interaction):
        member = interaction.user
        
        # Encontra e remove todos os cargos de time que o usuário possa ter
        roles_to_remove = [r for r in member.roles if r.id in TEAM_ROLES.values()]

        if not roles_to_remove:
            return await interaction.response.send_message("Você não possui nenhum cargo de time para remover.", ephemeral=True)

        old_role = roles_to_remove[0] # Pega o primeiro para o log
        await member.remove_roles(*roles_to_remove, reason="Remoção de cargo de time")
        
        # Envia o log
        await log_role_change(self.bot, interaction, old_role, None)

        await interaction.response.send_message("Seu cargo de time foi removido com sucesso!", ephemeral=True)


class TeamSelectView(ui.View):
    def __init__(self, bot_ref):
        super().__init__(timeout=None)
        self.add_item(TeamSelect(bot_ref))
        self.add_item(RemoveRoleButton(bot_ref))


class Roles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.add_view(TeamSelectView(bot))

    @commands.command(name="cargos-time")
    async def roles_prefix(self, ctx: commands.Context):
        embed = discord.Embed(
            title="Gerenciamento de Cargos de Torcedor",
            description="Selecione seu time no menu abaixo para receber um cargo exclusivo ou clique no botão para remover."
        )
        await ctx.send(embed=embed, view=TeamSelectView(self.bot), delete_after=15)

    @app_commands.command(name="cargos-time", description="Abre o painel para escolher seu cargo de time.")
    async def roles_slash(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Gerenciamento de Cargos de Torcedor",
            description="Selecione seu time no menu abaixo para receber um cargo exclusivo ou clique no botão para remover."
        )
        await interaction.response.send_message(embed=embed, view=TeamSelectView(self.bot), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Roles(bot))
