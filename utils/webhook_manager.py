# utils/webhook_manager.py
import discord

async def _get_webhook(channel: discord.TextChannel, bot_user) -> discord.Webhook:
    """Busca ou cria um webhook para o bot no canal."""
    webhooks = await channel.webhooks()
    webhook = discord.utils.get(webhooks, user=bot_user)
    if webhook is None:
        webhook = await channel.create_webhook(name="Ronaldin Webhooks")
    return webhook

async def send_webhook(channel: discord.TextChannel, embed: discord.Embed, view: discord.ui.View = None, bot_user=None, avatar_url: str = None, content: str = None):
    """Envia uma mensagem estilizada via Webhook, com mais opções."""
    if bot_user is None: return None

    # A cor padrão é amarela, mas pode ser sobrescrita no embed antes de chamar a função.
    if not embed.color:
        embed.color = discord.Color.gold()
    
    embed.set_footer(text="Ronaldin Bot • Gerenciamento Esportivo", icon_url=bot_user.display_avatar.url)

    webhook = await _get_webhook(channel, bot_user)
    final_avatar_url = avatar_url if avatar_url else bot_user.display_avatar.url

    kwargs = {
        "embed": embed, "username": bot_user.display_name, "avatar_url": final_avatar_url, "wait": True
    }
    if view: kwargs["view"] = view
    if content: kwargs["content"] = content
        
    message = await webhook.send(**kwargs)
    return message

async def edit_webhook(channel: discord.TextChannel, message_id: int, embed: discord.Embed, view: discord.ui.View = None, bot_user=None):
    """Edita uma mensagem enviada anteriormente por um webhook."""
    if bot_user is None: return None
    
    if not embed.color:
        embed.color = discord.Color.gold()
    embed.set_footer(text="Ronaldin Bot • Gerenciamento Esportivo", icon_url=bot_user.display_avatar.url)
    
    webhook = await _get_webhook(channel, bot_user)
    
    kwargs = {"embed": embed}
    if view is not None: 
        kwargs["view"] = view

    try:
        await webhook.edit_message(message_id, **kwargs)
    except discord.NotFound:
        print(f"Webhook não conseguiu encontrar a mensagem com ID {message_id} para editar.")
    except Exception as e:
        print(f"Erro ao editar webhook: {e}")
