# utils/database.py
import pymongo
import os
from datetime import datetime

STARTING_BALANCE = 500

class Database:
    def __init__(self):
        try:
            self.client = pymongo.MongoClient(os.getenv("MONGO_URI"))
            self.db = self.client.get_database("RonaldinBotDB")
            print("Conectado ao MongoDB com sucesso!")
        except Exception as e:
            print(f"Ocorreu um erro ao conectar ao MongoDB: {e}")
            self.db = None

    # --- Métodos de Economia ---
    def _get_or_create_user(self, user_id: int):
        if self.db is None: return None
        
        user_account = self.db.economy.find_one({"user_id": user_id})
        if user_account is None:
            new_account = {
                "user_id": user_id,
                "balance": STARTING_BALANCE,
                "stats": {
                    "bets_made": 0, "bets_won": 0, "total_wagered": 0, "total_won": 0
                },
                "cooldowns": {
                    "daily": None, "weekly": None, "monthly": None
                }
            }
            self.db.economy.insert_one(new_account)
            return new_account
        return user_account

    def get_user_data(self, user_id: int) -> dict:
        return self._get_or_create_user(user_id) or {}

    def get_balance(self, user_id: int) -> int:
        account = self._get_or_create_user(user_id)
        return account.get("balance", 0) if account else 0

    def update_balance(self, user_id: int, amount: int):
        if self.db is None: return
        self._get_or_create_user(user_id)
        self.db.economy.update_one({"user_id": user_id}, {"$inc": {"balance": amount}})

    # <<<< NOVO MÉTODO AQUI >>>>
    def set_balance(self, user_id: int, amount: int):
        """Define o saldo de um usuário para um valor exato."""
        if self.db is None: return
        self._get_or_create_user(user_id)
        self.db.economy.update_one({"user_id": user_id}, {"$set": {"balance": amount}})

    def update_user_stats(self, user_id: int, bets_made_inc: int = 0, bets_won_inc: int = 0, wagered_inc: int = 0, won_inc: int = 0):
        if self.db is None: return
        self._get_or_create_user(user_id)
        update_doc = {"$inc": {
            "stats.bets_made": bets_made_inc, "stats.bets_won": bets_won_inc,
            "stats.total_wagered": wagered_inc, "stats.total_won": won_inc
        }}
        self.db.economy.update_one({"user_id": user_id}, update_doc)

    def update_cooldown(self, user_id: int, cooldown_type: str):
        if self.db is None: return
        self._get_or_create_user(user_id)
        self.db.economy.update_one(
            {"user_id": user_id},
            {"$set": {f"cooldowns.{cooldown_type}": datetime.utcnow()}}
        )

    def get_top_users(self, guild_members: list, limit: int = 10):
        if self.db is None: return []
        member_ids = [m.id for m in guild_members]
        top_users = self.db.economy.find(
            {"user_id": {"$in": member_ids}}
        ).sort("balance", pymongo.DESCENDING).limit(limit)
        return list(top_users)

    # --- Métodos para Bolões ---
    def create_bet(self, bet_data: dict):
        if self.db is None: return None
        return self.db.bets.insert_one(bet_data)

    def get_bet(self, message_id: int):
        if self.db is None: return None
        return self.db.bets.find_one({"message_id": message_id})

    def add_participant_bet(self, message_id: int, user_id: int, team_choice: str, amount: int):
        if self.db is None: return None
        self.db.bets.update_one(
            {"message_id": message_id},
            {"$pull": {"participants": {"user_id": user_id}}}
        )
        self.db.bets.update_one(
            {"message_id": message_id},
            {"$push": {"participants": {"user_id": user_id, "bet_on": team_choice, "amount": amount}}}
        )

    def close_bet(self, message_id: int):
        if self.db is None: return None
        return self.db.bets.update_one({"message_id": message_id}, {"$set": {"status": "closed"}})
