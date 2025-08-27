# cogs/economy.py
import discord
import random
import asyncio
from discord import app_commands, ui
from discord.ext import commands, tasks
from utils.webhook_manager import send_webhook
from datetime import datetime, timedelta
from enum import Enum

# --- LÓGICA BASE DO BLACKJACK ---
suits = ('Copas ♥', 'Ouros ♦', 'Paus ♣', 'Espadas ♠')
ranks = ('2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A')
values = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 10, 'Q': 10, 'K': 10, 'A': 11}

# --- CONFIGURAÇÃO DE EMOJIS (IMPORTANTE!) ---
DICE_EMOJI_NAMES = {
    "blue": {
        1: "game_dice_1_blue", 2: "game_dice_2_blue", 3: "game_dice_3_blue",
        4: "game_dice_4_blue", 5: "game_dice_5_blue", 6: "game_dice_6_blue"
    },
    "red": {
        1: "game_dice_1_red", 2: "game_dice_2_red", 3: "game_dice_3_red",
        4: "game_dice_4_red", 5: "game_dice_5_red", 6: "game_dice_6_red"
    },
    "rolling_blue": "game_dice_rolling_blue",
    "rolling_red": "game_dice_rolling_red"
}

class Card:
    def __init__(self, suit, rank):
        self.suit = suit
        self.rank = rank
    def __str__(self):
        return f'`{self.rank}{self.suit[-1]}`'

class Deck:
    def __init__(self):
        self.deck = [Card(suit, rank) for suit in suits for rank in ranks]
        self.shuffle()
    def shuffle(self):
        random.shuffle(self.deck)
        if len(self.deck) < 20: # Recria o baralho se estiver acabando
             self.deck = [Card(suit, rank) for suit in suits for rank in ranks]
             random.shuffle(self.deck)
    def deal(self):
        return self.deck.pop()

class Hand:
    def __init__(self):
        self.cards = []
        self.value = 0
        self.aces = 0
    def add_card(self, card):
        self.cards.append(card)
        self.value += values[card.rank]
        if card.rank == 'A':
            self.aces += 1
        self.adjust_for_ace()
    def adjust_for_ace(self):
        while self.value > 21 and self.aces:
            self.value -= 10
            self.aces -= 1
    def __str__(self):
        return ", ".join(str(card) for card in self.cards)

# --- LÓGICA DO JOGO DA VELHA ---

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
        embed = discord.Embed(title="Jogo da Velha | Tic-Tac-Toe", color=discord.Color.blue())
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
        self.message = None # Adicionado para guardar a mensagem original

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
        if not self.confirmed and self.message:
            # Edita a mensagem original se o tempo acabar
            await self.message.edit(content="O desafio expirou.", embed=None, view=None)


# --- NOVAS CLASSES PARA BLACKJACK EM MESA ---

class GameState(Enum):
    WAITING_FOR_BETS = 1
    DEALING_CARDS = 2
    PLAYER_ACTIONS = 3
    DEALER_TURN = 4
    PAYOUTS = 5

class LiveBlackjackPlayer:
    def __init__(self, member: discord.Member):
        self.member = member
        self.hand = Hand()
        self.bet = 0
        self.status = 'playing'  # playing, stand, busted, blackjack

class LiveBlackjackTable:
    def __init__(self, bot, channel: discord.TextChannel):
        self.bot = bot
        self.channel = channel
        self.message: discord.WebhookMessage = None
        self.view: LiveBlackjackView = None
        self.state = GameState.WAITING_FOR_BETS
        self.countdown = 20
        self.deck = Deck()
        self.dealer_hand = Hand()
        self.players = {}  # {member_id: LiveBlackjackPlayer}
        self.spectators = set()
        self.active = True

    async def tick(self):
        if not self.active: return
        self.countdown -= 1
        if self.countdown <= 0:
            await self.next_state()
        
        try:
            await self.update_embed()
        except discord.NotFound:
            print(f"Mensagem da mesa de Blackjack no canal {self.channel.id} não encontrada. Encerrando mesa.")
            self.active = False

    async def next_state(self):
        if self.state == GameState.WAITING_FOR_BETS:
            if not any(p.bet > 0 for p in self.players.values()):
                self.countdown = 20
                return
            self.state = GameState.DEALING_CARDS
            await self.next_state()

        elif self.state == GameState.DEALING_CARDS:
            self.deck.shuffle()
            for player in self.players.values():
                player.hand = Hand()
                player.status = 'playing' if player.bet > 0 else 'spectating'
            self.dealer_hand = Hand()
            for _ in range(2):
                self.dealer_hand.add_card(self.deck.deal())
                for player in self.players.values():
                    if player.bet > 0:
                        player.hand.add_card(self.deck.deal())
            for player in self.players.values():
                if player.bet > 0 and player.hand.value == 21:
                    player.status = 'blackjack'
            self.state = GameState.PLAYER_ACTIONS
            self.countdown = 20

        elif self.state == GameState.PLAYER_ACTIONS:
            for player in self.players.values():
                if player.status == 'playing':
                    player.status = 'stand'
            self.state = GameState.DEALER_TURN
            await self.next_state()

        elif self.state == GameState.DEALER_TURN:
            while self.dealer_hand.value < 17:
                self.dealer_hand.add_card(self.deck.deal())
            self.state = GameState.PAYOUTS
            self.countdown = 15

        elif self.state == GameState.PAYOUTS:
            await self.process_payouts()
            self.state = GameState.WAITING_FOR_BETS
            self.countdown = 20
            for player in self.players.values():
                player.bet = 0
    
    async def process_payouts(self):
        dealer_val = self.dealer_hand.value
        for player in self.players.values():
            if player.bet == 0: continue
            if player.status == 'blackjack':
                payout = int(player.bet * 2.5)
                self.bot.db.update_balance(player.member.id, payout)
            elif player.status == 'busted': continue
            elif dealer_val > 21 or player.hand.value > dealer_val:
                payout = player.bet * 2
                self.bot.db.update_balance(player.member.id, payout)
            elif player.hand.value == dealer_val:
                payout = player.bet
                self.bot.db.update_balance(player.member.id, payout)

    async def update_embed(self):
        state_map = {
            GameState.WAITING_FOR_BETS: (f"Apostas Abertas! ({self.countdown}s)", discord.Color.gold()),
            GameState.PLAYER_ACTIONS: (f"Façam suas jogadas! ({self.countdown}s)", discord.Color.blue()),
            GameState.PAYOUTS: (f"Resultados! Próxima rodada em {self.countdown}s", discord.Color.green()),
            GameState.DEALER_TURN: ("Vez do Dealer...", discord.Color.purple()),
            GameState.DEALING_CARDS: ("Distribuindo cartas...", discord.Color.orange())
        }
        title, color = state_map.get(self.state, ("Carregando...", discord.Color.default()))
        embed = discord.Embed(title=f"Mesa de Blackjack - {title}", color=color)

        dealer_hand_str = ""
        if self.state in [GameState.PLAYER_ACTIONS, GameState.DEALING_CARDS] and self.dealer_hand.cards:
            dealer_hand_str = f"{str(self.dealer_hand.cards[0])}, `?`  **(?)**"
        else:
            dealer_hand_str = f"{str(self.dealer_hand)}  **({self.dealer_hand.value})**"
        embed.description = f"**Dealer:** {dealer_hand_str}\n\n"

        player_list = "\n".join(self.format_player_line(p) for p in self.players.values())
        spectator_list = ", ".join(f"{s.display_name}" for s in self.spectators)

        embed.add_field(name="Jogadores", value=player_list or "Nenhum jogador na mesa.", inline=False)
        if self.spectators:
            embed.add_field(name="Espectadores", value=spectator_list, inline=False)
        
        await self.message.edit(embed=embed, view=self.view)

    def format_player_line(self, player: LiveBlackjackPlayer):
        status_emoji = {'playing': '▶️', 'stand': '⏹️', 'busted': '💥', 'blackjack': '👑', 'spectating': '👀'}
        if player.bet > 0:
            hand_str = f"{str(player.hand)} **({player.hand.value})**"
            return f"{status_emoji.get(player.status, '')} **{player.member.display_name}**: {hand_str} | Aposta: `{player.bet}`"
        else:
            return f"👀 **{player.member.display_name}**: `(Aguardando para apostar)`"

    async def add_player(self, member: discord.Member):
        if member.id not in self.players and len(self.players) < 5:
            self.players[member.id] = LiveBlackjackPlayer(member)
            if member in self.spectators:
                self.spectators.remove(member)
        elif member.id not in self.players:
             self.spectators.add(member)

    async def remove_player(self, member: discord.Member):
        if member.id in self.players:
            del self.players[member.id]
        if member in self.spectators:
            self.spectators.remove(member)
        if not self.players and not self.spectators:
            self.active = False
            await self.message.edit(content="Mesa encerrada por falta de jogadores.", embed=None, view=None)

    async def place_bet(self, interaction: discord.Interaction, amount: int):
        user = interaction.user
        player = self.players.get(user.id)
        if not player: return await interaction.response.send_message("Você não está na mesa como jogador.", ephemeral=True)
        balance = self.bot.db.get_balance(user.id)
        if balance < amount: return await interaction.response.send_message("Saldo insuficiente.", ephemeral=True)
        if player.bet > 0: self.bot.db.update_balance(user.id, player.bet)
        self.bot.db.update_balance(user.id, -amount)
        player.bet = amount
        player.status = 'playing'
        await interaction.response.send_message(f"✅ Aposta de `{amount}` FutCoins registrada!", ephemeral=True)

    async def player_action(self, interaction: discord.Interaction, action: str):
        user = interaction.user
        player = self.players.get(user.id)
        if not player or player.bet <= 0: return await interaction.response.defer()
        if self.state != GameState.PLAYER_ACTIONS:
            return await interaction.response.send_message("Aguarde a fase de ações para jogar.", ephemeral=True, delete_after=5)
        if player.status != 'playing':
            return await interaction.response.send_message("Você não pode mais fazer jogadas nesta rodada.", ephemeral=True, delete_after=5)
        if action == 'hit':
            player.hand.add_card(self.deck.deal())
            if player.hand.value > 21:
                player.status = 'busted'
        elif action == 'stand':
            player.status = 'stand'
        await interaction.response.defer()

class BlackjackBetModal(ui.Modal, title="Faça sua Aposta"):
    def __init__(self, table: LiveBlackjackTable):
        super().__init__()
        self.table = table
    
    amount = ui.TextInput(label='Valor em FutCoins', placeholder='Ex: 100', style=discord.TextStyle.short)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet_amount = int(self.amount.value)
            if bet_amount <= 0: return await interaction.response.send_message("O valor deve ser positivo.", ephemeral=True)
            await self.table.place_bet(interaction, bet_amount)
        except ValueError:
            await interaction.response.send_message("Insira um número válido.", ephemeral=True)

class LiveBlackjackView(ui.View):
    def __init__(self, table: LiveBlackjackTable):
        super().__init__(timeout=None)
        self.table = table

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in self.table.players and interaction.user not in self.table.spectators:
            await self.table.add_player(interaction.user)
        return True

    @ui.button(label="Apostar", style=discord.ButtonStyle.green, custom_id="bj_bet")
    async def bet(self, interaction: discord.Interaction, button: ui.Button):
        if self.table.state != GameState.WAITING_FOR_BETS:
            return await interaction.response.send_message("As apostas estão encerradas no momento.", ephemeral=True, delete_after=5)
        if interaction.user.id not in self.table.players:
             return await interaction.response.send_message("A mesa de jogadores está cheia. Você está como espectador.", ephemeral=True)
        await interaction.response.send_modal(BlackjackBetModal(self.table))

    @ui.button(label="Comprar (Hit)", style=discord.ButtonStyle.primary, custom_id="bj_live_hit")
    async def hit(self, interaction: discord.Interaction, button: ui.Button):
        await self.table.player_action(interaction, 'hit')

    @ui.button(label="Parar (Stand)", style=discord.ButtonStyle.secondary, custom_id="bj_live_stand")
    async def stand(self, interaction: discord.Interaction, button: ui.Button):
        await self.table.player_action(interaction, 'stand')

    @ui.button(label="Sair da Mesa", style=discord.ButtonStyle.danger, custom_id="bj_leave")
    async def leave(self, interaction: discord.Interaction, button: ui.Button):
        await self.table.remove_player(interaction.user)
        await interaction.response.send_message("Você saiu da mesa.", ephemeral=True, delete_after=5)
        
# --- CLASSES ANTIGAS (PAYMENT, SOLO BLACKJACK, BACBO) ---
class ConfirmPaymentView(ui.View):
    def __init__(self, from_user, to_user, amount, bot):
        super().__init__(timeout=60)
        self.from_user = from_user
        self.to_user = to_user
        self.amount = amount
        self.bot = bot
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.from_user.id:
            await interaction.response.send_message("Apenas quem iniciou o pagamento pode interagir.", ephemeral=True)
            return False
        return True
    @ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        self.bot.db.update_balance(self.from_user.id, -self.amount)
        self.bot.db.update_balance(self.to_user.id, self.amount)
        embed = discord.Embed(description=f"✅ **{self.from_user.mention}** transferiu **{self.amount}** FutCoins para **{self.to_user.mention}**.")
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()
    @ui.button(label="Cancelar", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(description="❌ Transferência cancelada.")
        await interaction.response.edit_message(embed=embed, view=None)
        self.stop()
class BlackjackSoloView(ui.View):
    def __init__(self, bot, player, bet):
        super().__init__(timeout=120)
        self.bot = bot
        self.player = player
        self.bet = bet
        self.deck = Deck()
        self.deck.shuffle()
        self.player_hand = Hand()
        self.dealer_hand = Hand()
        self.message = None
    async def start_game(self):
        self.player_hand.add_card(self.deck.deal())
        self.player_hand.add_card(self.deck.deal())
        self.dealer_hand.add_card(self.deck.deal())
        self.dealer_hand.add_card(self.deck.deal())
        self.player_hand.adjust_for_ace()
        self.dealer_hand.adjust_for_ace()
    def create_embed(self, game_over=False, result_text=""):
        embed = discord.Embed(title=f"Blackjack - Aposta: {self.bet} FutCoins", color=discord.Color.green())
        embed.set_author(name=self.player.display_name, icon_url=self.player.display_avatar.url)
        player_cards = ", ".join(str(card) for card in self.player_hand.cards)
        embed.add_field(name=f"Sua Mão ({self.player_hand.value})", value=player_cards, inline=False)
        if game_over:
            dealer_cards = ", ".join(str(card) for card in self.dealer_hand.cards)
            embed.add_field(name=f"Mão do Dealer ({self.dealer_hand.value})", value=dealer_cards, inline=False)
            embed.description = result_text
        else:
            embed.add_field(name="Mão do Dealer (?)", value=f"{self.dealer_hand.cards[0]}, [CARTA OCULTA]", inline=False)
        return embed
    async def end_game(self, interaction: discord.Interaction, result_text: str, payout: int):
        for item in self.children:
            item.disabled = True
        self.bot.db.update_balance(self.player.id, payout)
        embed = self.create_embed(game_over=True, result_text=result_text)
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()
    @ui.button(label="Comprar Carta", style=discord.ButtonStyle.success, custom_id="bj_solo_hit")
    async def hit(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.player.id:
            return await interaction.response.send_message("Esta não é a sua mesa de jogo.", ephemeral=True)
        self.player_hand.add_card(self.deck.deal())
        self.player_hand.adjust_for_ace()
        if self.player_hand.value > 21:
            await self.end_game(interaction, f"Você estourou com {self.player_hand.value}! Perdeu {self.bet} FutCoins.", 0)
        else:
            embed = self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
    @ui.button(label="Parar", style=discord.ButtonStyle.danger, custom_id="bj_solo_stand")
    async def stand(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.player.id:
            return await interaction.response.send_message("Esta não é a sua mesa de jogo.", ephemeral=True)
        while self.dealer_hand.value < 17:
            self.dealer_hand.add_card(self.deck.deal())
            self.dealer_hand.adjust_for_ace()
        if self.dealer_hand.value > 21 or self.player_hand.value > self.dealer_hand.value:
            payout = self.bet * 2
            await self.end_game(interaction, f"Você ganhou! Recebeu {payout} FutCoins.", payout)
        elif self.player_hand.value < self.dealer_hand.value:
            await self.end_game(interaction, f"O Dealer ganhou! Você perdeu {self.bet} FutCoins.", 0)
        else:
            await self.end_game(interaction, "Empate! Você recebeu sua aposta de volta.", self.bet)
class BacBoBetModal(ui.Modal, title="Aposte no Bac Bo"):
    def __init__(self, bot, choice: str, parent_view):
        super().__init__()
        self.bot = bot
        self.choice = choice
        self.parent_view = parent_view
    amount = ui.TextInput(label='Valor em FutCoins', placeholder='Ex: 50', style=discord.TextStyle.short)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet_amount = int(self.amount.value)
            if bet_amount <= 0: return await interaction.response.send_message("O valor deve ser positivo.", ephemeral=True)
        except ValueError:
            return await interaction.response.send_message("Insira um número válido.", ephemeral=True)
        user_id = interaction.user.id
        view = self.parent_view
        refund_amount = 0
        if user_id in view.bets: refund_amount = view.bets[user_id]['amount']
        balance = self.bot.db.get_balance(user_id) + refund_amount
        if balance < bet_amount:
            return await interaction.response.send_message(f"Saldo insuficiente! Você tem {balance - refund_amount} FutCoins.", ephemeral=True)
        if refund_amount > 0: self.bot.db.update_balance(user_id, refund_amount)
        self.bot.db.update_balance(user_id, -bet_amount)
        view.bets[user_id] = {"choice": self.choice, "amount": bet_amount}
        await interaction.response.send_message(f"✅ Aposta de {bet_amount} em **{self.choice}** registrada!", ephemeral=True)
        await view.update_embed()
class BacBoView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=15)
        self.bot = bot
        self.bets = {}
        self.message = None
        self.emojis = {}
    def load_emojis(self, guild):
        for color, dice in DICE_EMOJI_NAMES.items():
            if isinstance(dice, dict):
                self.emojis[color] = {}
                for num, name in dice.items():
                    self.emojis[color][num] = discord.utils.get(guild.emojis, name=name) or "🎲"
            else:
                self.emojis[color] = discord.utils.get(guild.emojis, name=dice) or "🎲"
    async def on_timeout(self):
        for item in self.children: item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
                await self.reveal_result()
            except discord.NotFound: print("Mensagem do BacBo não encontrada para finalizar.")
    async def update_embed(self):
        if not self.message: return
        embed = self.message.embeds[0]
        embed.clear_fields()
        player_bets = sum(b['amount'] for b in self.bets.values() if b['choice'] == 'Jogador')
        banker_bets = sum(b['amount'] for b in self.bets.values() if b['choice'] == 'Banca')
        tie_bets = sum(b['amount'] for b in self.bets.values() if b['choice'] == 'Empate')
        embed.add_field(name="Apostas em Jogador", value=f"{player_bets} FutCoins", inline=True)
        embed.add_field(name="Apostas em Banca", value=f"{banker_bets} FutCoins", inline=True)
        embed.add_field(name="Apostas em Empate", value=f"{tie_bets} FutCoins", inline=True)
        await self.message.edit(embed=embed)
    async def reveal_result(self):
        rolling_blue = self.emojis.get("rolling_blue", "🎲")
        rolling_red = self.emojis.get("rolling_red", "🎲")
        embed = self.message.embeds[0]
        embed.title = "🎲 Bac Bo - Girando os dados..."
        embed.description = (f"**Jogador:** {rolling_blue} {rolling_blue}\n" f"**Banca:** {rolling_red} {rolling_red}\n\n" "Boa sorte!")
        await self.message.edit(embed=embed)
        await asyncio.sleep(2)
        player_d1, player_d2 = random.randint(1, 6), random.randint(1, 6)
        banker_d1, banker_d2 = random.randint(1, 6), random.randint(1, 6)
        player_total, banker_total = player_d1 + player_d2, banker_d1 + banker_d2
        dice_blue_1, dice_blue_2 = self.emojis.get("blue", {}).get(player_d1, "🎲"), self.emojis.get("blue", {}).get(player_d2, "🎲")
        dice_red_1, dice_red_2 = self.emojis.get("red", {}).get(banker_d1, "🎲"), self.emojis.get("red", {}).get(banker_d2, "🎲")
        await self.reveal_step(1, dice_blue_1, rolling_blue, rolling_red, rolling_red)
        await asyncio.sleep(2)
        await self.reveal_step(2, dice_blue_1, rolling_blue, dice_red_1, rolling_red)
        await asyncio.sleep(2)
        await self.reveal_step(3, dice_blue_1, dice_blue_2, dice_red_1, rolling_red)
        await asyncio.sleep(2)
        await self.reveal_step(4, dice_blue_1, dice_blue_2, dice_red_1, dice_red_2, player_total, banker_total)
        if player_total > banker_total: winner = 'Jogador'
        elif banker_total > player_total: winner = 'Banca'
        else: winner = 'Empate'
        result_embed = self.message.embeds[0]
        result_embed.title = "🎲 Bac Bo - Resultados!"
        result_embed.description += f"\n\nO vencedor é **{winner}**!"
        winners_text = ""
        for user_id, bet_info in self.bets.items():
            if bet_info['choice'] == winner:
                payout = bet_info['amount'] * 8 if winner == 'Empate' else bet_info['amount'] * 2
                self.bot.db.update_balance(user_id, payout)
                winners_text += f"🏅 <@{user_id}> ganhou **{payout}** FutCoins!\n"
        if not winners_text: winners_text = "Ninguém ganhou desta vez."
        result_embed.add_field(name="Vencedores", value=winners_text, inline=False)
        await self.message.edit(embed=result_embed)
    async def reveal_step(self, step, d_b1, d_b2, d_r1, d_r2, p_total=None, b_total=None):
        player_score = f"= **{p_total}**" if p_total is not None else ""
        banker_score = f"= **{b_total}**" if b_total is not None else ""
        embed = self.message.embeds[0]
        embed.description = (f"**Jogador:** {d_b1} {d_b2} {player_score}\n" f"**Banca:** {d_r1} {d_r2} {banker_score}")
        await self.message.edit(embed=embed)
    @ui.button(label="Jogador", style=discord.ButtonStyle.primary, custom_id="bacbo_player")
    async def player_button(self, i: discord.Interaction, b: ui.Button): await i.response.send_modal(BacBoBetModal(self.bot, "Jogador", self))
    @ui.button(label="Banca", style=discord.ButtonStyle.secondary, custom_id="bacbo_banker")
    async def banker_button(self, i: discord.Interaction, b: ui.Button): await i.response.send_modal(BacBoBetModal(self.bot, "Banca", self))
    @ui.button(label="Empate (8x)", style=discord.ButtonStyle.danger, custom_id="bacbo_tie")
    async def tie_button(self, i: discord.Interaction, b: ui.Button): await i.response.send_modal(BacBoBetModal(self.bot, "Empate", self))

# --- COG PRINCIPAL DE ECONOMIA E JOGOS ---
class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_tables = {} # {channel_id: LiveBlackjackTable}
        self.blackjack_table_updater.start()

    def cog_unload(self):
        self.blackjack_table_updater.cancel()

    @tasks.loop(seconds=1)
    async def blackjack_table_updater(self):
        if not self.active_tables:
            return
        for table in list(self.active_tables.values()):
            if not table.active:
                del self.active_tables[table.channel.id]
                continue
            try:
                await table.tick()
            except Exception as e:
                print(f"Erro no loop da mesa de Blackjack (canal {table.channel.id}): {e}")
                table.active = False

    @blackjack_table_updater.before_loop
    async def before_blackjack_updater(self):
        await self.bot.wait_until_ready()

    async def _send_response(self, ctx_or_i, content=None, embed=None, view=None, ephemeral=False, delete_after=None):
        if isinstance(ctx_or_i, discord.Interaction):
            if ctx_or_i.response.is_done():
                return await ctx_or_i.followup.send(content=content, embed=embed, view=view, ephemeral=ephemeral)
            else:
                await ctx_or_i.response.send_message(content=content, embed=embed, view=view, ephemeral=ephemeral, delete_after=delete_after)
                if not ephemeral: return await ctx_or_i.original_response()
        else:
            return await ctx_or_i.send(content=content, embed=embed, view=view, delete_after=delete_after)

    # --- COMANDOS DE JOGO ---
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


    # --- COMANDOS DE ECONOMIA ---
    @commands.command(name="saldo")
    async def saldo_prefix(self, ctx: commands.Context, membro: discord.Member = None):
        user = membro or ctx.author
        data = self.bot.db.get_user_data(user.id)
        embed = discord.Embed(title=f"💰 Saldo de {user.display_name}", description=f"Possui **{data.get('balance', 0)}** FutCoins.")
        await send_webhook(ctx.channel, embed, bot_user=self.bot.user)

    @app_commands.command(name="saldo", description="Verifica seu saldo ou o de outro membro.")
    async def saldo_slash(self, i: discord.Interaction, membro: discord.Member = None):
        user = membro or i.user
        data = self.bot.db.get_user_data(user.id)
        embed = discord.Embed(title=f"💰 Saldo de {user.display_name}", description=f"Possui **{data.get('balance', 0)}** FutCoins.")
        await i.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="perfil")
    async def perfil_prefix(self, ctx: commands.Context, membro: discord.Member = None):
        user = membro or ctx.author
        await self._handle_userstats(ctx, user)

    @app_commands.command(name="perfil", description="Mostra seu perfil econômico ou o de outro membro.")
    async def perfil_slash(self, i: discord.Interaction, membro: discord.Member = None):
        user = membro or i.user
        await self._handle_userstats(i, user)

    async def _handle_userstats(self, ctx_or_i, membro: discord.Member):
        user_data = self.bot.db.get_user_data(membro.id)
        stats = user_data.get("stats", {})
        embed = discord.Embed(title=f"Perfil de {membro.display_name}", color=membro.color)
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.add_field(name="💰 Saldo", value=f"`{user_data.get('balance', 0)}` FutCoins", inline=False)
        embed.add_field(name="Apostas Feitas", value=stats.get('bets_made', 0), inline=True)
        embed.add_field(name="Apostas Vencidas", value=stats.get('bets_won', 0), inline=True)
        embed.add_field(name="Total Apostado", value=f"`{stats.get('total_wagered', 0)}` FutCoins", inline=True)
        embed.add_field(name="Total Ganho", value=f"`{stats.get('total_won', 0)}` FutCoins", inline=True)
        await self._send_response(ctx_or_i, embed=embed, ephemeral=True)

    @commands.command(name="pagar")
    async def pagar_prefix(self, ctx: commands.Context, membro: discord.Member = None, quantia: int = None):
        if membro is None or quantia is None: return await ctx.send(f"Uso correto: `{ctx.prefix}pagar <@membro> <quantia>`")
        await self._handle_payment(ctx, membro, quantia)

    @app_commands.command(name="pagar", description="Transfere FutCoins para outro membro.")
    async def pagar_slash(self, i: discord.Interaction, membro: discord.Member, quantia: int):
        await self._handle_payment(i, membro, quantia)

    async def _handle_payment(self, ctx_or_i, membro: discord.Member, quantia: int):
        sender = ctx_or_i.author if isinstance(ctx_or_i, commands.Context) else ctx_or_i.user
        if sender.id == membro.id: return await self._send_response(ctx_or_i, "Você não pode pagar a si mesmo.", ephemeral=True)
        if quantia <= 0: return await self._send_response(ctx_or_i, "A quantia deve ser positiva.", ephemeral=True)
        sender_balance = self.bot.db.get_balance(sender.id)
        if sender_balance < quantia: return await self._send_response(ctx_or_i, f"Saldo insuficiente! Você tem {sender_balance} FutCoins.", ephemeral=True)
        embed = discord.Embed(title="Confirmar Transferência", description=f"Você tem certeza que deseja transferir **{quantia}** FutCoins para **{membro.mention}**?")
        view = ConfirmPaymentView(sender, membro, quantia, self.bot)
        await self._send_response(ctx_or_i, embed=embed, view=view, ephemeral=True)

    @commands.command(name="diario")
    async def diario_prefix(self, ctx: commands.Context): await self._handle_collect(ctx, "diario", 25, timedelta(hours=24))
    @app_commands.command(name="diario", description="Colete suas 25 FutCoins diárias.")
    async def diario_slash(self, i: discord.Interaction): await self._handle_collect(i, "diario", 25, timedelta(hours=24))

    @commands.command(name="semanal")
    async def semanal_prefix(self, ctx: commands.Context): await self._handle_collect(ctx, "semanal", 100, timedelta(days=7))
    @app_commands.command(name="semanal", description="Colete suas 100 FutCoins semanais.")
    async def semanal_slash(self, i: discord.Interaction): await self._handle_collect(i, "semanal", 100, timedelta(days=7))

    @commands.command(name="mensal")
    async def mensal_prefix(self, ctx: commands.Context): await self._handle_collect(ctx, "mensal", 350, timedelta(days=30))
    @app_commands.command(name="mensal", description="Colete suas 350 FutCoins mensais.")
    async def mensal_slash(self, i: discord.Interaction): await self._handle_collect(i, "mensal", 350, timedelta(days=30))

    async def _handle_collect(self, ctx_or_i, type, amount, delta):
        user = ctx_or_i.author if isinstance(ctx_or_i, commands.Context) else ctx_or_i.user
        user_data = self.bot.db.get_user_data(user.id)
        last_collect = user_data.get("cooldowns", {}).get(type)
        if last_collect and (datetime.utcnow() - last_collect) < delta:
            remaining = (last_collect + delta) - datetime.utcnow()
            return await self._send_response(ctx_or_i, f"Você já coletou seu prêmio {type}. Tente novamente em {str(remaining).split('.')[0]}.", ephemeral=True)
        self.bot.db.update_balance(user.id, amount)
        self.bot.db.update_cooldown(user.id, type)
        await self._send_response(ctx_or_i, f"🎉 Você coletou **{amount}** FutCoins!", ephemeral=True)

    @commands.command(name="top")
    async def top_prefix(self, ctx: commands.Context): await self._handle_top(ctx)
    @app_commands.command(name="top", description="Mostra o ranking dos mais ricos do servidor.")
    async def top_slash(self, i: discord.Interaction): await self._handle_top(i)

    async def _handle_top(self, ctx_or_i):
        guild = ctx_or_i.guild
        top_users_data = self.bot.db.get_top_users(guild.members, 10)
        embed = discord.Embed(title=f"🏆 Top 10 Ricos - {guild.name}")
        desc = ""
        for i, user_data in enumerate(top_users_data):
            member = guild.get_member(user_data["user_id"])
            if member: desc += f"**{i+1}º** {member.mention} - `{user_data['balance']}` FutCoins\n"
        embed.description = desc or "Ninguém no ranking ainda."
        await self._send_response(ctx_or_i, embed=embed)

    @commands.command(name="caraoucoroa")
    async def coinflip_prefix(self, ctx: commands.Context, lado: str = None, quantia: int = None):
        if lado is None or quantia is None: return await ctx.send(f"Uso correto: `{ctx.prefix}caraoucoroa <cara/coroa> <quantia>`")
        await self._handle_coinflip(ctx, lado, quantia)

    @app_commands.command(name="caraoucoroa", description="Aposte cara ou coroa para dobrar suas FutCoins.")
    @app_commands.describe(lado="Sua escolha: cara ou coroa", quantia="Valor a ser apostado")
    async def coinflip_slash(self, i: discord.Interaction, lado: str, quantia: int):
        await self._handle_coinflip(i, lado, quantia)

    async def _handle_coinflip(self, ctx_or_i, lado: str, quantia: int):
        user = ctx_or_i.author if isinstance(ctx_or_i, commands.Context) else ctx_or_i.user
        lado = lado.lower()
        if lado not in ['cara', 'coroa']: return await self._send_response(ctx_or_i, "Escolha inválida. Use 'cara' ou 'coroa'.", ephemeral=True)
        if quantia <= 0: return await self._send_response(ctx_or_i, "A quantia deve ser positiva.", ephemeral=True)
        balance = self.bot.db.get_balance(user.id)
        if balance < quantia: return await self._send_response(ctx_or_i, f"Saldo insuficiente! Você tem {balance} FutCoins.", ephemeral=True)
        resultado = random.choice(['cara', 'coroa'])
        if lado == resultado:
            self.bot.db.update_balance(user.id, quantia)
            msg = f"🎉 Deu **{resultado}**! Você ganhou **{quantia}** FutCoins!"
        else:
            self.bot.db.update_balance(user.id, -quantia)
            msg = f"😢 Deu **{resultado}**! Você perdeu **{quantia}** FutCoins."
        await self._send_response(ctx_or_i, msg)

    blackjack_group = app_commands.Group(name="blackjack", description="Jogue Blackjack solo ou em uma mesa.")

    @blackjack_group.command(name="solo", description="Jogue uma partida de 21 contra o Dealer valendo FutCoins.")
    @app_commands.describe(quantia="O valor que você quer apostar.")
    async def blackjack_solo(self, interaction: discord.Interaction, quantia: int):
        user = interaction.user
        if quantia <= 0: return await interaction.response.send_message("A aposta deve ser positiva.", ephemeral=True)
        balance = self.bot.db.get_balance(user.id)
        if balance < quantia: return await interaction.response.send_message(f"Saldo insuficiente! Você tem {balance} FutCoins.", ephemeral=True)
        self.bot.db.update_balance(user.id, -quantia)
        view = BlackjackSoloView(self.bot, user, quantia)
        await view.start_game()
        if view.player_hand.value == 21:
            payout = int(quantia * 2.5)
            self.bot.db.update_balance(user.id, payout)
            result_text = f"BLACKJACK! Você ganhou {payout} FutCoins!"
            for item in view.children: item.disabled = True
            embed = view.create_embed(game_over=True, result_text=result_text)
        else:
            embed = view.create_embed()
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @blackjack_group.command(name="mesa", description="Inicia uma mesa de Blackjack 'viva' neste canal.")
    async def blackjack_mesa(self, interaction: discord.Interaction):
        channel_id = interaction.channel.id
        if channel_id in self.active_tables:
            return await interaction.response.send_message("Já existe uma mesa de Blackjack ativa neste canal.", ephemeral=True)
        await interaction.response.send_message("Criando a mesa de Blackjack...", ephemeral=True, delete_after=3)
        table = LiveBlackjackTable(self.bot, interaction.channel)
        view = LiveBlackjackView(table)
        table.view = view
        initial_embed = discord.Embed(title="Mesa de Blackjack - Aguardando Jogadores...", description="Use os botões abaixo para interagir!")
        message = await interaction.channel.send(embed=initial_embed, view=view)
        table.message = message
        self.active_tables[channel_id] = table
        await table.add_player(interaction.user)

    @commands.command(name="bacbo")
    async def bacbo_prefix(self, ctx: commands.Context): await self._handle_bacbo(ctx)
    @app_commands.command(name="bacbo", description="Inicia uma rodada de Bac Bo para apostas.")
    async def bacbo_slash(self, interaction: discord.Interaction): await self._handle_bacbo(interaction)

    async def _handle_bacbo(self, ctx_or_i):
        view = BacBoView(self.bot)
        view.load_emojis(ctx_or_i.guild)
        embed = discord.Embed(title="🎲 Bac Bo - Façam suas apostas!", description=f"Apostas abertas por {view.timeout} segundos! Escolha entre Jogador, Banca ou Empate (paga 8x).")
        message = await self._send_response(ctx_or_i, embed=embed, view=view)
        view.message = message

async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
