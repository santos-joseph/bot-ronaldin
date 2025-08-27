# cogs/betting.py
import discord
from discord import app_commands, ui
from discord.ext import commands
from utils.webhook_manager import send_webhook, edit_webhook

BET_CREATOR_ROLE_ID = 1408073200310423652
BETS_CHANNEL_ID = 1408074183493156985
BET_NOTIFICATION_ROLE_ID = 1408120231703875755

class BetModal(ui.Modal, title='Faça sua Aposta no Bolão'):
    def __init__(self, bot, team_name: str):
        super().__init__()
        self.bot = bot
        self.team_name = team_name

    amount = ui.TextInput(label='Valor em FutCoins', placeholder='Ex: 100', style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet_amount = int(self.amount.value)
            if bet_amount <= 0: return await interaction.response.send_message("❌ O valor deve ser positivo.", ephemeral=True)
        except ValueError:
            return await interaction.response.send_message("❌ Insira um número válido.", ephemeral=True)

        user_id = interaction.user.id
        
        # <<<< MELHORIA AQUI >>>>
        # Lógica de reembolso ao trocar de aposta.
        bet_doc = self.bot.db.get_bet(interaction.message.id)
        previous_bet = next((p for p in bet_doc.get("participants", []) if p["user_id"] == user_id), None)
        
        refund_amount = 0
        if previous_bet:
            refund_amount = previous_bet['amount']

        balance = self.bot.db.get_balance(user_id) + refund_amount
        if balance < bet_amount:
            return await interaction.response.send_message(f"Saldo insuficiente! Você tem {balance - refund_amount} FutCoins.", ephemeral=True)

        # Devolve o dinheiro antigo e debita o novo
        if refund_amount > 0:
            self.bot.db.update_balance(user_id, refund_amount)
        
        self.bot.db.update_balance(user_id, -bet_amount)
        self.bot.db.update_user_stats(user_id, bets_made_inc=1, wagered_inc=bet_amount)
        self.bot.db.add_participant_bet(interaction.message.id, user_id, self.team_name, bet_amount)
        
        await interaction.response.send_message(f"✅ Aposta de **{bet_amount}** FutCoins registrada para **{self.team_name}**!", ephemeral=True)
        await update_bet_embed(interaction.message, self.bot)


class BetView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    async def handle_bet(self, interaction: discord.Interaction, team_type: str):
        bet_doc = self.bot.db.get_bet(interaction.message.id)
        if not bet_doc or bet_doc.get("status") == "closed":
            return await interaction.response.send_message("Este bolão está encerrado.", ephemeral=True)
        
        team_name = bet_doc[team_type]
        await interaction.response.send_modal(BetModal(self.bot, team_name))

    @ui.button(label="Apostar Time A", style=discord.ButtonStyle.primary, custom_id="bet_home_team")
    async def home_button(self, i: discord.Interaction, b: ui.Button): await self.handle_bet(i, "team_home")

    @ui.button(label="Apostar Time B", style=discord.ButtonStyle.secondary, custom_id="bet_away_team")
    async def away_button(self, i: discord.Interaction, b: ui.Button): await self.handle_bet(i, "team_away")

    @ui.button(label="Cancelar Aposta", style=discord.ButtonStyle.danger, custom_id="bet_cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        user_id = interaction.user.id
        bet_doc = self.bot.db.get_bet(interaction.message.id)
        if not bet_doc or bet_doc.get("status") == "closed":
            return await interaction.response.send_message("Este bolão está encerrado.", ephemeral=True)

        user_bet = next((p for p in bet_doc.get("participants", []) if p["user_id"] == user_id), None)

        if not user_bet:
            return await interaction.response.send_message("Você não tem uma aposta registrada neste bolão.", ephemeral=True)

        # Devolve o dinheiro e remove a aposta do DB
        refund_amount = user_bet['amount']
        self.bot.db.update_balance(user_id, refund_amount)
        self.bot.db.add_participant_bet(interaction.message.id, user_id, "", -1) # Gambiarra para remover com pull/push

        await interaction.response.send_message(f"✅ Sua aposta de {refund_amount} FutCoins foi cancelada e o valor devolvido.", ephemeral=True)
        await update_bet_embed(interaction.message, self.bot)


async def update_bet_embed(message: discord.Message, bot):
    bet_doc = bot.db.get_bet(message.id)
    if not bet_doc: return

    embed = message.embeds[0]
    embed.clear_fields()

    home_bets = [p for p in bet_doc.get("participants", []) if p["bet_on"] == bet_doc["team_home"]]
    away_bets = [p for p in bet_doc.get("participants", []) if p["bet_on"] == bet_doc["team_away"]]
    total_home = sum(b['amount'] for b in home_bets)
    total_away = sum(b['amount'] for b in away_bets)
    home_text = f"**Total: {total_home} FutCoins**\n" + "\n".join([f"<@{b['user_id']}> ({b['amount']})" for b in home_bets]) if home_bets else "Nenhuma aposta"
    away_text = f"**Total: {total_away} FutCoins**\n" + "\n".join([f"<@{b['user_id']}> ({b['amount']})" for b in away_bets]) if away_bets else "Nenhuma aposta"

    embed.add_field(name=f"Apostas em {bet_doc['team_home']}", value=home_text, inline=True)
    embed.add_field(name=f"Apostas em {bet_doc['team_away']}", value=away_text, inline=True)
    
    view = BetView(bot)
    view.children[0].label = bet_doc["team_home"]
    view.children[1].label = bet_doc["team_away"]
    await edit_webhook(message.channel, message.id, embed, view=view, bot_user=bot.user)


class Betting(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.add_view(BetView(bot))

    bolao_group = app_commands.Group(name="bolao", description="Comandos para criar e gerenciar bolões.")

    @bolao_group.command(name="proximo", description="Cria um novo bolão de aposta para o próximo jogo.")
    @app_commands.checks.has_role(BET_CREATOR_ROLE_ID)
    async def bolao_proximo_slash(self, interaction: discord.Interaction, titulo: str, time_a: str, time_b: str, campeonato: str = None, data_hora: str = None):
        bets_channel = self.bot.get_channel(BETS_CHANNEL_ID)
        if not bets_channel:
            return await interaction.response.send_message("Canal de apostas não encontrado.", ephemeral=True)

        description = f"Quem vence a partida entre **{time_a}** e **{time_b}**?"
        if data_hora: description = f"🗓️ **Data:** {data_hora}\n" + description
        
        embed = discord.Embed(title=f"🏆 Bolão: {titulo}", description=description)
        if campeonato: embed.set_author(name=campeonato)
            
        view = BetView(self.bot)
        view.children[0].label = time_a
        view.children[1].label = time_b

        message = await send_webhook(
            bets_channel, embed, view, self.bot.user,
            content=f"<@&{BET_NOTIFICATION_ROLE_ID}>"
        )

        bet_data = {"message_id": message.id, "title": titulo, "team_home": time_a, "team_away": time_b, "status": "open", "participants": []}
        self.bot.db.create_bet(bet_data)
        
        await update_bet_embed(message, self.bot)
        await interaction.response.send_message(f"Bolão criado com sucesso em {bets_channel.mention}!", ephemeral=True)

    @bolao_group.command(name="resultado", description="[Admin] Define o resultado de um bolão.")
    @app_commands.checks.has_role(BET_CREATOR_ROLE_ID)
    async def bolao_resultado_slash(self, interaction: discord.Interaction, id_da_mensagem: str, vencedor: str):
        try: message_id = int(id_da_mensagem)
        except ValueError: return await interaction.response.send_message("ID da mensagem inválido.", ephemeral=True)

        bet_doc = self.bot.db.get_bet(message_id)
        if not bet_doc or bet_doc['status'] == 'closed':
            return await interaction.response.send_message("Bolão não encontrado ou já encerrado.", ephemeral=True)

        self.bot.db.close_bet(message_id)
        winners = [p for p in bet_doc.get("participants", []) if p["bet_on"].lower() == vencedor.lower()]
        
        result_desc = f"O bolão **'{bet_doc.get('title', 'N/A')}'** foi encerrado!\nO vencedor foi **{vencedor}**."
        
        if not winners:
            result_desc += "\n\nNinguém acertou o palpite."
        else:
            winner_lines = []
            for winner in winners:
                payout = winner['amount'] * 2
                self.bot.db.update_balance(winner['user_id'], payout)
                self.bot.db.update_user_stats(winner['user_id'], bets_won_inc=1, won_inc=payout)
                winner_lines.append(f"🏅 <@{winner['user_id']}> ganhou **{payout}** FutCoins!")
            result_desc += "\n\n**Vencedores:**\n" + "\n".join(winner_lines)

        result_embed = discord.Embed(title="🏁 Bolão Encerrado!", description=result_desc)
        await send_webhook(interaction.channel, result_embed, bot_user=self.bot.user)
        
        try:
            bets_channel = self.bot.get_channel(BETS_CHANNEL_ID)
            original_message = await bets_channel.fetch_message(message_id)
            original_embed = original_message.embeds[0]
            original_embed.description += "\n\n**APOSTAS ENCERRADAS**"
            await edit_webhook(bets_channel, message_id, original_embed, view=None, bot_user=self.bot.user)
        except Exception as e:
            print(f"Não foi possível editar a mensagem original do bolão: {e}")

        await interaction.response.send_message("Resultado processado!", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Betting(bot))
