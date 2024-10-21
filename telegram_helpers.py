import asyncio
from telethon import TelegramClient, errors
from telethon.tl.types import Channel
from datetime import datetime, timedelta

class TelegramHelpers:
    @staticmethod
    async def get_user_chat(client: TelegramClient, name: str):
        dialogs = await client.get_dialogs() 
        for dialog in dialogs:
            if dialog.name == name:
                return dialog
        return None

    @staticmethod
    async def get_all_channel_msgs(client: TelegramClient, chat_id: int, last_hours: int):
        result = []
        try: 
            async for message in client.iter_messages(chat_id):
                if message.date.timestamp() > (datetime.now() - timedelta(hours=last_hours)).timestamp():
                    result.append(message)
                else:
                    break
        except errors.FloodWaitError as e: 
            print('Caught FloodWaitError, sleep:', e.seconds)
            await asyncio.sleep(e.seconds)
        except Exception as e:
            print(e)

        return result
    
    @staticmethod
    async def fetch_name(client, user_id):
        """Fetches the name of a user from Telegram."""
        try:
            entity = await client.get_entity(user_id)
            if isinstance(entity, Channel):
                return entity.title
            else:
                return entity.first_name + " " + entity.last_name if entity.first_name and entity.last_name else entity.first_name or entity.username
        except Exception as e:
            print(f"Error fetching name for ID {user_id}: {e}")
            return None