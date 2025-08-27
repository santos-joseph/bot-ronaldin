# cogs/games.py
import discord
from discord import app_commands, ui
from discord.ext import commands

class TicTacToeView(ui.View):
    def __init__(self, bot, challenger: discord.Member, opponent: discord.Member, bet: int):
        super().__init__(timeout=180) # Timeout de 3 minutos para a partida
        self.bot = bot
        self.challenger = challenger
        self.opponent = opponent
        self.bet = bet
        self.turn = challenger
        self.board = [0] * 9  # 0: Vazio, 1: Challenger (X), 2: Opponent (O)
        self.symbols = {1: "❌", 2: "⭕"}
        self.message = None

        # Adiciona os botões ao View
        for i in range(9):
            self.add_item(TicTacToeButton(row=i // 3))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Verifica se é o jogador do turno atual que está interagindo
        if interaction.user != self.turn:
            await interaction.response.send_message("Não é a sua vez de jogar!", ephemeral=True)
            return False
        return True
    
    def create_embed(self, status: str):
        embed = discord.Embed(title="Jogo da Velha  Tic-Tac-Toe", color=discord.Color.blue())
        embed.description = status
        return embed

    async def update_board(self, interaction: discord.Interaction):
        # Lógica para verificar vitória ou empate
        winner = self.check_winner()
        if winner is not None:
            # Paga o vencedor e encerra o jogo
            winner_user = self.challenger if winner == 1 else self.opponent
            payout = self.bet * 2
            self.bot.db.update_balance(winner_user.id, payout)
            status = f"🏆 **{winner_user.mention}** venceu e ganhou **{payout}** FutCoins!"
            await self.end_game(interaction, status)
            return

        if all(cell != 0 for cell in self.board):
            # Devolve o dinheiro em caso de empate
            self.bot.db.update_balance(self.challenger.id, self.bet)
            self.bot.db.update_balance(self.opponent.id, self.bet)
            status = f"🤝 Deu velha! O valor de **{self.bet}** FutCoins foi devolvido a ambos."
            await self.end_game(interaction, status)
            return

        # Passa o turno
        self.turn = self.opponent if self.turn == self.challenger else self.challenger
        status = f"É a vez de **{self.turn.mention}** {self.symbols[1 if self.turn == self.challenger else 2]}"
        embed = self.create_embed(status)
        await interaction.response.edit_message(embed=embed, view=self)

    def check_winner(self):
        lines = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
        for a, b, c in lines:
            if self.board[a] == self.board[b] == self.board[c] and self.board[a] != 0:
                return self.board[a]
        return None

    async def end_game(self, interaction: discord.Interaction, status: str):
        for item in self.children:
            item.disabled = True
        
        embed = self.create_embed(status)
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

class TicTacToeButton(ui.Button['TicTacToeView']):
    def __init__(self, row: int):
        super().__init__(style=discord.ButtonStyle.secondary, label='\u200b', row=row)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        player_value = 1 if interaction.user == view.challenger else 2

        # Marca a jogada no tabuleiro lógico e no botão
        self.style = discord.ButtonStyle.success if player_value == 1 else discord.ButtonStyle.primary
        self.label = view.symbols[player_value]
        self.disabled = True
        
        # Descobre qual botão foi pressionado (pela posição na lista de children)
        button_index = view.children.index(self)
        view.board[button_index] = player_value

        await view.update_board(interaction)


class ConfirmChallengeView(ui.View):
    def __init__(self, bot, challenger: discord.Member, opponent: discord.Member, bet: int):
        super().__init__(timeout=60)
        self.bot = bot
        self.challenger = challenger
        self.opponent = opponent
        self.bet = bet
        self.confirmed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Apenas o oponente pode aceitar/recusar
        if interaction.user != self.opponent:
            await interaction.response.send_message("Apenas o oponente pode responder ao desafio.", ephemeral=True)
            return False
        return True

    @ui.button(label="Aceitar", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        # Debita o valor dos jogadores
        self.bot.db.update_balance(self.challenger.id, -self.bet)
        self.bot.db.update_balance(self.opponent.id, -self.bet)

        # Inicia o jogo
        game_view = TicTacToeView(self.bot, self.challenger, self.opponent, self.bet)
        initial_status = f"É a vez de **{game_view.turn.mention}** {game_view.symbols[1]}"
        embed = game_view.create_embed(initial_status)
        await interaction.response.edit_message(content=f"Desafio aceito! Boa sorte, **{self.challenger.display_name}** e **{self.opponent.display_name}**!", embed=embed, view=game_view)
        self.confirmed = True
        self.stop()

    @ui.button(label="Recusar", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content=f"😔 {self.opponent.mention} recusou o desafio.", embed=None, view=None)
        self.stop()

    async def on_timeout(self):
        if not self.confirmed:
            # Edita a mensagem original se o tempo acabar
            if hasattr(self, 'message') and self.message:
                 await self.message.edit(content="O desafio expirou.", embed=None, view=None)


class Games(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="jogodavelha", description="Desafie alguém para uma partida de Jogo da Velha apostando FutCoins.")
    @app_commands.describe(oponente="O membro que você quer desafiar.", valor="A quantidade de FutCoins a ser apostada.")
    async def tic_tac_toe(self, interaction: discord.Interaction, oponente: discord.Member, valor: int):
        desafiante = interaction.user

        if oponente == desafiante:
            return await interaction.response.send_message("Você não pode desafiar a si mesmo!", ephemeral=True)
        if oponente.bot:
            return await interaction.response.send_message("Você não pode desafiar um bot!", ephemeral=True)
        if valor <= 0:
            return await interaction.response.send_message("O valor da aposta deve ser positivo.", ephemeral=True)

        # Verifica o saldo de ambos
        saldo_desafiante = self.bot.db.get_balance(desafiante.id)
        saldo_oponente = self.bot.db.get_balance(oponente.id)

        if saldo_desafiante < valor:
            return await interaction.response.send_message(f"Você não tem saldo suficiente! Seu saldo: {saldo_desafiante} FutCoins.", ephemeral=True)
        if saldo_oponente < valor:
            return await interaction.response.send_message(f"O oponente ({oponente.display_name}) não tem saldo suficiente! Saldo dele: {saldo_oponente} FutCoins.", ephemeral=True)

        # Envia o desafio para confirmação
        view = ConfirmChallengeView(self.bot, desafiante, oponente, valor)
        await interaction.response.send_message(
            content=f"⚔️ **{oponente.mention}**, você foi desafiado por **{desafiante.mention}** para um Jogo da Velha valendo **{valor}** FutCoins! Você aceita?",
            view=view
        )
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))