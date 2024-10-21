import os
import itertools
import threading
from urllib.parse import urljoin
from db_helpers import DbHelpers
from telegram_helpers import TelegramHelpers
from telethon import TelegramClient, events
import asyncio
from datetime import date, datetime
import pandas as pd
import requests
from llm_templates import LLMTemplates 
import json
import sqlite3
from bcolors import BColors

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_NAME = os.getenv("BOT_NAME") 
USER_NAME = os.getenv("USER_NAME") 
OPEN_WEBUI_TOKEN = os.getenv("OPEN_WEBUI_TOKEN")
OPEN_WEBUI_HOST = os.getenv("OPEN_WEBUI_HOST")
DB_NAME = os.getenv("DB_NAME")
MODEL_NAME = os.getenv("MODEL_NAME")
CHAT_NAMES = json.loads(os.getenv("CHAT_NAMES"))
FETCH_LAST_HOURS = int(os.getenv("FETCH_LAST_HOURS"))

bot = TelegramClient(BOT_NAME, API_ID, API_HASH).start(bot_token=BOT_TOKEN)
client = TelegramClient(USER_NAME, API_ID, API_HASH).start()
db = sqlite3.connect(DB_NAME)

app = Flask(__name__)
CORS(app)

chat_ids = []
user_cache = {}

def get_keys_by_value(d, value):
    return [key for key, val in d.items() if val == value]

async def _get_username(user_id: int):
    if user_id not in user_cache.keys():
        username = await TelegramHelpers.fetch_name(client, user_id)
        user_cache[user_id] = username
    return user_cache[user_id]

def _deserialize_json(data: str):
    return json.loads(data)

def _json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""

    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError ("Type %s not serializable" % type(obj))

def _serialize2json(data: str):
    """Serializes Python object to JSON string. This method is used to handle custom serialization for objects not supported by default json library."""
    return json.dumps(data, ensure_ascii=False, default=_json_serial)

async def _analyze_with_llm(data: str):
    """This function is used to analyze messages using large language models (LLMs)."""

    headers = {
        'Authorization': f'Bearer {OPEN_WEBUI_TOKEN}',
        'Content-Type': 'application/json'
    }

    generate_endpoint = urljoin(OPEN_WEBUI_HOST +'/', 'api/generate')
    data_filtered = [{k:d[k] for k in ['message_id', 'content']} for d in data]
    chunk_size = 1
    for chunk in [list(itertools.islice(data_filtered, i, i + chunk_size)) for i in range(0, len(data_filtered), chunk_size)]:
        prompt = LLMTemplates.prompt_analyze_news(_serialize2json(chunk))
        attempts = 0
        max_attempts = 3

        while attempts < max_attempts:
            try:
                r = requests.post(
                    generate_endpoint,
                    headers=headers,
                    json={
                        'model': MODEL_NAME,
                        'prompt': prompt,
                        'stream': False,
                        'options': {
                            'temperature': 0.1
                        }
                    },
                    stream=False,
                    timeout=600)
                r.raise_for_status()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 504: 
                    attempts += 1
                    print(f"{BColors.FAIL}Server Timeout (attempt {attempts}/{max_attempts}). Retrying...{BColors.ENDC}")
                    await asyncio.sleep(2)
                    continue
                else:
                    raise e
            
            try:
                response = _deserialize_json(r.content)
            except json.decoder.JSONDecodeError:
                attempts += 1
                print(f"{BColors.FAIL}Invalid json received @response.content: {r.content}\n(attempt {attempts}/{max_attempts}). Retrying...{BColors.ENDC}")
                continue

            try:
                print(BColors.OKGREEN + response["response"] + BColors.ENDC)
                yield _deserialize_json(response["response"])
                break
            except json.decoder.JSONDecodeError:
                attempts += 1
                print(f"{BColors.FAIL}Invalid json received @response['response']: {response['response']}\n(attempt {attempts}/{max_attempts}). Retrying...{BColors.ENDC}")
                continue
        if attempts == max_attempts:
            print(f"{BColors.FAIL}Failed to connect after {max_attempts} attempts. Switching to next item.{BColors.ENDC}") 
            break

def _write_to_html(data: str):
    df = pd.DataFrame(data)
    html = df.to_html()
    with open('output.html', 'w') as f: 
        f.write(html)

async def _process_messages(chat_id: int):
    messages = DbHelpers.read_messages(db, chat_id)
    analyzed_data = _analyze_with_llm(messages) 
    try:
        while True:
            await DbHelpers.update_messages(db, chat_id, await analyzed_data.__anext__()) 
    except StopAsyncIteration:
        pass

@client.on(events.NewMessage())
async def handler(event):
    message = event.message
    if  message.chat_id in chat_ids:
        DbHelpers.save_messages(db, message.chat_id, [message])
        await _process_messages(message.chat_id)

async def main():
    # create cache
    for chat_id in await DbHelpers.read_all_users(db):
        _ = await _get_username(chat_id)

    for chat_name in CHAT_NAMES:
        chat = await TelegramHelpers.get_user_chat(client, chat_name)
        if chat is not None:
            chat_ids.append(chat.id)
    for chat_id in chat_ids:
        messages = await TelegramHelpers.get_all_channel_msgs(client, chat_id, FETCH_LAST_HOURS)
        DbHelpers.save_messages(db, chat_id, messages)
        await _process_messages(chat_id)
    # _write_to_html(messages)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/news', methods=['GET'])
async def get_news():
    sort_by = request.args.get('sort_by', 'date')
    filter_country = request.args.get('country', None)
    filter_hashtag = request.args.get('hashtag', None)
    filter_priority = request.args.get('priority', None)
    filter_category = request.args.get('category', None)
    filter_source = request.args.get('source', None)
    
    query = "SELECT * FROM messages WHERE 1=1"
    
    if filter_country:
        query += " AND country = ?"
    if filter_hashtag:
        query += " AND hashtags LIKE ?"
    if filter_priority:
        query += " AND priority = ?"
    if filter_category:
        query += " AND category = ?"
    if filter_source:
        query += " AND chat_id = ?"
    
    query += f" ORDER BY {sort_by} DESC"
    
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    params = []
    if filter_country:
        params.append(filter_country)
    if filter_hashtag:
        params.append(f"%{filter_hashtag}%")
    if filter_priority:
        params.append(filter_priority)
    if filter_category:
        params.append(filter_category)
    if filter_source:
        params.append(get_keys_by_value(user_cache, filter_source)[0])

    cur.execute(query, params)
    articles = cur.fetchall()
    conn.close()
    
    articles_list = [dict(row) for row in articles]
    for article in articles_list:
        article["source"] = await _get_username(article["user_id"])

    return jsonify(articles_list)    

@app.route('/api/filter-options')
def get_filter_options():
    conn = sqlite3.connect(DB_NAME, uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT country FROM messages")
    countries = [row['country'] for row in cur.fetchall()]

    cur.execute("SELECT DISTINCT priority FROM messages")
    priorities = [row['priority'] for row in cur.fetchall()]

    cur.execute("SELECT DISTINCT category FROM messages")
    categories = [row['category'] for row in cur.fetchall()]
    
    sources = list(user_cache.values())

    conn.close()

    return jsonify({
        'countries': countries,
        'priorities': priorities,
        'categories': categories,
        'sources': sources
    })

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host="localhost", port=5000, debug=True, use_reloader=False)).start()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    client.run_until_disconnected()
    db.close()