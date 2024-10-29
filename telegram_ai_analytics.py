import os
import itertools
import threading
from urllib.parse import urljoin
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from telethon import TelegramClient, events
import asyncio
from datetime import date, datetime
import pandas as pd
import requests
import json
import sqlite3

from db_helpers import DbHelpers
from telegram_helpers import TelegramHelpers
from llm_templates import LLMTemplates
from bcolors import BColors

# Environment variables
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

# Initialize Telegram clients and SQLite connection
# bot = TelegramClient(BOT_NAME, API_ID, API_HASH).start(bot_token=BOT_TOKEN)
client = TelegramClient(USER_NAME, API_ID, API_HASH).start()
db = sqlite3.connect(DB_NAME)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Caches
chat_ids = []
user_cache = {}

# Helper functions
def _get_keys_by_value(d, value):
    return [key for key, val in d.items() if val == value]

async def _get_username(user_id: int):
    if user_id not in user_cache:
        username = await TelegramHelpers.fetch_name(client, user_id)
        user_cache[user_id] = username
    return user_cache[user_id]

def _deserialize_json(data: str):
    return json.loads(data)

def _json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

def _serialize2json(data):
    return json.dumps(data, ensure_ascii=False, default=_json_serial)

async def _analyze_with_llm(data):
    headers = {
        'Authorization': f'Bearer {OPEN_WEBUI_TOKEN}',
        'Content-Type': 'application/json'
    }
    generate_endpoint = urljoin(OPEN_WEBUI_HOST + '/', 'api/generate')
    data_filtered = [{k: d[k] for k in ['message_id', 'content']} for d in data]
    chunk_size = 2
    max_attempts = 3
    for chunk in itertools.islice(data_filtered, 0, len(data_filtered), chunk_size):
        prompt = LLMTemplates.prompt_analyze_news(_serialize2json(chunk))
        for attempt in range(max_attempts):
            try:
                response = requests.post(generate_endpoint, headers=headers, json={
                    'model': MODEL_NAME,
                    'prompt': prompt,
                    'stream': False,
                    'options': { 'temperature': 0 }
                }, timeout=900)
                response.raise_for_status()

                response_data = _deserialize_json(response.content)
                print(BColors.OKGREEN + response_data["response"] + BColors.ENDC)
                yield _deserialize_json(response_data["response"])
                break
            except requests.exceptions.HTTPError as e:
                print(f"{BColors.FAIL}Error during LLM call. Attempt: {attempt}/{max_attempts}. Retrying...{BColors.ENDC}")
                print(f"{BColors.FAIL}Error: {e}{BColors.ENDC}")
                await asyncio.sleep(2)
            except json.decoder.JSONDecodeError as e:
                print(f"{BColors.FAIL}Wrong response received from LLM. Attempt: {attempt}/{max_attempts}. Retrying...{BColors.ENDC}")
                print(f"{BColors.FAIL}Error: {e}{BColors.ENDC}")
                await asyncio.sleep(2)
        else:
            print(f"{BColors.FAIL}Failed after {max_attempts} attempts. Skipping item.{BColors.ENDC}")
            break

def _write_to_html(data):
    df = pd.DataFrame(data)
    df.to_html('output.html', index=False)

async def _process_messages(chat_id):
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
    if message.chat_id in chat_ids:
        DbHelpers.save_messages(db, message.chat_id, [message])
        await _process_messages(message.chat_id)

async def main():
    # Populate cache
    for chat_id in await DbHelpers.read_all_users(db):
        _ = await _get_username(chat_id)

    for chat_name in CHAT_NAMES:
        chat = await TelegramHelpers.get_user_chat(client, chat_name)
        if chat:
            chat_ids.append(chat.id)

    for chat_id in chat_ids:
        messages = await TelegramHelpers.get_all_channel_msgs(client, chat_id, FETCH_LAST_HOURS)
        DbHelpers.save_messages(db, chat_id, messages)
        await _process_messages(chat_id)

# Flask routes
@app.route('/table-news/')
def home():
    return render_template('table-news.html')

@app.route('/')
def news():
    return render_template('news.html')

@app.route('/api/news', methods=['GET'])
async def get_news():
    sort_by = request.args.get('sort_by', 'date')
    filter_country = request.args.get('country')
    filter_hashtag = request.args.get('hashtag')
    filter_priority = request.args.get('priority')
    filter_category = request.args.get('category')
    filter_source = request.args.get('source')
    filter_fromDate = request.args.get('fromDate')

    query = "SELECT * FROM messages WHERE 1=1"
    params = []
    
    if filter_country:
        query += " AND country = ?"
        params.append(filter_country)
    if filter_hashtag:
        query += " AND hashtags LIKE ?"
        params.append(f"%{filter_hashtag}%")
    if filter_priority:
        query += " AND priority = ?"
        params.append(filter_priority)
    if filter_category:
        query += " AND category = ?"
        params.append(filter_category)
    if filter_source:
        source_id = _get_keys_by_value(user_cache, filter_source)[0]
        query += " AND chat_id = ?"
        params.append(source_id)
    if filter_fromDate:
        from_date = datetime.fromisoformat(filter_fromDate)
        query += " AND date >= ?"
        params.append(from_date)
    
    query += f" ORDER BY {sort_by} DESC"
    
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(query, params)
    
    articles = [dict(row) for row in cur.fetchall()]
    conn.close()

    for article in articles:
        article["source"] = await _get_username(article["user_id"])
    
    return jsonify(articles)

@app.route('/api/filter-options')
def get_filter_options():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT country FROM messages")
    countries = [row['country'] for row in cur.fetchall()]

    priorities = {'1':'Low','2':'Medium-Low', '3':'Medium', '4':'Medium-High', '5':'High'}

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
