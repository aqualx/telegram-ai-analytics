import asyncio
from sqlite3 import Connection, IntegrityError
from typing import Any, List
from bcolors import BColors

class DbHelpers:
    table_name = 'messages'

    @staticmethod
    def read_messages(db: Connection, chat_id: int):
        c = db.cursor()
        return [{'message_id': item[0], 
                 'content': item[1]} for item in c.execute(f"SELECT message_id, content FROM {DbHelpers.table_name} WHERE analyzed=0 AND chat_id=?;", (chat_id,)).fetchall()]

    @staticmethod
    def save_messages(db: Connection, chat_id: int, messages: List[Any]):
        c = db.cursor()
        c.execute(f"CREATE TABLE IF NOT EXISTS {DbHelpers.table_name} " + \
                "(chat_id INTEGER, message_id INTEGER, user_id INTEGER, date NUMERIC, " + \
                "content TEXT, priority NUMERIC, category TEXT, description TEXT, " + \
                "country TEXT, hashtags TEXT, analyzed INTEGER DEFAULT 0)")
        to_insert = []
        for message in messages:
            if message.text is None or message.text == '':
                continue

            check_sql = f"SELECT * FROM {DbHelpers.table_name} WHERE message_id=? AND chat_id=?;"
            c.execute(check_sql, (message.id, chat_id))
            data = c.fetchone() 
            if data is None:
                insert_row = (chat_id, message.id, message.sender_id, message.date, message.text)
                to_insert.append(insert_row)
        if to_insert:
            try:
                insert_sql = f"INSERT INTO {DbHelpers.table_name} (chat_id, message_id, user_id, date, content) VALUES (?, ?, ?, ?, ?);"
                c.executemany(insert_sql, to_insert)
            except IntegrityError:
                print(f'{BColors.FAIL}An error occurred{BColors.ENDC}')            

        db.commit()

    @staticmethod
    async def update_messages(db: Connection, chat_id: int, messages: List[Any]):
        await asyncio.sleep(0)
        c = db.cursor()

        try:
            for message in messages:
                message_id  = message['message_id']
                priority    = message.get('priority', None)
                country     = message.get('country', None)
                category    = message.get('category', None)
                hashtags    = message.get('hashtags', None)
                description = message.get('summary', None)
                
                data = c.execute(f"SELECT * FROM {DbHelpers.table_name} WHERE message_id=? AND chat_id=?", (message_id, chat_id)).fetchone()
                if data is not None:
                    sql_update = f"UPDATE {DbHelpers.table_name} SET " + \
                                "priority=?, country=?, category=?, hashtags=?, description=?, analyzed=1 " + \
                                "WHERE chat_id=? AND message_id=?;"
                    c.execute(sql_update, (priority, country, category, hashtags, description, chat_id, message_id))
                else:
                    print('No record to update')
        except Exception as ex:
            print(f"{BColors.FAIL}Error occured during update: {ex}{BColors.ENDC}")

        db.commit()

    @staticmethod
    async def read_all_users(db: Connection):
        await asyncio.sleep(0)
        result = []
        try:
            c = db.cursor()
            result = [row[0] for row in c.execute(f"SELECT chat_id FROM {DbHelpers.table_name} WHERE 1=1;").fetchall()]
        except Exception as ex:
            print(f"{BColors.FAIL}Error reading users from DB: {ex}{BColors.ENDC}")
        return result
