#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
X PANEL OTP PANEL - COMPLETE SYSTEM
Single File Application
Owner Login: mohaymen / mohaymen
"""

import os, json, time, hashlib, secrets, threading, requests, re
from datetime import datetime
from functools import wraps
from flask import Flask, render_template_string, request, jsonify, session, redirect, send_file
from flask_socketio import SocketIO, join_room

# CONFIGURATION
app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

XPANEL_API_TOKEN = 'RFVWRjRSQkFDdIiIc4t5emKLY2dkjJFbhGSOUmiYlmBVdlJ7fU9X'
XPANEL_API_URL = 'http://51.77.216.195/crapi/konek/viewstats'
OTP_API_URL = 'http://147.135.212.197/crapi/st/viewstats'
OTP_API_TOKEN = 'SFBTSEdBUzR5UoeHWGBPa16KkoBzj2lgfHhhh2tQeUhBeIBWe21sgw=='
OTP_MONITOR_API_TOKEN = 'Q05RRUhBUzRkiYFCXHZ0YnVzjFRJjW1cX5aKYHx2Y4lzg25JV5CGXw=='
OTP_MONITOR_API_URL = 'http://51.77.216.195/crapi/mait/viewstats'
RESELLER_API_TOKEN = 'QlRRRUZUfkJHU1BJ'
RESELLER_API_URL = 'http://137.74.1.203/crapi/reseller/mdr.php'
POLL_INTERVAL = 15

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'xpanel_data')
os.makedirs(DATA_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, 'users.json')
DAILY_LIMITS_FILE = os.path.join(DATA_DIR, 'daily_limits.json')
NUMBERS_FILE = os.path.join(DATA_DIR, 'numbers.json')
TEST_NUMBERS_FILE = os.path.join(DATA_DIR, 'test_numbers.json')
SMS_FILE = os.path.join(DATA_DIR, 'sms.json')
NOTIFICATIONS_FILE = os.path.join(DATA_DIR, 'notifications.json')
PENDING_USERS_FILE = os.path.join(DATA_DIR, 'pending_users.json')
PAYMENTS_FILE = os.path.join(DATA_DIR, 'payments.json')

# DATA MANAGEMENT
def load_data(filepath, default=None):
    if default is None: default = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as file:
                return json.load(file)
        except: return default
    return default

def save_data(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

def init_data():
    if not os.path.exists(USERS_FILE):
        save_data(USERS_FILE, {
            'mohaymen': {
                'password': hashlib.sha256('mohaymen'.encode()).hexdigest(),
                'phone': '',
                'role': 'owner',
                'status': 'active',
                'created_at': datetime.now().isoformat(),
                'limit': 999999,
                'stats': {'numbers_added': 0, 'sms_received': 0, 'files_downloaded': 0}
            }
        })
    for filepath in [NUMBERS_FILE, TEST_NUMBERS_FILE, SMS_FILE, NOTIFICATIONS_FILE, PENDING_USERS_FILE, PAYMENTS_FILE]:
        if not os.path.exists(filepath): save_data(filepath, {})

init_data()

def hash_password(password): return hashlib.sha256(password.encode()).hexdigest()

def get_daily_limit_key(username):
    today = datetime.now().strftime('%Y-%m-%d')
    return f"{username}_{today}"

def get_daily_usage(username):
    daily_limits = load_data(DAILY_LIMITS_FILE)
    key = get_daily_limit_key(username)
    return daily_limits.get(key, 0)

def add_daily_usage(username, count):
    daily_limits = load_data(DAILY_LIMITS_FILE)
    key = get_daily_limit_key(username)
    daily_limits[key] = daily_limits.get(key, 0) + count
    save_data(DAILY_LIMITS_FILE, daily_limits)

def get_remaining_daily_limit(username):
    users = load_data(USERS_FILE)
    user = users.get(username, {})
    daily_limit = user.get('daily_limit', 2000)
    used = get_daily_usage(username)
    return max(0, daily_limit - used)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session: return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

def owner_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session: return redirect('/')
        users = load_data(USERS_FILE)
        if users.get(session['username'], {}).get('role') != 'owner':
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        return f(*args, **kwargs)
    return decorated_function

# SMS API FETCHING
def fetch_sms_from_apis():
    all_sms = []

    # Fetch from each API using its specific handler
    all_sms.extend(fetch_xpanel_api())
    all_sms.extend(fetch_otp_api())
    all_sms.extend(fetch_otp_monitor_api())
    all_sms.extend(fetch_reseller_api())

    print(f"[SMS Monitor] Total fetched: {len(all_sms)} SMS")
    return all_sms


# ====== API 1: X PANEL ======
# Format: Array of Objects with keys: num, message, dt
def fetch_xpanel_api():
    sms_list = []
    try:
        full_url = f"{XPANEL_API_URL}?token={XPANEL_API_TOKEN}"
        response = requests.get(full_url, timeout=10)
        print(f"[API] X PANEL: Status={response.status_code}")

        if response.status_code == 200:
            data = response.json()
            items = []

            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                for key in ['data', 'messages', 'sms', 'items', 'results', 'records']:
                    if key in data and isinstance(data[key], list):
                        items = data[key]
                        break
                if not items and ('num' in data or 'number' in data):
                    items = [data]

            print(f"[API] X PANEL: Found {len(items)} items")

            for item in items:
                if isinstance(item, dict):
                    number = str(item.get('num', item.get('number', ''))).strip()
                    message = str(item.get('message', item.get('text', item.get('body', '')))).strip()
                    time_str = item.get('dt', datetime.now().isoformat())

                    if number and message:
                        sms_list.append({
                            'number': number,
                            'message': message,
                            'api': 'X PANEL',
                            'time': time_str
                        })
                        print(f"[SMS] X PANEL: {number[:12]}... -> {message[:40]}...")
    except Exception as e:
        print(f'[API] X PANEL Error: {e}')

    return sms_list


# ====== API 2: OTP ======
# Format: Array of Arrays [app_name, number, message, datetime]
def fetch_otp_api():
    sms_list = []
    try:
        full_url = f"{OTP_API_URL}?token={OTP_API_TOKEN}"
        response = requests.get(full_url, timeout=10)
        print(f"[API] OTP: Status={response.status_code}")

        if response.status_code == 200:
            data = response.json()
            items = []

            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                for key in ['data', 'messages', 'sms', 'items', 'results', 'records']:
                    if key in data and isinstance(data[key], list):
                        items = data[key]
                        break

            print(f"[API] OTP: Found {len(items)} items")

            for item in items:
                # OTP API returns Array format: [app_name, number, message, datetime]
                if isinstance(item, list) and len(item) >= 4:
                    app_name = str(item[0]).strip() if len(item) > 0 else 'OTP'
                    number = str(item[1]).strip() if len(item) > 1 else ''
                    message = str(item[2]).strip() if len(item) > 2 else ''
                    time_str = str(item[3]).strip() if len(item) > 3 else datetime.now().isoformat()

                    if number and message:
                        sms_list.append({
                            'number': number,
                            'message': message,
                            'api': app_name,
                            'time': time_str
                        })
                        print(f"[SMS] OTP: {number[:12]}... -> {message[:40]}...")

                # Fallback: Object format
                elif isinstance(item, dict):
                    number = str(item.get('num', item.get('number', ''))).strip()
                    message = str(item.get('message', item.get('text', item.get('body', '')))).strip()
                    time_str = item.get('dt', datetime.now().isoformat())

                    if number and message:
                        sms_list.append({
                            'number': number,
                            'message': message,
                            'api': 'OTP',
                            'time': time_str
                        })
                        print(f"[SMS] OTP: {number[:12]}... -> {message[:40]}...")
    except Exception as e:
        print(f'[API] OTP Error: {e}')

    return sms_list


# ====== API 3: OTP MONITOR ======
# Format: Array of Objects with keys: num, message, dt
def fetch_otp_monitor_api():
    sms_list = []
    try:
        full_url = f"{OTP_MONITOR_API_URL}?token={OTP_MONITOR_API_TOKEN}"
        response = requests.get(full_url, timeout=10)
        print(f"[API] OTP_MONITOR: Status={response.status_code}")

        if response.status_code == 200:
            data = response.json()
            items = []

            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                for key in ['data', 'messages', 'sms', 'items', 'results', 'records']:
                    if key in data and isinstance(data[key], list):
                        items = data[key]
                        break
                if not items and ('num' in data or 'number' in data):
                    items = [data]

            print(f"[API] OTP_MONITOR: Found {len(items)} items")

            for item in items:
                if isinstance(item, dict):
                    number = str(item.get('num', item.get('number', ''))).strip()
                    message = str(item.get('message', item.get('text', item.get('body', '')))).strip()
                    time_str = item.get('dt', datetime.now().isoformat())

                    if number and message:
                        sms_list.append({
                            'number': number,
                            'message': message,
                            'api': 'OTP_MONITOR',
                            'time': time_str
                        })
                        print(f"[SMS] OTP_MONITOR: {number[:12]}... -> {message[:40]}...")
    except Exception as e:
        print(f'[API] OTP_MONITOR Error: {e}')

    return sms_list


# ====== API 4: RESELLER ======
# Format: Array of Objects with keys: num, message, dt
def fetch_reseller_api():
    sms_list = []
    try:
        full_url = f"{RESELLER_API_URL}?token={RESELLER_API_TOKEN}"
        response = requests.get(full_url, timeout=10)
        print(f"[API] RESELLER: Status={response.status_code}")

        if response.status_code == 200:
            data = response.json()
            items = []

            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                for key in ['data', 'messages', 'sms', 'items', 'results', 'records']:
                    if key in data and isinstance(data[key], list):
                        items = data[key]
                        break
                if not items and ('num' in data or 'number' in data):
                    items = [data]

            print(f"[API] RESELLER: Found {len(items)} items")

            for item in items:
                if isinstance(item, dict):
                    number = str(item.get('num', item.get('number', ''))).strip()
                    message = str(item.get('message', item.get('text', item.get('body', '')))).strip()
                    time_str = item.get('dt', datetime.now().isoformat())

                    if number and message:
                        sms_list.append({
                            'number': number,
                            'message': message,
                            'api': 'RESELLER',
                            'time': time_str
                        })
                        print(f"[SMS] RESELLER: {number[:12]}... -> {message[:40]}...")
    except Exception as e:
        print(f'[API] RESELLER Error: {e}')

    return sms_list


def mask_number(phone):
    if len(phone) >= 10: return phone[:6] + 'XXXXX' + phone[-3:]
    return phone

def process_new_sms():
    new_sms = fetch_sms_from_apis()
    numbers_data = load_data(NUMBERS_FILE)
    sms_data = load_data(SMS_FILE)
    notifications = load_data(NOTIFICATIONS_FILE)
    test_numbers = load_data(TEST_NUMBERS_FILE)
    payments = load_data(PAYMENTS_FILE)
    all_users = load_data(USERS_FILE)

    for sms in new_sms:
        phone = sms.get('number', '').strip()
        message = sms.get('message', '').strip()
        api_name = sms.get('api', '')
        time_str = sms.get('time', datetime.now().isoformat())

        if not phone or not message: 
            continue

        # ============================================
        # FEATURE 1: Match user's purchased numbers
        # ============================================
        for username, user_files in numbers_data.items():
            if username.startswith('_'): 
                continue
            if not isinstance(user_files, dict):
                continue
            for filename, numbers_list in user_files.items():
                if not isinstance(numbers_list, list):
                    continue
                if phone in numbers_list:
                    if username not in sms_data: 
                        sms_data[username] = {}
                    if phone not in sms_data[username]: 
                        sms_data[username][phone] = []

                    # Check if this exact SMS already exists (compare by message + time)
                    # Use a unique fingerprint: first 50 chars of message + time
                    msg_fingerprint = message[:50] + time_str[:16]
                    exists = any(
                        (s.get('message', '')[:50] + s.get('time', '')[:16]) == msg_fingerprint
                        for s in sms_data[username][phone]
                    )

                    if not exists:
                        sms_entry = {
                            'number': phone,
                            'message': message,
                            'api': api_name,
                            'time': time_str
                        }
                        sms_data[username][phone].append(sms_entry)
                        print(f"[NEW SMS] User {username} -> {phone}: {message[:40]}...")

                        # Add payment per SMS received
                        if username not in payments: 
                            payments[username] = []

                        cost_per_sms = 0.01
                        available_data = numbers_data.get('_available', {})
                        if filename in available_data and isinstance(available_data[filename], dict):
                            cost_per_sms = available_data[filename].get('cost', 0.01)

                        payments[username].append({
                            'type': 'sms',
                            'number': phone,
                            'file': filename,
                            'cost': cost_per_sms,
                            'time': datetime.now().isoformat()
                        })

                        # Add notification
                        if username not in notifications: 
                            notifications[username] = []
                        notifications[username].append({
                            'type': 'sms', 
                            'message': f'New SMS for {phone}',
                            'time': datetime.now().isoformat(), 
                            'read': False
                        })

                        # Emit real-time notification
                        try:
                            socketio.emit('new_sms', {
                                'number': phone, 
                                'message': message, 
                                'api': api_name
                            }, room=username)
                        except Exception as e:
                            print(f"Socket emit error: {e}")

        # ============================================
        # FEATURE 2: Show ALL API SMS to ALL users (catch_all)
        # Any number that appears in API will be visible to all users
        # This helps users see ALL available SMS even if they didn't buy the number
        # ============================================
        for username, user_info in all_users.items():
            if user_info.get('role') in ['user', 'admin']:
                if username not in sms_data: 
                    sms_data[username] = {}

                # Use a special key for API-wide SMS
                api_key = f"api_{phone}"
                if api_key not in sms_data[username]: 
                    sms_data[username][api_key] = []

                # Check if this exact SMS already exists
                msg_fingerprint = message[:50] + time_str[:16]
                exists = any(
                    (s.get('message', '')[:50] + s.get('time', '')[:16]) == msg_fingerprint
                    for s in sms_data[username][api_key]
                )

                if not exists:
                    sms_entry = {
                        'number': phone,
                        'message': message,
                        'api': api_name,
                        'time': time_str,
                        'source': 'api_global'  # Mark as from global API
                    }
                    sms_data[username][api_key].append(sms_entry)

        # ============================================
        # FEATURE 3: Process test numbers (masked)
        # ============================================
        for filename, test_list in test_numbers.items():
            if not isinstance(test_list, list):
                continue
            if phone in test_list:
                for username, user_info in all_users.items():
                    if user_info.get('role') in ['user', 'admin']:
                        if username not in sms_data: 
                            sms_data[username] = {}
                        test_key = f'test_{filename}'
                        if test_key not in sms_data[username]: 
                            sms_data[username][test_key] = []

                        masked = mask_number(phone)
                        msg_fingerprint = message[:50] + time_str[:16]
                        exists = any(
                            (s.get('message', '')[:50] + s.get('time', '')[:16]) == msg_fingerprint
                            for s in sms_data[username][test_key]
                        )

                        if not exists:
                            sms_data[username][test_key].append({
                                'number': phone,
                                'message': message,
                                'api': api_name,
                                'time': time_str,
                                'masked_number': masked, 
                                'original_number': phone
                            })
                            print(f"[TEST SMS] User {username} -> {masked}: {message[:40]}...")

        # ============================================
        # FEATURE 4: API Global SMS for Test Numbers too
        # Any API SMS for test numbers goes to ALL users
        # ============================================
        for filename, test_list in test_numbers.items():
            if not isinstance(test_list, list):
                continue
            if phone in test_list:
                for username, user_info in all_users.items():
                    if user_info.get('role') in ['user', 'admin']:
                        if username not in sms_data: 
                            sms_data[username] = {}

                        # Use special key for API test SMS
                        api_test_key = f"api_test_{filename}"
                        if api_test_key not in sms_data[username]: 
                            sms_data[username][api_test_key] = []

                        masked = mask_number(phone)
                        msg_fingerprint = message[:50] + time_str[:16]
                        exists = any(
                            (s.get('message', '')[:50] + s.get('time', '')[:16]) == msg_fingerprint
                            for s in sms_data[username][api_test_key]
                        )

                        if not exists:
                            sms_data[username][api_test_key].append({
                                'number': phone,
                                'message': message,
                                'api': api_name,
                                'time': time_str,
                                'masked_number': masked,
                                'original_number': phone,
                                'source': 'api_test_global'
                            })

    save_data(SMS_FILE, sms_data)
    save_data(NOTIFICATIONS_FILE, notifications)
    save_data(PAYMENTS_FILE, payments)

def start_sms_monitoring():
    def monitor():
        while True:
            try: process_new_sms()
            except Exception as e: print(f'Monitor error: {e}')
            time.sleep(POLL_INTERVAL)
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()


# ROUTES - HTML PAGES

@app.route('/')
def index():
    if 'username' in session: return redirect('/dashboard')
    return render_template_string(INDEX_HTML)

@app.route('/set_language', methods=['POST'])
def set_language():
    data = request.get_json()
    session['language'] = data.get('language', 'arabic')
    return jsonify({'success': True})

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    users = load_data(USERS_FILE)
    if username in users:
        if users[username]['password'] == hash_password(password):
            if users[username].get('status') == 'banned':
                return jsonify({'success': False, 'message': 'Account banned'})
            session['username'] = username
            session['role'] = users[username]['role']
            return jsonify({'success': True, 'role': users[username]['role']})
    return jsonify({'success': False, 'message': 'Invalid credentials'})

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    phone = data.get('phone', '').strip()
    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password required'})
    users = load_data(USERS_FILE)
    pending = load_data(PENDING_USERS_FILE)
    if username in users or username in pending:
        return jsonify({'success': False, 'message': 'Username already exists'})
    pending[username] = {
        'password': hash_password(password), 'phone': phone, 'role': 'user',
        'status': 'pending', 'created_at': datetime.now().isoformat(), 'limit': 2000
    }
    save_data(PENDING_USERS_FILE, pending)
    notifications = load_data(NOTIFICATIONS_FILE)
    if 'mohaymen' not in notifications: notifications['mohaymen'] = []
    notifications['mohaymen'].append({
        'type': 'registration', 'message': f'New registration request: {username}',
        'username': username, 'time': datetime.now().isoformat(), 'read': False
    })
    save_data(NOTIFICATIONS_FILE, notifications)
    return jsonify({'success': True, 'message': 'Registration pending approval'})

@app.route('/dashboard')
@login_required
def dashboard():
    role = session.get('role', 'user')
    if role == 'owner': return render_template_string(OWNER_HTML)
    elif role == 'admin': return render_template_string(ADMIN_HTML)
    return render_template_string(USER_HTML)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# OWNER APIs

@app.route('/api/owner/pending_users')
@owner_required
def get_pending_users():
    pending = load_data(PENDING_USERS_FILE)
    return jsonify({'success': True, 'users': pending})

@app.route('/api/owner/approve_user', methods=['POST'])
@owner_required
def approve_user():
    data = request.get_json()
    username = data.get('username')
    action = data.get('action')
    pending = load_data(PENDING_USERS_FILE)
    users = load_data(USERS_FILE)
    if username not in pending: return jsonify({'success': False, 'message': 'User not found'})
    if action == 'approve':
        users[username] = pending[username]
        users[username]['status'] = 'active'
        save_data(USERS_FILE, users)
        notifications = load_data(NOTIFICATIONS_FILE)
        if username not in notifications: notifications[username] = []
        notifications[username].append({
            'type': 'system', 'message': 'Your account has been approved!',
            'time': datetime.now().isoformat(), 'read': False
        })
        save_data(NOTIFICATIONS_FILE, notifications)
    del pending[username]
    save_data(PENDING_USERS_FILE, pending)
    return jsonify({'success': True})

@app.route('/api/owner/approve_all', methods=['POST'])
@owner_required
def approve_all():
    pending = load_data(PENDING_USERS_FILE)
    users = load_data(USERS_FILE)
    notifications = load_data(NOTIFICATIONS_FILE)
    for username, data in pending.items():
        users[username] = data
        users[username]['status'] = 'active'
        if username not in notifications: notifications[username] = []
        notifications[username].append({
            'type': 'system', 'message': 'Your account has been approved!',
            'time': datetime.now().isoformat(), 'read': False
        })
    save_data(USERS_FILE, users)
    save_data(NOTIFICATIONS_FILE, notifications)
    save_data(PENDING_USERS_FILE, {})
    return jsonify({'success': True})

@app.route('/api/owner/add_numbers', methods=['POST'])
@owner_required
def add_numbers():
    if 'file' not in request.files: return jsonify({'success': False, 'message': 'No file uploaded'})
    file = request.files['file']
    filename = request.form.get('filename', '').strip()
    cost = request.form.get('cost', '0').strip()
    if not filename: return jsonify({'success': False, 'message': 'Filename required'})
    numbers = []
    try:
        content = file.read().decode('utf-8')
        for line in content.split('\n'):
            num = line.strip()
            if num and re.match(r'^[+\d\s-]+$', num): numbers.append(num)
    except: return jsonify({'success': False, 'message': 'Invalid file'})
    numbers_data = load_data(NUMBERS_FILE)
    if '_available' not in numbers_data: numbers_data['_available'] = {}
    numbers_data['_available'][filename] = {
        'numbers': numbers, 'cost': float(cost), 'added_at': datetime.now().isoformat()
    }
    save_data(NUMBERS_FILE, numbers_data)
    return jsonify({'success': True, 'count': len(numbers)})

@app.route('/api/owner/delete_numbers', methods=['POST'])
@owner_required
def delete_numbers():
    data = request.get_json()
    filename = data.get('filename')
    numbers_data = load_data(NUMBERS_FILE)
    if '_available' in numbers_data and filename in numbers_data['_available']:
        del numbers_data['_available'][filename]
    for username in list(numbers_data.keys()):
        if username != '_available' and filename in numbers_data[username]:
            del numbers_data[username][filename]
    save_data(NUMBERS_FILE, numbers_data)
    return jsonify({'success': True})

@app.route('/api/owner/delete_all_numbers', methods=['POST'])
@owner_required
def delete_all_numbers():
    numbers_data = load_data(NUMBERS_FILE)
    available = numbers_data.get('_available', {})
    numbers_data = {'_available': available}
    save_data(NUMBERS_FILE, numbers_data)
    return jsonify({'success': True})

@app.route('/api/owner/broadcast', methods=['POST'])
@owner_required
def broadcast():
    data = request.get_json()
    message = data.get('message', '')
    users = load_data(USERS_FILE)
    notifications = load_data(NOTIFICATIONS_FILE)
    for username in users:
        if users[username].get('role') in ['user', 'admin']:
            if username not in notifications: notifications[username] = []
            notifications[username].append({
                'type': 'broadcast', 'message': message, 'from': 'mohaymen',
                'time': datetime.now().isoformat(), 'read': False
            })
    save_data(NOTIFICATIONS_FILE, notifications)
    socketio.emit('broadcast', {'message': message}, broadcast=True)
    return jsonify({'success': True})

@app.route('/api/owner/increase_limit', methods=['POST'])
@owner_required
def increase_limit():
    data = request.get_json()
    username = data.get('username')
    limit = int(data.get('limit', 0))
    users = load_data(USERS_FILE)
    if username in users:
        users[username]['limit'] = users[username].get('limit', 0) + limit
        save_data(USERS_FILE, users)
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'User not found'})

@app.route('/api/owner/add_admin', methods=['POST'])
@owner_required
def add_admin():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    users = load_data(USERS_FILE)
    if username in users: return jsonify({'success': False, 'message': 'User exists'})
    users[username] = {
        'password': hash_password(password), 'role': 'admin', 'status': 'active',
        'created_at': datetime.now().isoformat(), 'limit': 999999
    }
    save_data(USERS_FILE, users)
    return jsonify({'success': True})

@app.route('/api/owner/delete_admin', methods=['POST'])
@owner_required
def delete_admin():
    data = request.get_json()
    username = data.get('username')
    users = load_data(USERS_FILE)
    if username in users and users[username].get('role') == 'admin':
        users[username]['role'] = 'user'
        save_data(USERS_FILE, users)
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Admin not found'})

@app.route('/api/owner/add_test_numbers', methods=['POST'])
@owner_required
def add_test_numbers():
    if 'file' not in request.files: return jsonify({'success': False, 'message': 'No file uploaded'})
    file = request.files['file']
    filename = request.form.get('filename', '').strip()
    if not filename: return jsonify({'success': False, 'message': 'Filename required'})
    numbers = []
    try:
        content = file.read().decode('utf-8')
        for line in content.split('\n'):
            num = line.strip()
            if num and re.match(r'^[+\d\s-]+$', num): numbers.append(num)
    except: return jsonify({'success': False, 'message': 'Invalid file'})
    test_numbers = load_data(TEST_NUMBERS_FILE)
    test_numbers[filename] = numbers
    save_data(TEST_NUMBERS_FILE, test_numbers)
    return jsonify({'success': True, 'count': len(numbers)})

@app.route('/api/owner/delete_test_numbers', methods=['POST'])
@owner_required
def delete_test_numbers():
    data = request.get_json()
    filename = data.get('filename')
    test_numbers = load_data(TEST_NUMBERS_FILE)
    if filename in test_numbers:
        del test_numbers[filename]
        save_data(TEST_NUMBERS_FILE, test_numbers)
    return jsonify({'success': True})

@app.route('/api/owner/delete_all_test', methods=['POST'])
@owner_required
def delete_all_test():
    save_data(TEST_NUMBERS_FILE, {})
    return jsonify({'success': True})

@app.route('/api/owner/accounts')
@owner_required
def get_accounts():
    users = load_data(USERS_FILE)
    return jsonify({'success': True, 'users': users})

@app.route('/api/owner/toggle_ban', methods=['POST'])
@owner_required
def toggle_ban():
    data = request.get_json()
    username = data.get('username')
    users = load_data(USERS_FILE)
    if username in users and username != 'mohaymen':
        current = users[username].get('status', 'active')
        users[username]['status'] = 'banned' if current == 'active' else 'active'
        save_data(USERS_FILE, users)
        return jsonify({'success': True, 'status': users[username]['status']})
    return jsonify({'success': False})


# USER APIs

@app.route('/api/user/available_numbers')
@login_required
def get_available_numbers():
    numbers_data = load_data(NUMBERS_FILE)
    available = numbers_data.get('_available', {})
    return jsonify({'success': True, 'files': available})

@app.route('/api/user/request_numbers', methods=['POST'])
@login_required
def request_numbers():
    data = request.get_json()
    filename = data.get('filename')
    count = int(data.get('count', 0))
    username = session['username']

    if count <= 0:
        return jsonify({'success': False, 'message': 'Invalid count'})

    # Check daily limit
    remaining_daily = get_remaining_daily_limit(username)
    if count > remaining_daily:
        return jsonify({
            'success': False, 
            'message': f'Daily limit exceeded. Remaining: {remaining_daily} numbers today'
        })

    users = load_data(USERS_FILE)
    numbers_data = load_data(NUMBERS_FILE)
    payments = load_data(PAYMENTS_FILE)
    user_limit = users[username].get('limit', 0)
    user_numbers = numbers_data.get(username, {})
    current_count = sum(len(v) for v in user_numbers.values())
    if current_count + count > user_limit:
        return jsonify({'success': False, 'message': 'Total limit exceeded'})
    available = numbers_data.get('_available', {})
    if filename not in available: return jsonify({'success': False, 'message': 'File not found'})
    file_data = available[filename]
    available_numbers = file_data['numbers']
    cost_per_number = file_data['cost']
    if count > len(available_numbers): return jsonify({'success': False, 'message': 'Not enough numbers'})
    total_cost = count * cost_per_number
    assigned = available_numbers[:count]
    remaining = available_numbers[count:]
    if username not in numbers_data: numbers_data[username] = {}
    if filename not in numbers_data[username]: numbers_data[username][filename] = []
    numbers_data[username][filename].extend(assigned)
    if remaining: numbers_data['_available'][filename]['numbers'] = remaining
    else: del numbers_data['_available'][filename]

    # Add daily usage
    add_daily_usage(username, count)

    if username not in payments: payments[username] = []
    payments[username].append({
        'type': 'purchase',
        'file': filename, 'count': count, 'cost': total_cost,
        'time': datetime.now().isoformat()
    })
    save_data(NUMBERS_FILE, numbers_data)
    save_data(PAYMENTS_FILE, payments)

    new_remaining = get_remaining_daily_limit(username)
    return jsonify({
        'success': True, 
        'assigned': assigned, 
        'cost': total_cost,
        'daily_remaining': new_remaining,
        'daily_limit': 2000
    })

@app.route('/api/user/my_numbers')
@login_required
def get_my_numbers():
    username = session['username']
    numbers_data = load_data(NUMBERS_FILE)
    user_numbers = numbers_data.get(username, {})
    payments = load_data(PAYMENTS_FILE)
    user_payments = payments.get(username, [])
    file_costs = {}
    for p in user_payments:
        if p.get('type') == 'purchase' and p.get('file'):
            count = max(p.get('count', 1), 1)
            file_costs[p['file']] = p.get('cost', 0) / count
    return jsonify({'success': True, 'numbers': user_numbers, 'costs': file_costs})

@app.route('/api/user/delete_my_numbers', methods=['POST'])
@login_required
def delete_my_numbers():
    data = request.get_json()
    filename = data.get('filename')
    username = session['username']
    numbers_data = load_data(NUMBERS_FILE)
    if username in numbers_data and filename in numbers_data[username]:
        del numbers_data[username][filename]
        save_data(NUMBERS_FILE, numbers_data)
    return jsonify({'success': True})

@app.route('/api/user/daily_limit')
@login_required
def get_daily_limit():
    username = session['username']
    remaining = get_remaining_daily_limit(username)
    used = get_daily_usage(username)
    return jsonify({
        'success': True,
        'daily_limit': 2000,
        'daily_used': used,
        'daily_remaining': remaining,
        'resets_at': '23:59:59'
    })

@app.route('/api/user/my_range')
@login_required
def get_my_range():
    username = session['username']
    numbers_data = load_data(NUMBERS_FILE)
    user_numbers = numbers_data.get(username, {})
    result = {}
    for filename, numbers in user_numbers.items():
        result[filename] = len(numbers)
    return jsonify({'success': True, 'range': result})

@app.route('/api/user/my_sms')
@login_required
def get_my_sms():
    username = session['username']
    sms_data = load_data(SMS_FILE)
    user_sms = sms_data.get(username, {})

    # Debug: print what we're returning
    print(f"[API] User {username} requested SMS. Found {len(user_sms)} phone entries.")

    return jsonify({'success': True, 'sms': user_sms})

@app.route('/api/user/test_numbers')
@login_required
def get_test_numbers():
    test_numbers = load_data(TEST_NUMBERS_FILE)
    return jsonify({'success': True, 'files': test_numbers})

@app.route('/api/user/test_sms')
@login_required
def get_test_sms():
    username = session['username']
    sms_data = load_data(SMS_FILE)
    test_sms = {}
    for key, value in sms_data.get(username, {}).items():
        if key.startswith('test_'): test_sms[key] = value
    return jsonify({'success': True, 'sms': test_sms})

@app.route('/api/user/notifications')
@login_required
def get_notifications():
    username = session['username']
    notifications = load_data(NOTIFICATIONS_FILE)
    user_notifications = notifications.get(username, [])
    return jsonify({'success': True, 'notifications': user_notifications})

@app.route('/api/user/mark_read', methods=['POST'])
@login_required
def mark_read():
    username = session['username']
    notifications = load_data(NOTIFICATIONS_FILE)
    if username in notifications:
        for notif in notifications[username]: notif['read'] = True
        save_data(NOTIFICATIONS_FILE, notifications)
    return jsonify({'success': True})

@app.route('/api/user/my_account')
@login_required
def get_my_account():
    username = session['username']
    users = load_data(USERS_FILE)
    return jsonify({'success': True, 'user': users.get(username, {})})

@app.route('/api/user/update_account', methods=['POST'])
@login_required
def update_account():
    data = request.get_json()
    username = session['username']
    users = load_data(USERS_FILE)
    if username in users:
        if 'password' in data and data['password']:
            users[username]['password'] = hash_password(data['password'])
        if 'phone' in data: users[username]['phone'] = data['phone']
        save_data(USERS_FILE, users)
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/user/payments')
@login_required
def get_payments():
    username = session['username']
    payments = load_data(PAYMENTS_FILE)
    return jsonify({'success': True, 'payments': payments.get(username, [])})

@app.route('/api/user/download_file', methods=['POST'])
@login_required
def download_file():
    data = request.get_json()
    filename = data.get('filename')
    username = session['username']
    numbers_data = load_data(NUMBERS_FILE)
    user_numbers = numbers_data.get(username, {})
    if filename not in user_numbers: return jsonify({'success': False, 'message': 'File not found'})
    numbers = user_numbers[filename]
    file_path = os.path.join(DATA_DIR, f'{username}_{filename}.txt')
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write('\n'.join(numbers))
    return send_file(file_path, as_attachment=True, download_name=f'{filename}.txt')


# DIRECT API TEST - Check if APIs are reachable and returning correct format
@app.route('/api/test_api_connection')
@owner_required
def test_api_connection():
    """Test all API connections and show raw responses"""
    results = {}
    apis = [
        ('X PANEL', XPANEL_API_URL, XPANEL_API_TOKEN),
        ('OTP', OTP_API_URL, OTP_API_TOKEN),
        ('OTP_MONITOR', OTP_MONITOR_API_URL, OTP_MONITOR_API_TOKEN),
        ('RESELLER', RESELLER_API_URL, RESELLER_API_TOKEN),
    ]

    for name, url, token in apis:
        try:
            # Use token in URL like the real API expects
            full_url = f"{url}?token={token}"
            response = requests.get(full_url, timeout=10)

            if response.status_code == 200:
                try:
                    data = response.json()
                except:
                    results[name] = {'status': 'invalid_json', 'text': response.text[:200]}
                    continue

                # Count SMS items
                count = 0
                if isinstance(data, list):
                    count = len(data)
                    sample = data[0] if data else {}
                elif isinstance(data, dict):
                    if 'data' in data and isinstance(data['data'], list):
                        count = len(data['data'])
                        sample = data['data'][0] if data['data'] else {}
                    else:
                        sample = data
                else:
                    sample = {}

                results[name] = {
                    'status': 'connected',
                    'count': count,
                    'sample_keys': list(sample.keys()) if isinstance(sample, dict) else [],
                    'sample': sample if isinstance(sample, dict) else str(sample)[:200]
                }
            else:
                results[name] = {'status': 'error', 'code': response.status_code, 'text': response.text[:100]}
        except Exception as e:
            results[name] = {'status': 'failed', 'error': str(e)}

    return jsonify({'success': True, 'apis': results})

# DEBUG ENDPOINT - For troubleshooting SMS issues
@app.route('/api/debug/sms_data')
@login_required
def debug_sms_data():
    """Debug endpoint to see raw SMS data"""
    username = session['username']
    sms_data = load_data(SMS_FILE)
    numbers_data = load_data(NUMBERS_FILE)

    return jsonify({
        'success': True,
        'username': username,
        'user_sms': sms_data.get(username, {}),
        'all_sms_keys': list(sms_data.keys()),
        'user_numbers': numbers_data.get(username, {}),
        'available_numbers': list(numbers_data.get('_available', {}).keys())
    })

@app.route('/api/debug/check_number/<path:number>')
@login_required
def debug_check_number(number):
    """Check if a specific number exists in user's data"""
    username = session['username']
    numbers_data = load_data(NUMBERS_FILE)
    sms_data = load_data(SMS_FILE)

    user_numbers = numbers_data.get(username, {})
    found_in = []
    for filename, nums in user_numbers.items():
        if number in nums:
            found_in.append(filename)

    user_sms = sms_data.get(username, {})
    sms_for_number = user_sms.get(number, [])

    return jsonify({
        'success': True,
        'number': number,
        'found_in_files': found_in,
        'sms_count': len(sms_for_number),
        'sms_messages': sms_for_number
    })

# WEBSOCKET

@socketio.on('connect')
def handle_connect():
    if 'username' in session:
        join_room(session['username'])

@socketio.on('join')
def handle_join(data):
    username = data.get('username')
    if username: join_room(username)


# HTML TEMPLATES (EMBEDDED STRINGS)

INDEX_HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>X PANEL - OTP System</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
:root{--primary:#1E40AF;--primary-light:#3B82F6;--primary-dark:#1E3A8A;--background:#FFFFFF;--foreground:#1F2937;--secondary:#F3F4F6;--border:#E5E7EB;--muted:#6B7280;--destructive:#DC2626;--success:#10B981;--warning:#F59E0B}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background-color:#F9FAFB;color:var(--foreground);line-height:1.6;min-height:100vh}
h1,h2,h3,h4,h5,h6{font-family:'Poppins',sans-serif;font-weight:600}

/* ===== LOGIN PAGE ===== */
.login-page{background:linear-gradient(135deg,var(--primary-dark) 0%,var(--primary) 50%,var(--primary-light) 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.login-card{background:var(--background);border-radius:16px;padding:48px;width:100%;max-width:420px;box-shadow:0 25px 50px rgba(0,0,0,0.25)}
.login-logo{text-align:center;margin-bottom:32px}
.login-logo h1{font-family:'Poppins',sans-serif;font-size:2.5rem;font-weight:700;color:var(--primary);margin-bottom:8px}
.login-logo p{color:var(--muted);font-size:0.95rem}
.lang-selector{display:flex;gap:8px;margin-bottom:24px;justify-content:center}
.lang-chip{padding:8px 16px;border-radius:20px;border:1px solid var(--border);background:var(--secondary);color:var(--muted);font-size:0.85rem;cursor:pointer;transition:all 0.2s ease;font-family:'Inter',sans-serif}
.lang-chip:hover{border-color:var(--primary);color:var(--primary)}
.lang-chip.active{background:var(--primary);color:#fff;border-color:var(--primary)}
.input-group{margin-bottom:20px}
.input-group label{display:block;margin-bottom:8px;font-size:0.875rem;font-weight:500;color:var(--foreground)}
.input-group input{width:100%;padding:12px 16px;border:1px solid var(--border);border-radius:8px;font-size:0.95rem;font-family:'Inter',sans-serif;transition:all 0.2s ease;color:var(--foreground);background:var(--background)}
.input-group input:focus{outline:none;border-color:var(--primary);box-shadow:0 0 0 3px rgba(30,64,175,0.1)}
.input-group input::placeholder{color:var(--muted)}
.btn{width:100%;padding:12px;border:none;border-radius:8px;font-size:0.95rem;font-weight:600;font-family:'Inter',sans-serif;cursor:pointer;transition:all 0.2s ease;display:inline-flex;align-items:center;justify-content:center;gap:8px}
.btn-primary{background:var(--primary);color:#fff}
.btn-primary:hover{background:var(--primary-light);transform:translateY(-1px);box-shadow:0 4px 12px rgba(30,64,175,0.3)}
.btn-outline{background:var(--background);color:var(--primary);border:1px solid var(--primary)}
.btn-outline:hover{background:var(--primary);color:#fff}
.btn-secondary{background:var(--secondary);color:var(--foreground);border:1px solid var(--border)}
.btn-secondary:hover{background:var(--border)}
.divider{display:flex;align-items:center;gap:16px;margin:24px 0;color:var(--muted);font-size:0.85rem}
.divider::before,.divider::after{content:'';flex:1;height:1px;background:var(--border)}
.alert{padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:0.9rem;display:none;align-items:center;gap:8px}
.alert-success{background:rgba(16,185,129,0.1);border:1px solid var(--success);color:#047857}
.alert-error{background:rgba(220,38,38,0.1);border:1px solid var(--destructive);color:#B91C1C}
.register-section{display:none;margin-top:20px;padding-top:20px;border-top:1px solid var(--border)}
.register-section.show{display:block}
.toggle-register{text-align:center;margin-top:16px;font-size:0.9rem;color:var(--muted)}
.toggle-register a{color:var(--primary);text-decoration:none;font-weight:600;cursor:pointer}
.toggle-register a:hover{text-decoration:underline}
.loader{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(255,255,255,0.9);z-index:9999;justify-content:center;align-items:center;flex-direction:column}
.loader-spinner{width:48px;height:48px;border:3px solid var(--border);border-top-color:var(--primary);border-radius:50%;animation:spin 1s linear infinite}
.loader-text{margin-top:16px;color:var(--primary);font-weight:600;font-size:1rem}
@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:480px){.login-card{padding:32px 24px}.login-logo h1{font-size:2rem}}
</style>
</head>
<body>
<div class="loader" id="loader"><div class="loader-spinner"></div><div class="loader-text" id="loaderText">wait please </div></div>

<div class="login-page">
    <div class="login-card">
        <div class="login-logo">
            <img src="https://i.ibb.co/CKXS2Lcg/1000146872.png" alt="X PANEL Logo" style="width:180px;height:auto;margin-bottom:16px;border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,0.3);">
            <h1>X PANEL</h1>
            <p id="loginSubtitle">Log in to the X PANEL</p>
        </div>

        <div class="lang-selector">
            <button class="lang-chip active" onclick="selectLanguage('arabic')">العربية</button>
            <button class="lang-chip" onclick="selectLanguage('english')">English</button>
            <button class="lang-chip" onclick="selectLanguage('hindi')">हिंदी</button>
            <button class="lang-chip" onclick="selectLanguage('urdu')">اردو</button>
        </div>

        <div class="alert" id="alert"></div>

        <form id="loginForm">
            <div class="input-group">
                <label id="loginUserLabel">User</label>
                <input type="text" id="loginUsername" placeholder="Enter User" required>
            </div>
            <div class="input-group">
                <label id="loginPassLabel">Password</label>
                <input type="password" id="loginPassword" placeholder="Enter Password" required>
            </div>
            <button type="submit" class="btn btn-primary" id="loginBtn">
                <i class="fas fa-sign-in-alt"></i> <span id="loginBtnText">Login</span>
            </button>
        </form>

        <div class="toggle-register">
            <span id="noAccountText">You do not have an account؟</span> 
            <a onclick="toggleRegister()" id="registerLink">Create account  جديد</a>
        </div>

        <div class="register-section" id="registerSection">
            <div class="divider"><span id="orText">أو</span></div>
            <form id="regForm">
                <div class="input-group">
                    <label id="regUserLabel">User</label>
                    <input type="text" id="regUsername" placeholder="اختر اسم مستخدم" required>
                </div>
                <div class="input-group">
                    <label id="regPassLabel">Password</label>
                    <input type="password" id="regPassword" placeholder="اختر كلمة مرور" required>
                </div>
                <div class="input-group">
                    <label id="regPhoneLabel">phone number </label>
                    <input type="tel" id="regPhone" placeholder="+20xxxxxxxxxx" required>
                </div>
                <button type="submit" class="btn btn-outline" id="regBtn">
                    <i class="fas fa-paper-plane"></i> <span id="regBtnText">إرسال طلب التسجيل</span>
                </button>
            </form>
        </div>
    </div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.5.1/socket.io.js"></script>
<script>
let currentLang='arabic';
const socket=io();

const translations={
    arabic:{
        loginSubtitle:'Log in to the X PANEL',
        loginUserLabel:'User',loginPassLabel:'Password',
        loginBtnText:'Login',registerBtnText:'إرسال طلب التسجيل',
        regUserLabel:'User',regPassLabel:'Password',regPhoneLabel:'phone number ',
        noAccountText:'You do not have an account؟',registerLink:'Create account  جديد',
        orText:'أو',loaderText:'wait please ',
        loginPlaceholderUser:'Enter User',loginPlaceholderPass:'Enter Password',
        regPlaceholderUser:'اختر اسم مستخدم',regPlaceholderPass:'اختر كلمة مرور',regPlaceholderPhone:'+20xxxxxxxxxx',
        loginError:'خطأ في Login',
        registerSuccess:'تم إرسال طلبك للمالك، في انتظار الموافقة',
        registerError:'خطأ في التسجيل',dir:'rtl'
    },
    english:{
        loginSubtitle:'Login to Dashboard',loginUserLabel:'Username',loginPassLabel:'Password',
        loginBtnText:'Login',registerBtnText:'Send Registration Request',
        regUserLabel:'Username',regPassLabel:'Password',regPhoneLabel:'Phone Number',
        noAccountText:"Don't have an account?",registerLink:'Create New Account',
        orText:'OR',loaderText:'Loading...',
        loginPlaceholderUser:'Enter username',loginPlaceholderPass:'Enter password',
        regPlaceholderUser:'Choose a username',regPlaceholderPass:'Choose a password',regPlaceholderPhone:'+1xxxxxxxxxx',
        loginError:'Invalid credentials',registerSuccess:'Your request has been sent, pending approval',
        registerError:'Registration error',dir:'ltr'
    },
    hindi:{
        loginSubtitle:'डैशबोर्ड में लॉग इन करें',loginUserLabel:'उपयोगकर्ता नाम',loginPassLabel:'पासवर्ड',
        loginBtnText:'लॉग इन',registerBtnText:'पंजीकरण अनुरोध भेजें',
        regUserLabel:'उपयोगकर्ता नाम',regPassLabel:'पासवर्ड',regPhoneLabel:'फोन नंबर',
        noAccountText:'खाता नहीं है?',registerLink:'नया खाता बनाएं',
        orText:'या',loaderText:'लोड हो रहा है...',
        loginPlaceholderUser:'उपयोगकर्ता नाम दर्ज करें',loginPlaceholderPass:'पासवर्ड दर्ज करें',
        regPlaceholderUser:'उपयोगकर्ता नाम चुनें',regPlaceholderPass:'पासवर्ड चुनें',regPlaceholderPhone:'+91xxxxxxxxxx',
        loginError:'अमान्य क्रेडेंशियल्स',registerSuccess:'आपका अनुरोध भेज दिया गया है',
        registerError:'पंजीकरण त्रुटि',dir:'ltr'
    },
    urdu:{
        loginSubtitle:'ڈیش بورڈ میں لاگ ان کریں',loginUserLabel:'صارف نام',loginPassLabel:'پاس ورڈ',
        loginBtnText:'لاگ ان',registerBtnText:'رجسٹریشن کی درخواست بھیجیں',
        regUserLabel:'صارف نام',regPassLabel:'پاس ورڈ',regPhoneLabel:'فون نمبر',
        noAccountText:'اکاؤنٹ نہیں ہے?',registerLink:'نیا اکاؤنٹ بنائیں',
        orText:'یا',loaderText:'لوڈ ہو رہا ہے...',
        loginPlaceholderUser:'صارف نام درج کریں',loginPlaceholderPass:'پاس ورڈ درج کریں',
        regPlaceholderUser:'صارف نام منتخب کریں',regPlaceholderPass:'پاس ورڈ منتخب کریں',regPlaceholderPhone:'+92xxxxxxxxxx',
        loginError:'غلط اسناد',registerSuccess:'آپ کی درخواست بھیج دی گئی ہے',
        registerError:'رجسٹریشن میں خرابی',dir:'rtl'
    }
};

function applyLanguage(lang){
    const t=translations[lang];
    document.getElementById('loginSubtitle').textContent=t.loginSubtitle;
    document.getElementById('loginUserLabel').textContent=t.loginUserLabel;
    document.getElementById('loginPassLabel').textContent=t.loginPassLabel;
    document.getElementById('loginBtnText').textContent=t.loginBtnText;
    document.getElementById('regBtnText').textContent=t.registerBtnText;
    document.getElementById('regUserLabel').textContent=t.regUserLabel;
    document.getElementById('regPassLabel').textContent=t.regPassLabel;
    document.getElementById('regPhoneLabel').textContent=t.regPhoneLabel;
    document.getElementById('noAccountText').textContent=t.noAccountText;
    document.getElementById('registerLink').textContent=t.registerLink;
    document.getElementById('orText').textContent=t.orText;
    document.getElementById('loaderText').textContent=t.loaderText;
    document.getElementById('loginUsername').placeholder=t.loginPlaceholderUser;
    document.getElementById('loginPassword').placeholder=t.loginPlaceholderPass;
    document.getElementById('regUsername').placeholder=t.regPlaceholderUser;
    document.getElementById('regPassword').placeholder=t.regPlaceholderPass;
    document.getElementById('regPhone').placeholder=t.regPlaceholderPhone;
    document.body.dir=t.dir;
}

function selectLanguage(lang){
    currentLang=lang;
    document.querySelectorAll('.lang-chip').forEach(c=>c.classList.remove('active'));
    event.target.classList.add('active');
    fetch('/set_language',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({language:lang})});
    applyLanguage(lang);
}

function toggleRegister(){
    const section=document.getElementById('registerSection');
    section.classList.toggle('show');
}

function showAlert(message,type){
    const alert=document.getElementById('alert');
    alert.className=`alert alert-${type}`;
    alert.innerHTML=type==='success'?`<i class="fas fa-check-circle"></i> ${message}`:`<i class="fas fa-exclamation-circle"></i> ${message}`;
    alert.style.display='flex';
    setTimeout(()=>alert.style.display='none',5000);
}

function showLoader(){document.getElementById('loader').style.display='flex';}
function hideLoader(){document.getElementById('loader').style.display='none';}

document.getElementById('loginForm').addEventListener('submit',async(e)=>{
    e.preventDefault();showLoader();
    const response=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:document.getElementById('loginUsername').value,password:document.getElementById('loginPassword').value})});
    const data=await response.json();hideLoader();
    if(data.success){window.location.href='/dashboard';}
    else{showAlert(data.message||translations[currentLang].loginError,'error');}
});

document.getElementById('regForm').addEventListener('submit',async(e)=>{
    e.preventDefault();showLoader();
    const response=await fetch('/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:document.getElementById('regUsername').value,password:document.getElementById('regPassword').value,phone:document.getElementById('regPhone').value})});
    const data=await response.json();hideLoader();
    if(data.success){showAlert(translations[currentLang].registerSuccess,'success');document.getElementById('registerSection').classList.remove('show');}
    else{showAlert(data.message||translations[currentLang].registerError,'error');}
});

if('Notification' in window&&Notification.permission==='default'){Notification.requestPermission();}
socket.on('broadcast',(data)=>{if(Notification.permission==='granted'){new Notification('X PANEL',{body:data.message});}});
</script>
</body>
</html>
"""
OWNER_HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>X PANEL - Owner</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
:root{--primary:#1E40AF;--primary-light:#3B82F6;--primary-dark:#1E3A8A;--background:#FFFFFF;--foreground:#1F2937;--secondary:#F3F4F6;--border:#E5E7EB;--muted:#6B7280;--destructive:#DC2626;--success:#10B981;--warning:#F59E0B;--card-bg:#FFFFFF;--sidebar-width:260px}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background-color:#F9FAFB;color:var(--foreground);line-height:1.6;min-height:100vh}
h1,h2,h3,h4,h5,h6{font-family:'Poppins',sans-serif;font-weight:600}

/* ===== SIDEBAR ===== */
.sidebar{position:fixed;right:0;top:0;width:var(--sidebar-width);height:100vh;background:white;border-left:1px solid var(--border);padding:20px 0;overflow-y:auto;z-index:100;box-shadow:-2px 0 10px rgba(0,0,0,0.05)}
.sidebar-logo{text-align:center;margin-bottom:24px;padding:0 20px 20px;border-bottom:1px solid var(--border)}
.sidebar-logo h1{font-family:'Poppins',sans-serif;font-size:1.4rem;font-weight:700;color:var(--primary);margin-bottom:4px}
.sidebar-logo p{color:var(--muted);font-size:0.75rem;font-weight:500}
.nav-section{margin-top:8px;padding:0 12px}
.nav-section-title{font-size:0.7rem;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-bottom:8px;padding:0 8px;font-weight:600}
.nav-item{display:flex;align-items:center;padding:10px 14px;margin-bottom:4px;border-radius:8px;cursor:pointer;transition:all 0.2s ease;border:none;background:none;width:100%;text-align:right;font-family:'Inter',sans-serif;font-size:0.85rem;color:var(--foreground);gap:10px}
.nav-item:hover{background:var(--secondary);color:var(--primary)}
.nav-item.active{background:var(--primary);color:white}
.nav-item.active i{color:white}
.nav-item i{font-size:1rem;width:20px;text-align:center;color:var(--muted);transition:color 0.2s}
.nav-item:hover i{color:var(--primary)}
.nav-item.active:hover{background:var(--primary-dark)}
.nav-item.active:hover i{color:white}

/* ===== MAIN CONTENT ===== */
.main-content{margin-right:var(--sidebar-width);min-height:100vh;display:flex;flex-direction:column}
.page-content{flex:1;max-width:1400px;margin:0 auto;padding:24px 32px;width:100%}

/* ===== HEADER ===== */
.header{background-color:white;border-bottom:1px solid var(--border);box-shadow:0 1px 3px rgba(0,0,0,0.05);padding:14px 32px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:40}
.header-left h2{font-size:20px;margin-bottom:2px;color:var(--foreground)}
.header-left p{font-size:13px;color:var(--muted)}
.header-right{display:flex;align-items:center;gap:14px}
.header-icon-btn{position:relative;background:none;border:none;cursor:pointer;color:var(--muted);transition:all 0.2s ease;padding:8px;border-radius:8px;font-size:18px}
.header-icon-btn:hover{color:var(--primary);background-color:var(--secondary)}
.notification-badge{position:absolute;top:4px;right:4px;width:8px;height:8px;background-color:var(--destructive);border-radius:50%}
.divider{width:1px;height:24px;background-color:var(--border)}
.user-profile{display:flex;align-items:center;gap:10px;cursor:pointer}
.user-avatar{width:34px;height:34px;background-color:var(--primary);border-radius:50%;display:flex;align-items:center;justify-content:center;color:white;font-size:16px;font-weight:600}
.user-name{font-size:14px;font-weight:500}
.logout-btn{background:var(--destructive);color:#fff;border:none;padding:8px 18px;border-radius:6px;cursor:pointer;font-family:'Inter',sans-serif;font-weight:600;font-size:13px;transition:all 0.2s ease;display:inline-flex;align-items:center;gap:6px}
.logout-btn:hover{background:#B91C1C;transform:translateY(-1px)}

/* ===== SECTIONS ===== */
.page-section{margin-bottom:20px}
.section-title{font-size:18px;font-weight:600;margin-bottom:16px;color:var(--foreground);display:flex;align-items:center;gap:10px}
.section-title::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--border),transparent)}
.content-section{display:none;animation:fadeIn 0.3s ease}
.content-section.active{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}

/* ===== CARDS ===== */
.cards-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:24px}
.stat-card{background:white;border:1px solid var(--border);border-radius:8px;padding:20px;transition:all 0.2s ease;box-shadow:0 1px 3px rgba(0,0,0,0.05)}
.stat-card:hover{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,0.1)}
.stat-card .icon{font-size:24px;margin-bottom:8px;display:block}
.stat-card .number{font-family:'Poppins',sans-serif;font-size:1.6rem;font-weight:700;margin-bottom:4px;color:var(--foreground)}
.stat-card .label{color:var(--muted);font-size:12px}

/* ===== BUTTONS ===== */
.action-buttons{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap}
.btn{padding:10px 18px;border-radius:6px;border:none;cursor:pointer;font-size:13px;font-weight:500;transition:all 0.2s ease;display:inline-flex;align-items:center;gap:8px;font-family:'Inter',sans-serif}
.btn-primary{background-color:var(--primary);color:white}
.btn-primary:hover{background-color:var(--primary-light);transform:translateY(-1px);box-shadow:0 4px 12px rgba(30,64,175,0.2)}
.btn-outline{background-color:white;color:var(--foreground);border:1px solid var(--border)}
.btn-outline:hover{background-color:var(--secondary);border-color:var(--primary);color:var(--primary)}
.btn-danger{background-color:var(--destructive);color:white}
.btn-danger:hover{background-color:#B91C1C;transform:translateY(-1px)}
.btn-success{background-color:var(--success);color:white}
.btn-success:hover{background-color:#059669;transform:translateY(-1px)}
.btn-warning{background-color:var(--warning);color:white}
.btn-warning:hover{background-color:#D97706}
.btn-sm{padding:6px 12px;font-size:12px}

/* ===== FORMS ===== */
.form-container{background:white;border:1px solid var(--border);border-radius:8px;padding:24px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.05)}
.form-group{margin-bottom:16px}
.form-group label{display:block;margin-bottom:6px;font-size:13px;font-weight:500;color:var(--foreground)}
.form-group input,.form-group textarea,.form-group select{width:100%;padding:10px 14px;border:1px solid var(--border);border-radius:6px;font-size:13px;background-color:white;color:var(--foreground);font-family:'Inter',sans-serif;transition:all 0.2s ease}
.form-group input:focus,.form-group textarea:focus,.form-group select:focus{outline:none;border-color:var(--primary);box-shadow:0 0 0 3px rgba(30,64,175,0.1)}
.form-group input::placeholder,.form-group textarea::placeholder{color:var(--muted)}
.file-upload{border:2px dashed var(--border);border-radius:8px;padding:32px;text-align:center;cursor:pointer;transition:all 0.2s ease;margin-bottom:16px;background:var(--secondary)}
.file-upload:hover{border-color:var(--primary);background:rgba(30,64,175,0.03)}
.file-upload i{font-size:2rem;color:var(--primary);margin-bottom:10px}
.file-upload p{color:var(--muted);font-size:13px}

/* ===== TABLE ===== */
.table-wrapper{background-color:white;border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.05)}
.table-controls{display:flex;align-items:center;justify-content:space-between;padding:14px 20px;background-color:var(--secondary);border-bottom:1px solid var(--border);flex-wrap:wrap;gap:12px}
.table-show{display:flex;align-items:center;gap:8px;font-size:13px}
.table-show select{padding:6px 10px;border:1px solid var(--border);border-radius:4px;font-size:12px;background-color:white;cursor:pointer;font-family:'Inter',sans-serif}
.table-export{display:flex;gap:8px;flex-wrap:wrap}
table{width:100%;border-collapse:collapse}
thead{background-color:var(--secondary)}
th{padding:12px 16px;text-align:right;font-size:12px;font-weight:600;color:var(--foreground);border-bottom:1px solid var(--border);white-space:nowrap}
td{padding:12px 16px;font-size:13px;border-bottom:1px solid var(--border)}
tbody tr{transition:background-color 0.2s ease}
tbody tr:hover{background-color:var(--secondary)}
tbody tr:nth-child(even){background-color:rgba(243,244,246,0.5)}
.checkbox{width:16px;height:16px;cursor:pointer;accent-color:var(--primary)}
.text-primary{color:var(--primary);font-weight:500}
.text-muted{color:var(--muted)}
.text-mono{font-family:'Courier New',monospace;font-weight:500;font-size:12px}
.text-success{color:var(--success);font-weight:500}
.text-danger{color:var(--destructive);font-weight:500}

/* ===== STATUS BADGES ===== */
.status-badge{padding:4px 10px;border-radius:12px;font-size:11px;font-weight:600;display:inline-block}
.status-active{background:rgba(16,185,129,0.1);color:#047857;border:1px solid var(--success)}
.status-pending{background:rgba(245,158,11,0.1);color:#B45309;border:1px solid var(--warning)}
.status-banned{background:rgba(220,38,38,0.1);color:#B91C1C;border:1px solid var(--destructive)}
.status-admin{background:rgba(59,130,246,0.1);color:var(--primary);border:1px solid var(--primary-light)}

/* ===== FILE CARDS ===== */
.files-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
.file-card{background:white;border:1px solid var(--border);border-radius:8px;padding:20px;transition:all 0.2s ease;box-shadow:0 1px 3px rgba(0,0,0,0.05)}
.file-card:hover{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,0.1);border-color:var(--primary)}
.file-card h4{color:var(--primary);margin-bottom:12px;font-size:15px;display:flex;align-items:center;gap:8px}
.file-card .info{display:flex;justify-content:space-between;margin-bottom:10px;color:var(--muted);font-size:13px}
.file-card .cost{color:var(--success);font-weight:700;font-size:16px}
.qty-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:12px}
.qty-btn{padding:10px;background:rgba(30,64,175,0.05);border:1px solid var(--border);border-radius:6px;color:var(--primary);font-family:'Poppins',sans-serif;font-size:14px;font-weight:600;cursor:pointer;transition:all 0.2s ease}
.qty-btn:hover,.qty-btn.selected{background:var(--primary);color:white;border-color:var(--primary);transform:scale(1.02)}

/* ===== SMS CARDS ===== */
.sms-card{background:white;border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:12px;transition:all 0.2s ease}
.sms-card:hover{border-color:var(--primary);box-shadow:0 2px 8px rgba(30,64,175,0.08)}
.sms-card .phone{color:var(--primary);font-weight:600;font-size:14px;margin-bottom:8px;display:flex;align-items:center;gap:8px}
.sms-card .message{color:var(--foreground);margin-bottom:10px;line-height:1.6;font-size:13px}
.sms-card .meta{display:flex;justify-content:space-between;font-size:12px;color:var(--muted);align-items:center}
.sms-card .api-badge{background:rgba(30,64,175,0.1);color:var(--primary);padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600}
.sms-card.test .phone{color:var(--warning)}
.sms-card.api-global{border-color:var(--warning);background:rgba(245,158,11,0.03)}
.sms-card.api-global .phone{color:var(--warning)}
.sms-card.api-test-global{border-color:var(--success);background:rgba(16,185,129,0.03)}
.sms-card.api-test-global .phone{color:var(--success)}

/* ===== NOTIFICATION PANEL ===== */
.notification-panel{background:white;border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:12px;transition:all 0.2s ease}
.notification-panel.unread{border-color:var(--warning);background:rgba(245,158,11,0.03)}
.notification-panel .header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.notification-panel .type{background:rgba(30,64,175,0.1);color:var(--primary);padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600}
.notification-panel .time{color:var(--muted);font-size:12px}
.notification-panel p{font-size:13px;color:var(--foreground);line-height:1.5}

/* ===== TOAST ===== */
.toast-container{position:fixed;top:20px;left:20px;z-index:9999;display:flex;flex-direction:column;gap:10px}
.toast{background:white;border-right:4px solid var(--success);border-radius:8px;padding:14px 18px;min-width:300px;box-shadow:0 10px 30px rgba(0,0,0,0.15);animation:toastIn 0.3s ease;font-size:13px;display:flex;align-items:center;gap:10px}
.toast.error{border-right-color:var(--destructive)}
.toast.info{border-right-color:var(--primary)}
.toast.warning{border-right-color:var(--warning)}
@keyframes toastIn{from{transform:translateX(-100%);opacity:0}to{transform:translateX(0);opacity:1}}

/* ===== FOOTER ===== */
.footer{background-color:white;border-top:1px solid var(--border);padding:16px 32px;text-align:center;font-size:12px;color:var(--muted);margin-top:auto}

/* ===== RESPONSIVE ===== */
@media(max-width:768px){
    .sidebar{width:100%;transform:translateX(100%);transition:transform 0.3s ease}
    .sidebar.open{transform:translateX(0)}
    .main-content{margin-right:0}
    .header{flex-direction:column;align-items:flex-start;gap:10px;padding:12px 20px}
    .header-right{width:100%;justify-content:flex-start}
    .page-content{padding:16px 20px}
    .cards-grid{grid-template-columns:1fr}
    .qty-grid{grid-template-columns:repeat(2,1fr)}
    .files-grid{grid-template-columns:1fr}
    table{font-size:12px}
    th,td{padding:10px 12px}
}
@media(max-width:640px){
    .header-left h2{font-size:18px}
    .section-title{font-size:16px}
    .user-name{display:none}
}
</style>
</head>
<body>

<!-- SIDEBAR -->
<div class="sidebar">
    <div class="sidebar-logo">
        <img src="https://i.ibb.co/CKXS2Lcg/1000146872.png" alt="X PANEL" style="width:80px;height:auto;margin-bottom:8px;border-radius:8px;">
        <h1>X PANEL</h1>
        <p>OWNER PANEL</p>
    </div>

    <div class="nav-section">
        <div class="nav-section-title">main Dashboard</div>
        <button class="nav-item active" onclick="showSection('dashboard',this)">
            <i class="fas fa-home"></i> Dashboard
        </button>
    </div>

    <div class="nav-section">
        <div class="nav-section-title">Number management</div>
        <button class="nav-item" onclick="showSection('addNumbers',this)">
            <i class="fas fa-plus-circle"></i> إضافة أرقام
        </button>
        <button class="nav-item" onclick="showSection('deleteNumbers',this)">
            <i class="fas fa-trash"></i> delete أرقام
        </button>
        <button class="nav-item" onclick="showSection('deleteAllNumbers',this)">
            <i class="fas fa-trash-alt"></i> Delete all numbers
        </button>
    </div>

    <div class="nav-section">
        <div class="nav-section-title">اختبارات</div>
        <button class="nav-item" onclick="showSection('addTest',this)">
            <i class="fas fa-vial"></i> إضافة تجريبي
        </button>
        <button class="nav-item" onclick="showSection('deleteTest',this)">
            <i class="fas fa-trash"></i> delete تجريبي
        </button>
        <button class="nav-item" onclick="showSection('deleteAllTest',this)">
            <i class="fas fa-trash-alt"></i> delete كل التجريبي
        </button>
    </div>

    <div class="nav-section">
        <div class="nav-section-title">المستخدمين</div>
        <button class="nav-item" onclick="showSection('pendingUsers',this)">
            <i class="fas fa-user-clock"></i> طلبات التسجيل
        </button>
        <button class="nav-item" onclick="showSection('accounts',this)">
            <i class="fas fa-users"></i> الحسابات
        </button>
        <button class="nav-item" onclick="showSection('increaseLimit',this)">
            <i class="fas fa-arrow-up"></i> زيادة الحد
        </button>
        <button class="nav-item" onclick="showSection('addAdmin',this)">
            <i class="fas fa-user-shield"></i> إضافة أدمن
        </button>
        <button class="nav-item" onclick="showSection('deleteAdmin',this)">
            <i class="fas fa-user-times"></i> delete أدمن
        </button>
    </div>

    <div class="nav-section">
        <div class="nav-section-title">التواصل</div>
        <button class="nav-item" onclick="showSection('broadcast',this)">
            <i class="fas fa-broadcast-tower"></i> إذاعة رسالة
        </button>
        <button class="nav-item" onclick="showSection('notifications',this)">
            <i class="fas fa-bell"></i> notifications
        </button>
        <button class="nav-item" onclick="showSection('apiTest',this)">
            <i class="fas fa-plug"></i> فحص APIs
        </button>
    </div>
</div>

<!-- MAIN CONTENT -->
<div class="main-content">
    <!-- HEADER -->
    <header class="header">
        <div class="header-left">
            <h2><i class="fas fa-crown" style="color:var(--warning)"></i> لوحة التحكم - المالك</h2>
            <p>إدارة النظام والمستخدمين</p>
        </div>
        <div class="header-right">
            <button class="header-icon-btn" onclick="showSection('notifications',this)" title="notifications">
                <i class="fas fa-bell"></i>
                <span class="notification-badge" id="notifBadge" style="display:none"></span>
            </button>
            <button class="header-icon-btn" title="الإعدادات"><i class="fas fa-cog"></i></button>
            <div class="divider"></div>
            <div class="user-profile">
                <div class="user-avatar">M</div>
                <span class="user-name">mohaymen</span>
            </div>
            <button class="logout-btn" onclick="logout()"><i class="fas fa-sign-out-alt"></i> Logout</button>
        </div>
    </header>

    <!-- PAGE CONTENT -->
    <div class="page-content">
        <!-- DASHBOARD -->
        <div class="content-section active" id="dashboard">
            <div class="cards-grid">
                <div class="stat-card"><span class="icon" style="color:var(--primary)">👥</span><div class="number" id="totalUsers">0</div><div class="label">Total المستخدمين</div></div>
                <div class="stat-card"><span class="icon" style="color:var(--success)">📱</span><div class="number" id="totalNumbers">0</div><div class="label">Total Available number </div></div>
                <div class="stat-card"><span class="icon" style="color:var(--warning)">⏳</span><div class="number" id="pendingCount">0</div><div class="label">طلبات معلقة</div></div>
                <div class="stat-card"><span class="icon" style="color:var(--destructive)">🚫</span><div class="number" id="bannedCount">0</div><div class="label">حسابات محظورة</div></div>
            </div>
        </div>

        <!-- ADD NUMBERS -->
        <div class="content-section" id="addNumbers">
            <h3 class="section-title"><i class="fas fa-plus-circle"></i> إضافة أرقام جديدة</h3>
            <div class="form-container">
                <div class="file-upload" onclick="document.getElementById('numberFile').click()">
                    <i class="fas fa-cloud-upload-alt"></i>
                    <p>اضغط لرفع File الأرقام (.txt)</p>
                    <p style="color:var(--muted);font-size:12px;margin-top:6px">كل رقم في سطر منفصل</p>
                    <input type="file" id="numberFile" accept=".txt" style="display:none" onchange="handleFileSelect(this)">
                </div>
                <div class="filter-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-bottom:16px">
                    <div class="form-group"><label>اسم الFile</label><input type="text" id="fileName" placeholder="مثال: أرقام مصر"></div>
                    <div class="form-group"><label>Coast For each number ($)</label><input type="number" id="fileCost" placeholder="0.00" step="0.01"></div>
                </div>
                <button class="btn btn-primary" onclick="addNumbers()"><i class="fas fa-save"></i> حفظ الأرقام</button>
            </div>
        </div>

        <!-- DELETE NUMBERS -->
        <div class="content-section" id="deleteNumbers">
            <h3 class="section-title"><i class="fas fa-trash"></i> delete أرقام</h3>
            <div class="form-container">
                <div class="form-group"><label>Select file الأرقام</label><select id="deleteFileSelect" class="filter-select"><option value="">-- Select file --</option></select></div>
                <button class="btn btn-danger" onclick="deleteNumbers()"><i class="fas fa-trash"></i> delete الFile</button>
            </div>
        </div>

        <!-- DELETE ALL NUMBERS -->
        <div class="content-section" id="deleteAllNumbers">
            <h3 class="section-title"><i class="fas fa-trash-alt"></i> Delete all numbers</h3>
            <div class="form-container" style="text-align:center">
                <i class="fas fa-exclamation-triangle" style="font-size:4rem;color:var(--destructive);margin-bottom:20px"></i>
                <p style="margin-bottom:30px;font-size:1.1rem">هذا الإجراء سيDelete all numbers من عند جميع المستخدمين!</p>
                <button class="btn btn-danger" onclick="deleteAllNumbers()"><i class="fas fa-trash-alt"></i> نعم، اDelete all numbers</button>
            </div>
        </div>

        <!-- ADD TEST -->
        <div class="content-section" id="addTest">
            <h3 class="section-title"><i class="fas fa-vial"></i> إضافة Test number </h3>
            <div class="form-container">
                <div class="file-upload" onclick="document.getElementById('testFile').click()">
                    <i class="fas fa-cloud-upload-alt"></i>
                    <p>اضغط لرفع File Test number </p>
                    <input type="file" id="testFile" accept=".txt" style="display:none" onchange="handleTestFileSelect(this)">
                </div>
                <div class="form-group"><label>اسم الFile</label><input type="text" id="testFileName" placeholder="اسم الFile"></div>
                <button class="btn btn-primary" onclick="addTestNumbers()"><i class="fas fa-save"></i> حفظ</button>
            </div>
        </div>

        <!-- DELETE TEST -->
        <div class="content-section" id="deleteTest">
            <h3 class="section-title"><i class="fas fa-trash"></i> delete Test number </h3>
            <div class="form-container">
                <div class="form-group"><label>اختر الFile</label><select id="deleteTestSelect" class="filter-select"><option value="">-- اختر --</option></select></div>
                <button class="btn btn-danger" onclick="deleteTestNumbers()"><i class="fas fa-trash"></i> delete</button>
            </div>
        </div>

        <!-- DELETE ALL TEST -->
        <div class="content-section" id="deleteAllTest">
            <h3 class="section-title"><i class="fas fa-trash-alt"></i> delete كل التجريبي</h3>
            <div class="form-container" style="text-align:center">
                <i class="fas fa-exclamation-triangle" style="font-size:4rem;color:var(--destructive);margin-bottom:20px"></i>
                <p style="margin-bottom:30px">سيتم Delete all numbers التجريبية!</p>
                <button class="btn btn-danger" onclick="deleteAllTest()"><i class="fas fa-trash-alt"></i> delete الكل</button>
            </div>
        </div>

        <!-- PENDING USERS -->
        <div class="content-section" id="pendingUsers">
            <h3 class="section-title"><i class="fas fa-user-clock"></i> طلبات التسجيل</h3>
            <div class="form-container">
                <div class="action-buttons">
                    <button class="btn btn-success" onclick="approveAllUsers()"><i class="fas fa-check-double"></i> قبول الكل</button>
                </div>
                <div class="table-wrapper">
                    <table>
                        <thead><tr><th>User</th><th>phone number </th><th>تاريخ الطلب</th><th>الإجراءات</th></tr></thead>
                        <tbody id="pendingUsersTable"></tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- ACCOUNTS -->
        <div class="content-section" id="accounts">
            <h3 class="section-title"><i class="fas fa-users"></i> إدارة الحسابات</h3>
            <div class="table-wrapper">
                <div class="table-controls">
                    <div class="table-show"><span>عرض</span><select><option>10</option><option>25</option><option>50</option></select><span>إدخالات</span></div>
                    <div class="table-export">
                        <button class="btn btn-outline btn-sm" onclick="exportTable('csv')"><i class="fas fa-file-csv"></i> CSV</button>
                        <button class="btn btn-outline btn-sm" onclick="exportTable('excel')"><i class="fas fa-file-excel"></i> Excel</button>
                    </div>
                </div>
                <table>
                    <thead><tr><th>المستخدم</th><th>الدور</th><th>الحالة</th><th>الحد</th><th>الإجراءات</th></tr></thead>
                    <tbody id="accountsTable"></tbody>
                </table>
            </div>
        </div>

        <!-- INCREASE LIMIT -->
        <div class="content-section" id="increaseLimit">
            <h3 class="section-title"><i class="fas fa-arrow-up"></i> زيادة الحد</h3>
            <div class="form-container">
                <div class="filter-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-bottom:16px">
                    <div class="form-group"><label>User</label><select id="limitUserSelect" class="filter-select"></select></div>
                    <div class="form-group"><label>العدد الجديد</label><input type="number" id="newLimit" placeholder="عدد الأرقام المسموح بها"></div>
                </div>
                <button class="btn btn-primary" onclick="increaseLimit()"><i class="fas fa-save"></i> حفظ</button>
            </div>
        </div>

        <!-- ADD ADMIN -->
        <div class="content-section" id="addAdmin">
            <h3 class="section-title"><i class="fas fa-user-shield"></i> إضافة أدمن</h3>
            <div class="form-container">
                <div class="filter-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-bottom:16px">
                    <div class="form-group"><label>User</label><input type="text" id="adminUsername" placeholder="اسم الأدمن"></div>
                    <div class="form-group"><label>Password</label><input type="password" id="adminPassword" placeholder="Password"></div>
                </div>
                <button class="btn btn-primary" onclick="addAdmin()"><i class="fas fa-user-plus"></i> إنشاء أدمن</button>
            </div>
        </div>

        <!-- DELETE ADMIN -->
        <div class="content-section" id="deleteAdmin">
            <h3 class="section-title"><i class="fas fa-user-times"></i> delete أدمن</h3>
            <div class="form-container">
                <div class="form-group"><label>اسم الأدمن</label><select id="adminSelect" class="filter-select"></select></div>
                <button class="btn btn-danger" onclick="deleteAdmin()"><i class="fas fa-user-times"></i> delete صلاحيات الأدمن</button>
            </div>
        </div>

        <!-- BROADCAST -->
        <div class="content-section" id="broadcast">
            <h3 class="section-title"><i class="fas fa-broadcast-tower"></i> إذاعة رسالة</h3>
            <div class="form-container">
                <div class="form-group"><label>الرسالة</label><textarea id="broadcastMessage" rows="5" placeholder="اكتب رسالتك هنا..."></textarea></div>
                <button class="btn btn-primary" onclick="sendBroadcast()"><i class="fas fa-paper-plane"></i> إرسال للجميع</button>
            </div>
        </div>

        <!-- NOTIFICATIONS -->
        <div class="content-section" id="notifications">
            <h3 class="section-title"><i class="fas fa-bell"></i> notifications</h3>
            <div id="notificationsList"></div>
        </div>

        <!-- API TEST -->
        <div class="content-section" id="apiTest">
            <h3 class="section-title"><i class="fas fa-plug"></i> فحص اتصال APIs</h3>
            <div class="form-container">
                <button class="btn btn-primary" onclick="testAPIs()"><i class="fas fa-sync-alt"></i> فحص APIs</button>
                <div id="apiTestResults" style="margin-top:20px"></div>
            </div>
        </div>
    </div>

    <!-- FOOTER -->
    <footer class="footer">
        <p>© 2026 X PANEL OTP System. جميع الحقوق محفوظة.</p>
    </footer>
</div>

<div class="toast-container" id="toastContainer"></div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.5.1/socket.io.js"></script>
<script>
const socket=io();
let selectedFile=null,selectedTestFile=null;
socket.on('connect',()=>{socket.emit('join',{username:'mohaymen'})});
socket.on('broadcast',(data)=>{showToast('إذاعة: '+data.message,'info')});

function showSection(sectionId,btn){
    document.querySelectorAll('.content-section').forEach(s=>s.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
    document.getElementById(sectionId).classList.add('active');
    if(btn) btn.classList.add('active');
    if(sectionId==='pendingUsers')loadPendingUsers();
    if(sectionId==='accounts')loadAccounts();
    if(sectionId==='deleteNumbers')loadDeleteFiles();
    if(sectionId==='deleteTest')loadDeleteTestFiles();
    if(sectionId==='increaseLimit')loadLimitUsers();
    if(sectionId==='deleteAdmin')loadAdminSelect();
    if(sectionId==='dashboard')loadDashboardStats();
    if(sectionId==='notifications')loadNotifications();
}

function showToast(message,type='success'){
    const container=document.getElementById('toastContainer');
    const toast=document.createElement('div');
    toast.className='toast '+(type==='error'?'error':type==='info'?'info':type==='warning'?'warning':'');
    toast.innerHTML=`<i class="fas fa-${type==='success'?'check-circle':type==='error'?'exclamation-circle':type==='info'?'info-circle':'exclamation-triangle'}"></i> ${message}`;
    container.appendChild(toast);
    setTimeout(()=>toast.remove(),5000);
}

async function loadDashboardStats(){
    const users=await fetch('/api/owner/accounts').then(r=>r.json());
    const pending=await fetch('/api/owner/pending_users').then(r=>r.json());
    const allUsers=users.users||{};
    document.getElementById('totalUsers').textContent=Object.keys(allUsers).length;
    document.getElementById('pendingCount').textContent=Object.keys(pending.users||{}).length;
    let banned=0;
    for(const u of Object.values(allUsers)){if(u.status==='banned')banned++;}
    document.getElementById('bannedCount').textContent=banned;
    const numbers=await fetch('/api/user/available_numbers').then(r=>r.json());
    let totalNums=0;
    for(const f of Object.values(numbers.files||{})){totalNums+=(f.numbers?.length||0);}
    document.getElementById('totalNumbers').textContent=totalNums;
}

function handleFileSelect(input){selectedFile=input.files[0];if(selectedFile)showToast('تم اختيار الFile: '+selectedFile.name)}
function handleTestFileSelect(input){selectedTestFile=input.files[0];if(selectedTestFile)showToast('تم اختيار الFile: '+selectedTestFile.name)}

async function addNumbers(){
    if(!selectedFile){showToast('Select file أولاً','error');return}
    const formData=new FormData();
    formData.append('file',selectedFile);
    formData.append('filename',document.getElementById('fileName').value);
    formData.append('cost',document.getElementById('fileCost').value);
    const response=await fetch('/api/owner/add_numbers',{method:'POST',body:formData});
    const data=await response.json();
    if(data.success){showToast('تم إضافة '+data.count+' رقم');selectedFile=null;document.getElementById('numberFile').value='';document.getElementById('fileName').value='';document.getElementById('fileCost').value='';}
    else{showToast(data.message,'error')}
}

async function loadDeleteFiles(){
    const response=await fetch('/api/user/available_numbers');
    const data=await response.json();
    const select=document.getElementById('deleteFileSelect');
    select.innerHTML='<option value="">-- Select file --</option>';
    for(const[name,info]of Object.entries(data.files||{})){select.innerHTML+=`<option value="${name}">${name} (${info.numbers?.length||0} رقم)</option>`}
}

async function deleteNumbers(){
    const filename=document.getElementById('deleteFileSelect').value;
    if(!filename){showToast('Select file','error');return}
    const response=await fetch('/api/owner/delete_numbers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename})});
    const data=await response.json();
    if(data.success){showToast('تم الdelete بنجاح');loadDeleteFiles()}
}

async function deleteAllNumbers(){if(!confirm('هل أنت متأكد من Delete all numbers؟'))return;const response=await fetch('/api/owner/delete_all_numbers',{method:'POST'});const data=await response.json();if(data.success)showToast('تم Delete all numbers')}

async function addTestNumbers(){
    if(!selectedTestFile){showToast('Select file','error');return}
    const formData=new FormData();
    formData.append('file',selectedTestFile);
    formData.append('filename',document.getElementById('testFileName').value);
    const response=await fetch('/api/owner/add_test_numbers',{method:'POST',body:formData});
    const data=await response.json();
    if(data.success){showToast('تم إضافة '+data.count+' رقم تجريبي');selectedTestFile=null;document.getElementById('testFile').value='';document.getElementById('testFileName').value='';}
}

async function loadDeleteTestFiles(){
    const response=await fetch('/api/user/test_numbers');
    const data=await response.json();
    const select=document.getElementById('deleteTestSelect');
    select.innerHTML='<option value="">-- اختر --</option>';
    for(const name of Object.keys(data.files||{})){select.innerHTML+=`<option value="${name}">${name}</option>`}
}

async function deleteTestNumbers(){
    const filename=document.getElementById('deleteTestSelect').value;
    if(!filename)return;
    await fetch('/api/owner/delete_test_numbers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename})});
    showToast('تم الdelete');loadDeleteTestFiles();
}

async function deleteAllTest(){if(!confirm('هل أنت متأكد؟'))return;await fetch('/api/owner/delete_all_test',{method:'POST'});showToast('تم delete كل التجريبي')}

async function loadPendingUsers(){
    const response=await fetch('/api/owner/pending_users');
    const data=await response.json();
    const tbody=document.getElementById('pendingUsersTable');
    tbody.innerHTML='';
    for(const[username,user]of Object.entries(data.users||{})){
        tbody.innerHTML+=`<tr><td class="text-primary">${username}</td><td>${user.phone||'-'}</td><td class="text-muted">${new Date(user.created_at).toLocaleDateString('ar')}</td><td><button class="btn btn-success btn-sm" onclick="approveUser('${username}')"><i class="fas fa-check"></i> قبول</button><button class="btn btn-danger btn-sm" onclick="rejectUser('${username}')" style="margin-right:5px"><i class="fas fa-times"></i> رفض</button></td></tr>`;
    }
}

async function approveUser(username){
    await fetch('/api/owner/approve_user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,action:'approve'})});
    showToast('تم قبول '+username);loadPendingUsers();
}

async function rejectUser(username){
    await fetch('/api/owner/approve_user',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,action:'reject'})});
    showToast('تم رفض '+username);loadPendingUsers();
}

async function approveAllUsers(){
    await fetch('/api/owner/approve_all',{method:'POST'});
    showToast('تم قبول كل المستخدمين');loadPendingUsers();
}

async function loadAccounts(){
    const response=await fetch('/api/owner/accounts');
    const data=await response.json();
    const tbody=document.getElementById('accountsTable');
    tbody.innerHTML='';
    for(const[username,user]of Object.entries(data.users||{})){
        if(username==='mohaymen')continue;
        const statusClass=user.status==='active'?'status-active':user.status==='pending'?'status-pending':'status-banned';
        const roleClass=user.role==='admin'?'status-admin':'';
        tbody.innerHTML+=`<tr><td class="text-primary">${username}</td><td><span class="status-badge ${roleClass}">${user.role}</span></td><td><span class="status-badge ${statusClass}">${user.status}</span></td><td>${user.limit||0}</td><td><button class="btn ${user.status==='active'?'btn-danger':'btn-success'} btn-sm" onclick="toggleBan('${username}')"><i class="fas fa-ban"></i> ${user.status==='active'?'حظر':'إلغاء'}</button></td></tr>`;
    }
}

async function toggleBan(username){
    await fetch('/api/owner/toggle_ban',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username})});
    loadAccounts();
}

async function loadLimitUsers(){
    const response=await fetch('/api/owner/accounts');
    const data=await response.json();
    const select=document.getElementById('limitUserSelect');
    select.innerHTML='';
    for(const username of Object.keys(data.users||{})){if(username!=='mohaymen'){select.innerHTML+=`<option value="${username}">${username}</option>`}}
}

async function increaseLimit(){
    const username=document.getElementById('limitUserSelect').value;
    const limit=document.getElementById('newLimit').value;
    const response=await fetch('/api/owner/increase_limit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,limit})});
    const data=await response.json();
    if(data.success)showToast('تم زيادة الحد');
}

async function addAdmin(){
    const username=document.getElementById('adminUsername').value;
    const password=document.getElementById('adminPassword').value;
    const response=await fetch('/api/owner/add_admin',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});
    const data=await response.json();
    if(data.success){showToast('تم إضافة الأدمن');document.getElementById('adminUsername').value='';document.getElementById('adminPassword').value='';loadAdminSelect();}
    else{showToast(data.message,'error')}
}

async function loadAdminSelect(){
    const response=await fetch('/api/owner/accounts');
    const data=await response.json();
    const select=document.getElementById('adminSelect');
    select.innerHTML='';
    for(const[username,user]of Object.entries(data.users||{})){if(user.role==='admin'){select.innerHTML+=`<option value="${username}">${username}</option>`}}
}

async function deleteAdmin(){
    const username=document.getElementById('adminSelect').value;
    if(!username)return;
    await fetch('/api/owner/delete_admin',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username})});
    showToast('تم delete صلاحيات الأدمن');loadAdminSelect();loadAccounts();
}

async function sendBroadcast(){
    const message=document.getElementById('broadcastMessage').value;
    if(!message){showToast('اكتب رسالة','error');return}
    await fetch('/api/owner/broadcast',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message})});
    showToast('تم الإذاعة');document.getElementById('broadcastMessage').value='';
}

async function loadNotifications(){
    const response=await fetch('/api/user/notifications');
    const data=await response.json();
    const container=document.getElementById('notificationsList');
    container.innerHTML='';
    const notifs=data.notifications||[];
    if(notifs.length===0){container.innerHTML='<div class="form-container" style="text-align:center"><p style="color:var(--muted)">لا توجد إشعارات</p></div>';return;}
    for(const notif of notifs.slice().reverse()){
        container.innerHTML+=`<div class="notification-panel ${notif.read?'':'unread'}"><div class="header"><span class="type">${notif.type}</span><span class="time">${new Date(notif.time).toLocaleString('ar')}</span></div><p>${notif.message}</p></div>`;
    }
}

async function testAPIs(){
    const btn = event.target;
    btn.querySelector('i').classList.add('fa-spin');
    const response = await fetch('/api/test_api_connection');
    const data = await response.json();
    const container = document.getElementById('apiTestResults');

    let html = '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px">';
    for(const[name,info] of Object.entries(data.apis||{})){
        const color = info.status==='connected' ? 'var(--success)' : 'var(--destructive)';
        html += `<div style="border:1px solid var(--border);border-radius:8px;padding:16px">
            <h4 style="color:${color};margin-bottom:8px"><i class="fas fa-${info.status==='connected'?'check-circle':'times-circle'}"></i> ${name}</h4>
            <p>الحالة: ${info.status}</p>
            <p>الرسائل: ${info.count||0}</p>
            <p style="font-size:11px;color:var(--muted);margin-top:8px">المفاتيح: ${(info.sample_keys||[]).join(', ')}</p>
        </div>`;
    }
    html += '</div>';
    container.innerHTML = html;
    btn.querySelector('i').classList.remove('fa-spin');
    showToast('تم فحص APIs');
}

function exportTable(type){showToast('جاري التصدير...','info');}
function logout(){window.location.href='/logout'}
loadDashboardStats();
</script>
</body>
</html>
"""
USER_HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>X PANEL - User</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
:root{--primary:#1E40AF;--primary-light:#3B82F6;--primary-dark:#1E3A8A;--background:#FFFFFF;--foreground:#1F2937;--secondary:#F3F4F6;--border:#E5E7EB;--muted:#6B7280;--destructive:#DC2626;--success:#10B981;--warning:#F59E0B;--card-bg:#FFFFFF;--sidebar-width:260px}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background-color:#F9FAFB;color:var(--foreground);line-height:1.6;min-height:100vh}
h1,h2,h3,h4,h5,h6{font-family:'Poppins',sans-serif;font-weight:600}

/* ===== SIDEBAR ===== */
.sidebar{position:fixed;right:0;top:0;width:var(--sidebar-width);height:100vh;background:white;border-left:1px solid var(--border);padding:20px 0;overflow-y:auto;z-index:100;box-shadow:-2px 0 10px rgba(0,0,0,0.05)}
.sidebar-logo{text-align:center;margin-bottom:24px;padding:0 20px 20px;border-bottom:1px solid var(--border)}
.sidebar-logo h1{font-family:'Poppins',sans-serif;font-size:1.4rem;font-weight:700;color:var(--primary);margin-bottom:4px}
.sidebar-logo p{color:var(--muted);font-size:0.75rem;font-weight:500}
.nav-section{margin-top:8px;padding:0 12px}
.nav-section-title{font-size:0.7rem;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-bottom:8px;padding:0 8px;font-weight:600}
.nav-item{display:flex;align-items:center;padding:10px 14px;margin-bottom:4px;border-radius:8px;cursor:pointer;transition:all 0.2s ease;border:none;background:none;width:100%;text-align:right;font-family:'Inter',sans-serif;font-size:0.85rem;color:var(--foreground);gap:10px}
.nav-item:hover{background:var(--secondary);color:var(--primary)}
.nav-item.active{background:var(--primary);color:white}
.nav-item.active i{color:white}
.nav-item i{font-size:1rem;width:20px;text-align:center;color:var(--muted);transition:color 0.2s}
.nav-item:hover i{color:var(--primary)}
.nav-item.active:hover{background:var(--primary-dark)}
.nav-item.active:hover i{color:white}

/* ===== MAIN CONTENT ===== */
.main-content{margin-right:var(--sidebar-width);min-height:100vh;display:flex;flex-direction:column}
.page-content{flex:1;max-width:1400px;margin:0 auto;padding:24px 32px;width:100%}

/* ===== HEADER ===== */
.header{background-color:white;border-bottom:1px solid var(--border);box-shadow:0 1px 3px rgba(0,0,0,0.05);padding:14px 32px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:40}
.header-left h2{font-size:20px;margin-bottom:2px;color:var(--foreground)}
.header-left p{font-size:13px;color:var(--muted)}
.header-right{display:flex;align-items:center;gap:14px}
.header-icon-btn{position:relative;background:none;border:none;cursor:pointer;color:var(--muted);transition:all 0.2s ease;padding:8px;border-radius:8px;font-size:18px}
.header-icon-btn:hover{color:var(--primary);background-color:var(--secondary)}
.notification-badge{position:absolute;top:4px;right:4px;width:8px;height:8px;background-color:var(--destructive);border-radius:50%}
.divider{width:1px;height:24px;background-color:var(--border)}
.user-profile{display:flex;align-items:center;gap:10px;cursor:pointer}
.user-avatar{width:34px;height:34px;background-color:var(--primary);border-radius:50%;display:flex;align-items:center;justify-content:center;color:white;font-size:16px;font-weight:600}
.user-name{font-size:14px;font-weight:500}
.logout-btn{background:var(--destructive);color:#fff;border:none;padding:8px 18px;border-radius:6px;cursor:pointer;font-family:'Inter',sans-serif;font-weight:600;font-size:13px;transition:all 0.2s ease;display:inline-flex;align-items:center;gap:6px}
.logout-btn:hover{background:#B91C1C;transform:translateY(-1px)}

/* ===== SECTIONS ===== */
.page-section{margin-bottom:20px}
.section-title{font-size:18px;font-weight:600;margin-bottom:16px;color:var(--foreground);display:flex;align-items:center;gap:10px}
.section-title::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--border),transparent)}
.content-section{display:none;animation:fadeIn 0.3s ease}
.content-section.active{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}

/* ===== CARDS ===== */
.cards-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:24px}
.stat-card{background:white;border:1px solid var(--border);border-radius:8px;padding:20px;transition:all 0.2s ease;box-shadow:0 1px 3px rgba(0,0,0,0.05)}
.stat-card:hover{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,0.1)}
.stat-card .icon{font-size:24px;margin-bottom:8px;display:block}
.stat-card .number{font-family:'Poppins',sans-serif;font-size:1.6rem;font-weight:700;margin-bottom:4px;color:var(--foreground)}
.stat-card .label{color:var(--muted);font-size:12px}

/* ===== BUTTONS ===== */
.action-buttons{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap}
.btn{padding:10px 18px;border-radius:6px;border:none;cursor:pointer;font-size:13px;font-weight:500;transition:all 0.2s ease;display:inline-flex;align-items:center;gap:8px;font-family:'Inter',sans-serif}
.btn-primary{background-color:var(--primary);color:white}
.btn-primary:hover{background-color:var(--primary-light);transform:translateY(-1px);box-shadow:0 4px 12px rgba(30,64,175,0.2)}
.btn-outline{background-color:white;color:var(--foreground);border:1px solid var(--border)}
.btn-outline:hover{background-color:var(--secondary);border-color:var(--primary);color:var(--primary)}
.btn-danger{background-color:var(--destructive);color:white}
.btn-danger:hover{background-color:#B91C1C;transform:translateY(-1px)}
.btn-success{background-color:var(--success);color:white}
.btn-success:hover{background-color:#059669;transform:translateY(-1px)}
.btn-sm{padding:6px 12px;font-size:12px}

/* ===== FORMS ===== */
.form-container{background:white;border:1px solid var(--border);border-radius:8px;padding:24px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.05)}
.form-group{margin-bottom:16px}
.form-group label{display:block;margin-bottom:6px;font-size:13px;font-weight:500;color:var(--foreground)}
.form-group input,.form-group textarea,.form-group select{width:100%;padding:10px 14px;border:1px solid var(--border);border-radius:6px;font-size:13px;background-color:white;color:var(--foreground);font-family:'Inter',sans-serif;transition:all 0.2s ease}
.form-group input:focus,.form-group textarea:focus,.form-group select:focus{outline:none;border-color:var(--primary);box-shadow:0 0 0 3px rgba(30,64,175,0.1)}
.form-group input::placeholder,.form-group textarea::placeholder{color:var(--muted)}

/* ===== TABLE ===== */
.table-wrapper{background-color:white;border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.05)}
.table-controls{display:flex;align-items:center;justify-content:space-between;padding:14px 20px;background-color:var(--secondary);border-bottom:1px solid var(--border);flex-wrap:wrap;gap:12px}
.table-show{display:flex;align-items:center;gap:8px;font-size:13px}
.table-show select{padding:6px 10px;border:1px solid var(--border);border-radius:4px;font-size:12px;background-color:white;cursor:pointer;font-family:'Inter',sans-serif}
table{width:100%;border-collapse:collapse}
thead{background-color:var(--secondary)}
th{padding:12px 16px;text-align:right;font-size:12px;font-weight:600;color:var(--foreground);border-bottom:1px solid var(--border);white-space:nowrap}
td{padding:12px 16px;font-size:13px;border-bottom:1px solid var(--border)}
tbody tr{transition:background-color 0.2s ease}
tbody tr:hover{background-color:var(--secondary)}
tbody tr:nth-child(even){background-color:rgba(243,244,246,0.5)}
.text-primary{color:var(--primary);font-weight:500}
.text-muted{color:var(--muted)}
.text-mono{font-family:'Courier New',monospace;font-weight:500;font-size:12px}
.text-success{color:var(--success);font-weight:500}
.text-danger{color:var(--destructive);font-weight:500}

/* ===== FILE CARDS ===== */
.files-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
.file-card{background:white;border:1px solid var(--border);border-radius:8px;padding:20px;transition:all 0.2s ease;box-shadow:0 1px 3px rgba(0,0,0,0.05)}
.file-card:hover{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,0.1);border-color:var(--primary)}
.file-card h4{color:var(--primary);margin-bottom:12px;font-size:15px;display:flex;align-items:center;gap:8px}
.file-card .info{display:flex;justify-content:space-between;margin-bottom:10px;color:var(--muted);font-size:13px}
.file-card .cost{color:var(--success);font-weight:700;font-size:16px}
.qty-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:12px}
.qty-btn{padding:10px;background:rgba(30,64,175,0.05);border:1px solid var(--border);border-radius:6px;color:var(--primary);font-family:'Poppins',sans-serif;font-size:14px;font-weight:600;cursor:pointer;transition:all 0.2s ease}
.qty-btn:hover,.qty-btn.selected{background:var(--primary);color:white;border-color:var(--primary);transform:scale(1.02)}

/* ===== SMS CARDS ===== */
.sms-card{background:white;border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:12px;transition:all 0.2s ease}
.sms-card:hover{border-color:var(--primary);box-shadow:0 2px 8px rgba(30,64,175,0.08)}
.sms-card .phone{color:var(--primary);font-weight:600;font-size:14px;margin-bottom:8px;display:flex;align-items:center;gap:8px}
.sms-card .message{color:var(--foreground);margin-bottom:10px;line-height:1.6;font-size:13px}
.sms-card .meta{display:flex;justify-content:space-between;font-size:12px;color:var(--muted);align-items:center}
.sms-card .api-badge{background:rgba(30,64,175,0.1);color:var(--primary);padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600}
.sms-card.test .phone{color:var(--warning)}
.sms-card.api-global{border-color:var(--warning);background:rgba(245,158,11,0.03)}
.sms-card.api-global .phone{color:var(--warning)}
.sms-card.api-test-global{border-color:var(--success);background:rgba(16,185,129,0.03)}
.sms-card.api-test-global .phone{color:var(--success)}

/* ===== NOTIFICATION PANEL ===== */
.notification-panel{background:white;border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:12px;transition:all 0.2s ease}
.notification-panel.unread{border-color:var(--warning);background:rgba(245,158,11,0.03)}
.notification-panel .header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.notification-panel .type{background:rgba(30,64,175,0.1);color:var(--primary);padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600}
.notification-panel .time{color:var(--muted);font-size:12px}
.notification-panel p{font-size:13px;color:var(--foreground);line-height:1.5}

/* ===== TOAST ===== */
.toast-container{position:fixed;top:20px;left:20px;z-index:9999;display:flex;flex-direction:column;gap:10px}
.toast{background:white;border-right:4px solid var(--success);border-radius:8px;padding:14px 18px;min-width:300px;box-shadow:0 10px 30px rgba(0,0,0,0.15);animation:toastIn 0.3s ease;font-size:13px;display:flex;align-items:center;gap:10px}
.toast.error{border-right-color:var(--destructive)}
.toast.info{border-right-color:var(--primary)}
.toast.warning{border-right-color:var(--warning)}
@keyframes toastIn{from{transform:translateX(-100%);opacity:0}to{transform:translateX(0);opacity:1}}

/* ===== FOOTER ===== */
.footer{background-color:white;border-top:1px solid var(--border);padding:16px 32px;text-align:center;font-size:12px;color:var(--muted);margin-top:auto}

/* ===== RESPONSIVE ===== */
@media(max-width:768px){
    .sidebar{width:100%;transform:translateX(100%);transition:transform 0.3s ease}
    .sidebar.open{transform:translateX(0)}
    .main-content{margin-right:0}
    .header{flex-direction:column;align-items:flex-start;gap:10px;padding:12px 20px}
    .header-right{width:100%;justify-content:flex-start}
    .page-content{padding:16px 20px}
    .cards-grid{grid-template-columns:1fr}
    .qty-grid{grid-template-columns:repeat(2,1fr)}
    .files-grid{grid-template-columns:1fr}
    table{font-size:12px}
    th,td{padding:10px 12px}
}
@media(max-width:640px){
    .header-left h2{font-size:18px}
    .section-title{font-size:16px}
    .user-name{display:none}
}
</style>
</head>
<body>

<!-- SIDEBAR -->
<div class="sidebar">
    <div class="sidebar-logo">
        <img src="https://i.ibb.co/CKXS2Lcg/1000146872.png" alt="X PANEL" style="width:80px;height:auto;margin-bottom:8px;border-radius:8px;">
        <h1>X PANEL</h1>
        <p>USER PANEL</p>
    </div>

    <div class="nav-section">
        <div class="nav-section-title">main Dashboard</div>
        <button class="nav-item active" onclick="showSection('dashboard',this)">
            <i class="fas fa-home"></i> Dashboard
        </button>
    </div>

    <div class="nav-section">
        <div class="nav-section-title">الأرقام</div>
        <button class="nav-item" onclick="showSection('requestNumbers',this)">
            <i class="fas fa-plus-circle"></i> Request numbers
        </button>
        <button class="nav-item" onclick="showSection('myNumbers',this)">
            <i class="fas fa-list"></i> My Numbers 
        </button>
        <button class="nav-item" onclick="showSection('myRange',this)">
            <i class="fas fa-chart-bar"></i> My Range
        </button>
        <button class="nav-item" onclick="showSection('myFiles',this)">
            <i class="fas fa-file-download"></i> My File number 
        </button>
    </div>

    <div class="nav-section">
        <div class="nav-section-title">الرسائل</div>
        <button class="nav-item" onclick="showSection('mySMS',this)">
            <i class="fas fa-envelope"></i> My massage 
        </button>
        <button class="nav-item" onclick="showSection('testNumbers',this)">
            <i class="fas fa-vial"></i> Test number 
        </button>
        <button class="nav-item" onclick="showSection('testSMS',this)">
            <i class="fas fa-flask"></i> Sms test
        </button>
    </div>

    <div class="nav-section">
        <div class="nav-section-title">الحساب</div>
        <button class="nav-item" onclick="showSection('notifications',this)">
            <i class="fas fa-bell"></i> notifications
        </button>
        <button class="nav-item" onclick="showSection('payments',this)">
            <i class="fas fa-credit-card"></i> Payments
        </button>
        <button class="nav-item" onclick="showSection('myAccount',this)">
            <i class="fas fa-user-cog"></i> My account
        </button>
    </div>
</div>

<!-- MAIN CONTENT -->
<div class="main-content">
    <!-- HEADER -->
    <header class="header">
        <div class="header-left">
            <h2><i class="fas fa-user" style="color:var(--primary)"></i> AGENT PANEL</h2>
            <p>X PANEL</p>
        </div>
        <div class="header-right">
            <button class="header-icon-btn" onclick="showSection('notifications',this)" title="notifications">
                <i class="fas fa-bell"></i>
                <span class="notification-badge" id="notifBadge" style="display:none"></span>
            </button>
            <button class="header-icon-btn" title="الإعدادات"><i class="fas fa-cog"></i></button>
            <div class="divider"></div>
            <div class="user-profile">
                <div class="user-avatar" id="userAvatar">U</div>
                <span class="user-name" id="userNameDisplay">User</span>
            </div>
            <button class="logout-btn" onclick="logout()"><i class="fas fa-sign-out-alt"></i> Logout</button>
        </div>
    </header>

    <!-- PAGE CONTENT -->
    <div class="page-content">
        <!-- DASHBOARD -->
        <div class="content-section active" id="dashboard">
            <div class="cards-grid">
                <div class="stat-card"><span class="icon" style="color:var(--primary)">📱</span><div class="number" id="totalMyNumbers">0</div><div class="label">Total My Numbers </div></div>
                <div class="stat-card"><span class="icon" style="color:var(--success)">💬</span><div class="number" id="totalMySMS">0</div><div class="label">Messages received</div></div>
                <div class="stat-card"><span class="icon" style="color:var(--warning)">📁</span><div class="number" id="totalMyFiles">0</div><div class="label">file</div></div>
                <div class="stat-card"><span class="icon" style="color:var(--destructive)">💰</span><div class="number" id="totalSpent">0</div><div class="label">Total expenses ($)</div></div>
                <div class="stat-card"><span class="icon" style="color:var(--primary)">📊</span><div class="number" id="dailyLimitRemaining">2000</div><div class="label">Remaining daily limit</div></div>
            </div>
        </div>

        <!-- REQUEST NUMBERS -->
        <div class="content-section" id="requestNumbers">
            <h3 class="section-title"><i class="fas fa-plus-circle"></i> Request numbers جديدة</h3>
            <div id="availableFiles"></div>
        </div>

        <!-- MY NUMBERS -->
        <div class="content-section" id="myNumbers">
            <h3 class="section-title"><i class="fas fa-list"></i> My Numbers </h3>
            <div class="action-buttons">
                <button class="btn btn-danger" onclick="showDeleteMyNumbers()"><i class="fas fa-trash"></i> delete My Numbers </button>
            </div>
            <div id="myNumbersList"></div>
        </div>

        <!-- MY RANGE -->
        <div class="content-section" id="myRange">
            <h3 class="section-title"><i class="fas fa-chart-bar"></i> Range  My Numbers </h3>
            <div id="myRangeList"></div>
        </div>

        <!-- MY FILES -->
        <div class="content-section" id="myFiles">
            <h3 class="section-title"><i class="fas fa-file-download"></i> My File number </h3>
            <div class="action-buttons">
                <button class="btn btn-danger" onclick="showDeleteMyFiles()"><i class="fas fa-trash"></i> delete File</button>
            </div>
            <div id="myFilesList"></div>
        </div>

        <!-- MY SMS -->
        <div class="content-section" id="mySMS">
            <h3 class="section-title"><i class="fas fa-envelope"></i> My massage </h3>
            <div class="action-buttons">
                <button class="btn btn-primary" id="refreshSMSBtn" onclick="refreshSMS()"><i class="fas fa-sync-alt"></i> Messages update</button>
                <button class="btn btn-outline" onclick="debugSMS()"><i class="fas fa-bug"></i> Check</button>
            </div>
            <div class="form-container" style="padding:16px;margin-bottom:16px">
                <div style="display:flex;gap:10px;align-items:center">
                    <div style="flex:1">
                        <input type="text" id="smsSearchInput" placeholder="🔍 Search phone..." 
                            style="width:100%;padding:10px 14px;border:1px solid var(--border);border-radius:6px;font-size:13px;font-family:'Inter',sans-serif"
                            onkeyup="searchSMS()">
                    </div>
                    <button class="btn btn-outline" onclick="clearSMSSearch()" style="white-space:nowrap">
                        <i class="fas fa-times"></i> مسح
                    </button>
                </div>
                <div id="smsSearchStats" style="margin-top:8px;font-size:12px;color:var(--muted)"></div>
            </div>
            <div id="smsDebugInfo" style="margin-bottom:16px;font-size:12px;color:var(--muted);display:none"></div>
            <div id="smsList"></div>
        </div>

        <!-- TEST NUMBERS -->
        <div class="content-section" id="testNumbers">
            <h3 class="section-title"><i class="fas fa-vial"></i> Test number </h3>
            <div id="testNumbersList"></div>
        </div>

        <!-- TEST SMS -->
        <div class="content-section" id="testSMS">
            <h3 class="section-title"><i class="fas fa-flask"></i> Sms</h3>
            <div id="testSMSList"></div>
        </div>

        <!-- NOTIFICATIONS -->
        <div class="content-section" id="notifications">
            <h3 class="section-title"><i class="fas fa-bell"></i> notifications</h3>
            <div id="notificationsList"></div>
        </div>

        <!-- PAYMENTS -->
        <div class="content-section" id="payments">
            <h3 class="section-title"><i class="fas fa-credit-card"></i> Payments</h3>
            <div class="table-wrapper">
                <table>
                    <thead><tr><th>tipe</th><th>the details</th><th>Coast</th><th>Data</th></tr></thead>
                    <tbody id="paymentsTable"></tbody>
                </table>
            </div>
        </div>

        <!-- MY ACCOUNT -->
        <div class="content-section" id="myAccount">
            <h3 class="section-title"><i class="fas fa-user-cog"></i> Setting account</h3>
            <div class="form-container">
                <div class="form-group"><label>Password new</label><input type="password" id="newPassword" placeholder="اترك فارغاً إذا لا تريد التغيير"></div>
                <div class="form-group"><label>phone number </label><input type="tel" id="newPhone" placeholder="phone number "></div>
                <button class="btn btn-primary" onclick="updateAccount()"><i class="fas fa-save"></i> Save</button>
            </div>
        </div>
    </div>

    <!-- FOOTER -->
    <footer class="footer">
        <p>© 2026 X PANEL OTP System. جميع الحقوق محفوظة.</p>
    </footer>
</div>

<div class="toast-container" id="toastContainer"></div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.5.1/socket.io.js"></script>
<script>
const socket=io();
let currentUsername='';
socket.on('connect',()=>{fetch('/api/user/my_account').then(r=>r.json()).then(data=>{if(data.success){currentUsername=data.user.username||'';document.getElementById('userAvatar').textContent=currentUsername.charAt(0).toUpperCase();document.getElementById('userNameDisplay').textContent=currentUsername;socket.emit('join',{username:currentUsername})}})});
socket.on('new_sms',(data)=>{showToast('رسالة جديدة من: '+data.number,'info');if(document.getElementById('mySMS').classList.contains('active')){loadMySMS()}updateNotificationBadge()});
socket.on('broadcast',(data)=>{showToast('إذاعة: '+data.message,'info');if('Notification' in window&&Notification.permission==='granted'){new Notification('X PANEL',{body:data.message})}});

function showSection(sectionId,btn){
    document.querySelectorAll('.content-section').forEach(s=>s.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
    document.getElementById(sectionId).classList.add('active');
    if(btn) btn.classList.add('active');
    if(sectionId==='requestNumbers')loadAvailableFiles();
    if(sectionId==='myNumbers')loadMyNumbers();
    if(sectionId==='myRange')loadMyRange();
    if(sectionId==='myFiles')loadMyFiles();
    if(sectionId==='mySMS')loadMySMS();
    if(sectionId==='testNumbers')loadTestNumbers();
    if(sectionId==='testSMS')loadTestSMS();
    if(sectionId==='notifications')loadNotifications();
    if(sectionId==='payments')loadPayments();
    if(sectionId==='dashboard')loadDashboardStats();
}

function showToast(message,type='success'){
    const container=document.getElementById('toastContainer');
    const toast=document.createElement('div');
    toast.className='toast '+(type==='error'?'error':type==='info'?'info':type==='warning'?'warning':'');
    toast.innerHTML=`<i class="fas fa-${type==='success'?'check-circle':type==='error'?'exclamation-circle':type==='info'?'info-circle':'exclamation-triangle'}"></i> ${message}`;
    container.appendChild(toast);
    setTimeout(()=>toast.remove(),5000);
}

async function loadDashboardStats(){
    const numbers=await fetch('/api/user/my_numbers').then(r=>r.json());
    const sms=await fetch('/api/user/my_sms').then(r=>r.json());
    const payments=await fetch('/api/user/payments').then(r=>r.json());
    const dailyLimit=await fetch('/api/user/daily_limit').then(r=>r.json());

    let totalNumbers=0;for(const nums of Object.values(numbers.numbers||{})){totalNumbers+=nums.length}
    let totalSMS=0;for(const msgs of Object.values(sms.sms||{})){totalSMS+=msgs.length}
    let totalSpent=0;
    for(const p of payments.payments||[]){if(p.type==='sms'||p.type==='purchase'){totalSpent+=p.cost||0}}

    document.getElementById('totalMyNumbers').textContent=totalNumbers;
    document.getElementById('totalMySMS').textContent=totalSMS;
    document.getElementById('totalMyFiles').textContent=Object.keys(numbers.numbers||{}).length;
    document.getElementById('totalSpent').textContent=totalSpent.toFixed(2);

    const remaining = dailyLimit.daily_remaining || 2000;
    const limitEl = document.getElementById('dailyLimitRemaining');
    limitEl.textContent = remaining;
    if(remaining < 100) limitEl.style.color = 'var(--destructive)';
    else if(remaining < 500) limitEl.style.color = 'var(--warning)';
}

async function loadAvailableFiles(){
    const response=await fetch('/api/user/available_numbers');
    const data=await response.json();
    const container=document.getElementById('availableFiles');
    container.innerHTML='';
    if(Object.keys(data.files||{}).length===0){container.innerHTML='<div class="form-container" style="text-align:center"><p style="color:var(--muted)">لا توجد Fileات متاحة حالياً</p></div>';return}
    let html='<div class="files-grid">';
    for(const[name,info]of Object.entries(data.files||{})){
        html+=`<div class="file-card"><h4><i class="fas fa-file-alt"></i> ${name}</h4><div class="info"><span>Available number : ${info.numbers?.length||0}</span></div><div class="cost">Coast: $${info.cost||0} For each number</div><div class="qty-grid"><button class="qty-btn" onclick="requestNumbers('${name}',5)">5</button><button class="qty-btn" onclick="requestNumbers('${name}',15)">15</button><button class="qty-btn" onclick="requestNumbers('${name}',30)">30</button><button class="qty-btn" onclick="requestNumbers('${name}',50)">50</button><button class="qty-btn" onclick="requestNumbers('${name}',75)">75</button><button class="qty-btn" onclick="requestNumbers('${name}',100)">100</button><button class="qty-btn" onclick="requestNumbers('${name}',150)">150</button><button class="qty-btn" onclick="requestNumbers('${name}',200)">200</button></div></div>`;
    }
    html+='</div>';
    container.innerHTML=html;
}

async function requestNumbers(filename,count){
    const response=await fetch('/api/user/request_numbers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename,count})});
    const data=await response.json();
    if(data.success){
        showToast(`تم إضافة ${data.assigned.length} رقم - Coast: $${data.cost} - متبقي يومي: ${data.daily_remaining}`, 'success');
        loadAvailableFiles();
        loadDashboardStats();
    }
    else{showToast(data.message,'error')}
}

async function loadMyNumbers(){
    const response=await fetch('/api/user/my_numbers');
    const data=await response.json();
    const container=document.getElementById('myNumbersList');
    container.innerHTML='';
    const costs=data.costs||{};
    for(const[filename,numbers]of Object.entries(data.numbers||{})){
        const costPerNumber=costs[filename]||0;
        container.innerHTML+=`<div class="form-container"><h4 style="color:var(--primary);margin-bottom:12px"><i class="fas fa-file"></i> ${filename}</h4><p style="color:var(--success);margin-bottom:10px;font-size:13px">Cost per number: $${costPerNumber.toFixed(2)}</p><div class="table-wrapper"><table><thead><tr><th>#</th><th>الرقم</th><th>Coast</th></tr></thead><tbody>${numbers.map((num,i)=>`<tr><td>${i+1}</td><td class="text-mono text-primary">${num}</td><td class="text-success">$${costPerNumber.toFixed(2)}</td></tr>`).join('')}</tbody></table></div></div>`;
    }
}

function showDeleteMyNumbers(){
    const filename=prompt('Enter the name of the file you want to delete:');
    if(filename){fetch('/api/user/delete_my_numbers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename})}).then(()=>{showToast('تم الdelete');loadMyNumbers()})}
}

async function loadMyRange(){
    const response=await fetch('/api/user/my_range');
    const data=await response.json();
    const container=document.getElementById('myRangeList');
    container.innerHTML='';
    for(const[filename,count]of Object.entries(data.range||{})){container.innerHTML+=`<div class="stat-card" style="margin-bottom:12px"><span class="icon" style="color:var(--primary)">📁</span><div class="number">${count}</div><div class="label">${filename}</div></div>`}
}

async function loadMyFiles(){
    const response=await fetch('/api/user/my_numbers');
    const data=await response.json();
    const container=document.getElementById('myFilesList');
    container.innerHTML='';
    for(const filename of Object.keys(data.numbers||{})){container.innerHTML+=`<div class="file-card"><h4><i class="fas fa-file-alt"></i> ${filename}</h4><button class="btn btn-primary" onclick="downloadFile('${filename}')" style="margin-top:12px"><i class="fas fa-download"></i> Download file</button></div>`}
}

function showDeleteMyFiles(){
    const filename=prompt('Enter the name of the file you want to delete:');
    if(filename){fetch('/api/user/delete_my_numbers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename})}).then(()=>{showToast('File deleted');loadMyFiles()})}
}

async function downloadFile(filename){
    const response=await fetch('/api/user/download_file',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename})});
    if(response.ok){const blob=await response.blob();const url=window.URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=filename+'.txt';a.click();showToast('Loaded')}
}

async function loadMySMS(){
    const response=await fetch('/api/user/my_sms');
    const data=await response.json();
    const container=document.getElementById('smsList');
    container.innerHTML='';
    let count=0;
    allSMSCache = []; // Clear search cache
    console.log('SMS Data:', data);

    if(!data.sms || Object.keys(data.sms).length === 0){
        container.innerHTML='<div class="form-container" style="text-align:center"><p style="color:var(--muted)">No massage</p></div>';
        return;
    }

    let purchasedHTML = '<h4 style="color:var(--primary);margin:16px 0 12px"><i class="fas fa-shopping-cart"></i> رسائل My Numbers </h4>';
    let apiHTML = '<h4 style="color:var(--warning);margin:24px 0 12px"><i class="fas fa-globe"></i> All messages </h4>';
    let purchasedCount = 0;
    let apiCount = 0;

    for(const[phone,messages]of Object.entries(data.sms||{})){
        if(phone.startsWith('test_')) continue;
        if(!Array.isArray(messages)) continue;

        const sortedMessages = [...messages].sort((a,b) => new Date(b.time) - new Date(a.time));
        const isApiGlobal = phone.startsWith('api_');
        const displayPhone = isApiGlobal ? phone.replace('api_', '') : phone;

        for(const sms of sortedMessages){
            count++;
            const msgText = sms.message || sms.text || sms.body || 'No message';
            const apiName = sms.api || 'Unknown';
            const timeStr = sms.time ? new Date(sms.time).toLocaleString('ar') : '-';
            const sourceBadge = sms.source === 'api_global' ? '<span style="background:var(--warning);color:white;padding:2px 8px;border-radius:10px;font-size:10px;margin-right:8px">API</span>' : '';

            // Add to cache for search
            allSMSCache.push({
                phone: displayPhone,
                message: msgText,
                api: apiName,
                time: sms.time,
                source: sms.source,
                isApiGlobal: isApiGlobal
            });

            const cardHTML = `<div class="sms-card ${isApiGlobal ? 'api-global' : ''}">
                <div class="phone"><i class="fas fa-phone"></i> ${displayPhone} ${sourceBadge}</div>
                <div class="message">${msgText}</div>
                <div class="meta">
                    <span class="api-badge">${apiName}</span>
                    <span>${timeStr}</span>
                </div>
            </div>`;

            if(isApiGlobal){
                apiHTML += cardHTML;
                apiCount++;
            } else {
                purchasedHTML += cardHTML;
                purchasedCount++;
            }
        }
    }

    let finalHTML = '';
    if(purchasedCount > 0) finalHTML += purchasedHTML;
    if(apiCount > 0) finalHTML += apiHTML;

    container.innerHTML = finalHTML || '<div class="form-container" style="text-align:center"><p style="color:var(--muted)">No massage</p></div>';
    console.log(`SMS Loaded: ${purchasedCount} purchased, ${apiCount} API global, Total cached: ${allSMSCache.length}`);
}

async function refreshSMS(){
    const btn=document.getElementById('refreshSMSBtn');
    btn.querySelector('i').classList.add('fa-spin');
    btn.disabled=true;

    // Force fetch from server
    const response = await fetch('/api/user/my_sms');
    const data = await response.json();
    console.log('Manual refresh - SMS data:', data);

    await loadMySMS();

    const totalMessages = Object.values(data.sms || {}).reduce((acc, arr) => acc + (Array.isArray(arr) ? arr.length : 0), 0);
    showToast(`تم Messages update (${totalMessages} رسالة)`, totalMessages > 0 ? 'success' : 'info');

    btn.querySelector('i').classList.remove('fa-spin');
    btn.disabled=false;
}

async function loadTestNumbers(){
    const response=await fetch('/api/user/test_numbers');
    const data=await response.json();
    const container=document.getElementById('testNumbersList');
    container.innerHTML='';
    for(const[filename,numbers]of Object.entries(data.files||{})){container.innerHTML+=`<div class="form-container"><h4 style="color:var(--warning);margin-bottom:12px"><i class="fas fa-vial"></i> ${filename}</h4><div class="table-wrapper"><table><thead><tr><th>#</th><th>الرقم</th></tr></thead><tbody>${numbers.map((num,i)=>`<tr><td>${i+1}</td><td class="text-mono">${num}</td></tr>`).join('')}</tbody></table></div></div>`}
}

async function loadTestSMS(){
    // Fetch both test SMS and regular user SMS
    const [testResponse, mySmsResponse] = await Promise.all([
        fetch('/api/user/test_sms'),
        fetch('/api/user/my_sms')
    ]);
    const testData = await testResponse.json();
    const mySmsData = await mySmsResponse.json();
    const container = document.getElementById('testSMSList');
    container.innerHTML='';

    // ====== SECTION 1: User's Regular SMS (from purchased numbers) ======
    let mySMSHTML = '<h4 style="color:var(--primary);margin:16px 0 12px"><i class="fas fa-envelope"></i> My massage  (My Numbers )</h4>';
    let mySMSCount = 0;

    for(const[phone,messages]of Object.entries(mySmsData.sms||{})){
        if(phone.startsWith('test_') || phone.startsWith('api_test_')) continue;
        if(!Array.isArray(messages)) continue;
        const isApiGlobal = phone.startsWith('api_');
        const displayPhone = isApiGlobal ? phone.replace('api_', '') : phone;

        const sortedMessages = [...messages].sort((a,b) => new Date(b.time) - new Date(a.time));
        for(const sms of sortedMessages){
            const msgText = sms.message || sms.text || sms.body || 'No message';
            const apiName = sms.api || 'Unknown';
            const timeStr = sms.time ? new Date(sms.time).toLocaleString('ar') : '-';
            const sourceBadge = sms.source === 'api_global' ? '<span style="background:var(--warning);color:white;padding:2px 8px;border-radius:10px;font-size:10px;margin-right:8px">API</span>' : '';

            mySMSHTML += `<div class="sms-card ${isApiGlobal ? 'api-global' : ''}">
                <div class="phone"><i class="fas fa-phone"></i> ${displayPhone} ${sourceBadge}</div>
                <div class="message">${msgText}</div>
                <div class="meta">
                    <span class="api-badge">${apiName}</span>
                    <span>${timeStr}</span>
                </div>
            </div>`;
            mySMSCount++;
        }
    }

    // ====== SECTION 2: Test SMS (masked numbers) ======
    let testHTML = '<h4 style="color:var(--warning);margin:24px 0 12px"><i class="fas fa-vial"></i> Sms test (مخفية)</h4>';
    let apiTestHTML = '<h4 style="color:var(--success);margin:24px 0 12px"><i class="fas fa-globe"></i> رسائل API تجريبية</h4>';
    let testCount = 0;
    let apiTestCount = 0;

    for(const[key,messages]of Object.entries(testData.sms||{})){
        if(!Array.isArray(messages)) continue;
        const isApiTest = key.startsWith('api_test_');

        for(const sms of messages){
            const displayNum = sms.masked_number || sms.number;
            const timeStr = sms.time ? new Date(sms.time).toLocaleString('ar') : '-';
            const sourceBadge = sms.source === 'api_test_global' ? '<span style="background:var(--success);color:white;padding:2px 8px;border-radius:10px;font-size:10px;margin-right:8px">API</span>' : '';

            const cardHTML = `<div class="sms-card test ${isApiTest ? 'api-test-global' : ''}">
                <div class="phone"><i class="fas fa-vial"></i> ${displayNum} ${sourceBadge}</div>
                <div class="message">${sms.message}</div>
                <div class="meta">
                    <span class="api-badge">${sms.api}</span>
                    <span>${timeStr}</span>
                </div>
            </div>`;

            if(isApiTest){
                apiTestHTML += cardHTML;
                apiTestCount++;
            } else {
                testHTML += cardHTML;
                testCount++;
            }
        }
    }

    // Build final HTML
    let finalHTML = '';
    if(mySMSCount > 0) finalHTML += mySMSHTML;
    if(testCount > 0) finalHTML += testHTML;
    if(apiTestCount > 0) finalHTML += apiTestHTML;

    container.innerHTML = finalHTML || '<div class="form-container" style="text-align:center"><p style="color:var(--muted)">لا توجد رسائل</p></div>';
}

async function loadNotifications(){
    const response=await fetch('/api/user/notifications');
    const data=await response.json();
    const container=document.getElementById('notificationsList');
    container.innerHTML='';
    const notifs=data.notifications||[];
    if(notifs.length===0){container.innerHTML='<div class="form-container" style="text-align:center"><p style="color:var(--muted)">لا توجد إشعارات</p></div>';return;}
    for(const notif of notifs.slice().reverse()){container.innerHTML+=`<div class="notification-panel ${notif.read?'':'unread'}"><div class="header"><span class="type">${notif.type}</span><span class="time">${new Date(notif.time).toLocaleString('ar')}</span></div><p>${notif.message}</p></div>`;}
    await fetch('/api/user/mark_read',{method:'POST'});
    updateNotificationBadge();
}

async function updateNotificationBadge(){
    const response=await fetch('/api/user/notifications');
    const data=await response.json();
    const unread=(data.notifications||[]).filter(n=>!n.read).length;
    const badge=document.getElementById('notifBadge');
    badge.style.display=unread>0?'block':'none';
}

async function loadPayments(){
    const response=await fetch('/api/user/payments');
    const data=await response.json();
    const tbody=document.getElementById('paymentsTable');
    tbody.innerHTML='';
    for(const payment of(data.payments||[]).slice().reverse()){
        const typeLabel=payment.type==='sms'?'رسالة SMS':'شراء أرقام';
        const detail=payment.type==='sms'?`رقم: ${payment.number||'-'} (File: ${payment.file||'-'})`:`File: ${payment.file||'-'} (${payment.count||0} رقم)`;
        tbody.innerHTML+=`<tr><td><span class="api-badge">${typeLabel}</span></td><td>${detail}</td><td class="text-success">$${payment.cost?.toFixed(2)||0}</td><td class="text-muted">${new Date(payment.time).toLocaleDateString('ar')}</td></tr>`
    }
}

async function updateAccount(){
    const password=document.getElementById('newPassword').value;
    const phone=document.getElementById('newPhone').value;
    const response=await fetch('/api/user/update_account',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password,phone})});
    const data=await response.json();
    if(data.success){showToast('تم تحديث الحساب');document.getElementById('newPassword').value=''}
}

async function debugSMS(){
    const response = await fetch('/api/debug/sms_data');
    const data = await response.json();
    console.log('Debug SMS Data:', data);

    const debugDiv = document.getElementById('smsDebugInfo');
    debugDiv.style.display = 'block';
    debugDiv.innerHTML = `
        <strong>معلومات التشخيص:</strong><br>
        المستخدم: ${data.username}<br>
        مفاتيح SMS: ${data.all_sms_keys.join(', ')}<br>
        أرقامك: ${JSON.stringify(data.user_numbers)}<br>
        رسائلك: ${JSON.stringify(data.user_sms)}
    `;
    showToast('تم طباعة البيانات في Console (F12)', 'info');
}

let allSMSCache = []; // Store all SMS for search

function searchSMS(){
    const query = document.getElementById('smsSearchInput').value.trim();
    const container = document.getElementById('smsList');
    const statsDiv = document.getElementById('smsSearchStats');

    if(!query){
        // Reload all SMS
        loadMySMS();
        statsDiv.textContent = '';
        return;
    }

    // Filter cached SMS
    const filtered = allSMSCache.filter(sms => {
        const phone = (sms.phone || '').toLowerCase();
        const message = (sms.message || '').toLowerCase();
        const q = query.toLowerCase();
        return phone.includes(q) || message.includes(q);
    });

    // Render filtered results
    let html = `<h4 style="color:var(--primary);margin:16px 0 12px"><i class="fas fa-search"></i> نتائج البحث: "${query}"</h4>`;

    if(filtered.length === 0){
        html += '<div class="form-container" style="text-align:center"><p style="color:var(--muted)">لا توجد نتائج للبحث</p></div>';
    } else {
        for(const sms of filtered){
            const timeStr = sms.time ? new Date(sms.time).toLocaleString('ar') : '-';
            const sourceBadge = sms.source === 'api_global' ? '<span style="background:var(--warning);color:white;padding:2px 8px;border-radius:10px;font-size:10px;margin-right:8px">API</span>' : '';

            html += `<div class="sms-card ${sms.isApiGlobal ? 'api-global' : ''}">
                <div class="phone"><i class="fas fa-phone"></i> ${sms.phone} ${sourceBadge}</div>
                <div class="message">${sms.message}</div>
                <div class="meta">
                    <span class="api-badge">${sms.api}</span>
                    <span>${timeStr}</span>
                </div>
            </div>`;
        }
    }

    container.innerHTML = html;
    statsDiv.textContent = `تم العثور على ${filtered.length} رسالة`;
}

function clearSMSSearch(){
    document.getElementById('smsSearchInput').value = '';
    document.getElementById('smsSearchStats').textContent = '';
    loadMySMS();
}

function logout(){window.location.href='/logout'}
loadDashboardStats();
updateNotificationBadge();
setInterval(()=>{if(document.getElementById('mySMS').classList.contains('active')){loadMySMS()}if(document.getElementById('testSMS').classList.contains('active')){loadTestSMS()}updateNotificationBadge()},5000); // Check every 5 seconds
</script>
</body>
</html>
"""
ADMIN_HTML = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>X PANEL - Admin</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
:root{--primary:#1E40AF;--primary-light:#3B82F6;--primary-dark:#1E3A8A;--background:#FFFFFF;--foreground:#1F2937;--secondary:#F3F4F6;--border:#E5E7EB;--muted:#6B7280;--destructive:#DC2626;--success:#10B981;--warning:#F59E0B;--card-bg:#FFFFFF;--sidebar-width:260px}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background-color:#F9FAFB;color:var(--foreground);line-height:1.6;min-height:100vh}
h1,h2,h3,h4,h5,h6{font-family:'Poppins',sans-serif;font-weight:600}

/* ===== SIDEBAR ===== */
.sidebar{position:fixed;right:0;top:0;width:var(--sidebar-width);height:100vh;background:white;border-left:1px solid var(--border);padding:20px 0;overflow-y:auto;z-index:100;box-shadow:-2px 0 10px rgba(0,0,0,0.05)}
.sidebar-logo{text-align:center;margin-bottom:24px;padding:0 20px 20px;border-bottom:1px solid var(--border)}
.sidebar-logo h1{font-family:'Poppins',sans-serif;font-size:1.4rem;font-weight:700;color:var(--primary);margin-bottom:4px}
.sidebar-logo p{color:var(--muted);font-size:0.75rem;font-weight:500}
.nav-section{margin-top:8px;padding:0 12px}
.nav-section-title{font-size:0.7rem;text-transform:uppercase;letter-spacing:1px;color:var(--muted);margin-bottom:8px;padding:0 8px;font-weight:600}
.nav-item{display:flex;align-items:center;padding:10px 14px;margin-bottom:4px;border-radius:8px;cursor:pointer;transition:all 0.2s ease;border:none;background:none;width:100%;text-align:right;font-family:'Inter',sans-serif;font-size:0.85rem;color:var(--foreground);gap:10px}
.nav-item:hover{background:var(--secondary);color:var(--primary)}
.nav-item.active{background:var(--primary);color:white}
.nav-item.active i{color:white}
.nav-item i{font-size:1rem;width:20px;text-align:center;color:var(--muted);transition:color 0.2s}
.nav-item:hover i{color:var(--primary)}
.nav-item.active:hover{background:var(--primary-dark)}
.nav-item.active:hover i{color:white}

/* ===== MAIN CONTENT ===== */
.main-content{margin-right:var(--sidebar-width);min-height:100vh;display:flex;flex-direction:column}
.page-content{flex:1;max-width:1400px;margin:0 auto;padding:24px 32px;width:100%}

/* ===== HEADER ===== */
.header{background-color:white;border-bottom:1px solid var(--border);box-shadow:0 1px 3px rgba(0,0,0,0.05);padding:14px 32px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:40}
.header-left h2{font-size:20px;margin-bottom:2px;color:var(--foreground)}
.header-left p{font-size:13px;color:var(--muted)}
.header-right{display:flex;align-items:center;gap:14px}
.header-icon-btn{position:relative;background:none;border:none;cursor:pointer;color:var(--muted);transition:all 0.2s ease;padding:8px;border-radius:8px;font-size:18px}
.header-icon-btn:hover{color:var(--primary);background-color:var(--secondary)}
.notification-badge{position:absolute;top:4px;right:4px;width:8px;height:8px;background-color:var(--destructive);border-radius:50%}
.divider{width:1px;height:24px;background-color:var(--border)}
.user-profile{display:flex;align-items:center;gap:10px;cursor:pointer}
.user-avatar{width:34px;height:34px;background-color:var(--primary);border-radius:50%;display:flex;align-items:center;justify-content:center;color:white;font-size:16px;font-weight:600}
.user-name{font-size:14px;font-weight:500}
.logout-btn{background:var(--destructive);color:#fff;border:none;padding:8px 18px;border-radius:6px;cursor:pointer;font-family:'Inter',sans-serif;font-weight:600;font-size:13px;transition:all 0.2s ease;display:inline-flex;align-items:center;gap:6px}
.logout-btn:hover{background:#B91C1C;transform:translateY(-1px)}

/* ===== SECTIONS ===== */
.page-section{margin-bottom:20px}
.section-title{font-size:18px;font-weight:600;margin-bottom:16px;color:var(--foreground);display:flex;align-items:center;gap:10px}
.section-title::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--border),transparent)}
.content-section{display:none;animation:fadeIn 0.3s ease}
.content-section.active{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}

/* ===== BUTTONS ===== */
.action-buttons{display:flex;gap:10px;margin-bottom:20px;flex-wrap:wrap}
.btn{padding:10px 18px;border-radius:6px;border:none;cursor:pointer;font-size:13px;font-weight:500;transition:all 0.2s ease;display:inline-flex;align-items:center;gap:8px;font-family:'Inter',sans-serif}
.btn-primary{background-color:var(--primary);color:white}
.btn-primary:hover{background-color:var(--primary-light);transform:translateY(-1px);box-shadow:0 4px 12px rgba(30,64,175,0.2)}
.btn-outline{background-color:white;color:var(--foreground);border:1px solid var(--border)}
.btn-outline:hover{background-color:var(--secondary);border-color:var(--primary);color:var(--primary)}
.btn-danger{background-color:var(--destructive);color:white}
.btn-danger:hover{background-color:#B91C1C;transform:translateY(-1px)}
.btn-success{background-color:var(--success);color:white}
.btn-success:hover{background-color:#059669;transform:translateY(-1px)}
.btn-sm{padding:6px 12px;font-size:12px}

/* ===== FORMS ===== */
.form-container{background:white;border:1px solid var(--border);border-radius:8px;padding:24px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.05)}
.form-group{margin-bottom:16px}
.form-group label{display:block;margin-bottom:6px;font-size:13px;font-weight:500;color:var(--foreground)}
.form-group input,.form-group select{width:100%;padding:10px 14px;border:1px solid var(--border);border-radius:6px;font-size:13px;background-color:white;color:var(--foreground);font-family:'Inter',sans-serif;transition:all 0.2s ease}
.form-group input:focus,.form-group select:focus{outline:none;border-color:var(--primary);box-shadow:0 0 0 3px rgba(30,64,175,0.1)}
.form-group input::placeholder{color:var(--muted)}

/* ===== TABLE ===== */
.table-wrapper{background-color:white;border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.05)}
.table-controls{display:flex;align-items:center;justify-content:space-between;padding:14px 20px;background-color:var(--secondary);border-bottom:1px solid var(--border);flex-wrap:wrap;gap:12px}
table{width:100%;border-collapse:collapse}
thead{background-color:var(--secondary)}
th{padding:12px 16px;text-align:right;font-size:12px;font-weight:600;color:var(--foreground);border-bottom:1px solid var(--border);white-space:nowrap}
td{padding:12px 16px;font-size:13px;border-bottom:1px solid var(--border)}
tbody tr{transition:background-color 0.2s ease}
tbody tr:hover{background-color:var(--secondary)}
tbody tr:nth-child(even){background-color:rgba(243,244,246,0.5)}
.status-badge{padding:4px 10px;border-radius:12px;font-size:11px;font-weight:600;display:inline-block}
.status-active{background:rgba(16,185,129,0.1);color:#047857;border:1px solid var(--success)}
.status-pending{background:rgba(245,158,11,0.1);color:#B45309;border:1px solid var(--warning)}
.status-banned{background:rgba(220,38,38,0.1);color:#B91C1C;border:1px solid var(--destructive)}
.status-admin{background:rgba(59,130,246,0.1);color:var(--primary);border:1px solid var(--primary-light)}
.text-primary{color:var(--primary);font-weight:500}
.text-muted{color:var(--muted)}

/* ===== TOAST ===== */
.toast-container{position:fixed;top:20px;left:20px;z-index:9999;display:flex;flex-direction:column;gap:10px}
.toast{background:white;border-right:4px solid var(--success);border-radius:8px;padding:14px 18px;min-width:300px;box-shadow:0 10px 30px rgba(0,0,0,0.15);animation:toastIn 0.3s ease;font-size:13px;display:flex;align-items:center;gap:10px}
.toast.error{border-right-color:var(--destructive)}
@keyframes toastIn{from{transform:translateX(-100%);opacity:0}to{transform:translateX(0);opacity:1}}

/* ===== FOOTER ===== */
.footer{background-color:white;border-top:1px solid var(--border);padding:16px 32px;text-align:center;font-size:12px;color:var(--muted);margin-top:auto}

/* ===== RESPONSIVE ===== */
@media(max-width:768px){
    .sidebar{width:100%;transform:translateX(100%);transition:transform 0.3s ease}
    .sidebar.open{transform:translateX(0)}
    .main-content{margin-right:0}
    .header{flex-direction:column;align-items:flex-start;gap:10px;padding:12px 20px}
    .header-right{width:100%;justify-content:flex-start}
    .page-content{padding:16px 20px}
    .action-buttons{flex-direction:column}
    .btn{width:100%;justify-content:center}
    table{font-size:12px}
    th,td{padding:10px 12px}
}
@media(max-width:640px){
    .header-left h2{font-size:18px}
    .section-title{font-size:16px}
    .user-name{display:none}
}
</style>
</head>
<body>

<!-- SIDEBAR -->
<div class="sidebar">
    <div class="sidebar-logo">
        <img src="https://i.ibb.co/CKXS2Lcg/1000146872.png" alt="X PANEL" style="width:80px;height:auto;margin-bottom:8px;border-radius:8px;">
        <h1>X PANEL</h1>
        <p>ADMIN PANEL</p>
    </div>

    <div class="nav-section">
        <div class="nav-section-title">main Dashboard</div>
        <button class="nav-item active" onclick="showSection('dashboard',this)">
            <i class="fas fa-home"></i> Dashboard
        </button>
    </div>

    <div class="nav-section">
        <div class="nav-section-title">الحسابات</div>
        <button class="nav-item" onclick="showSection('createAccount',this)">
            <i class="fas fa-user-plus"></i> Create account 
        </button>
        <button class="nav-item" onclick="showSection('deleteAccount',this)">
            <i class="fas fa-user-times"></i> delete حساب
        </button>
        <button class="nav-item" onclick="showSection('usersList',this)">
            <i class="fas fa-users"></i> المستخدمين
        </button>
    </div>
</div>

<!-- MAIN CONTENT -->
<div class="main-content">
    <!-- HEADER -->
    <header class="header">
        <div class="header-left">
            <h2><i class="fas fa-user-shield" style="color:var(--warning)"></i> لوحة الأدمن</h2>
            <p>إدارة حسابات المستخدمين</p>
        </div>
        <div class="header-right">
            <button class="header-icon-btn" title="الإعدادات"><i class="fas fa-cog"></i></button>
            <div class="divider"></div>
            <div class="user-profile">
                <div class="user-avatar">A</div>
                <span class="user-name">Admin</span>
            </div>
            <button class="logout-btn" onclick="logout()"><i class="fas fa-sign-out-alt"></i> Logout</button>
        </div>
    </header>

    <!-- PAGE CONTENT -->
    <div class="page-content">
        <!-- DASHBOARD -->
        <div class="content-section active" id="dashboard">
            <div class="form-container" style="text-align:center;padding:48px">
                <i class="fas fa-user-shield" style="font-size:4rem;color:var(--warning);margin-bottom:20px"></i>
                <h3 style="color:var(--primary);margin-bottom:12px">مرحباً بك في لوحة الأدمن</h3>
                <p style="color:var(--muted)">يمكنك إنشاء وdelete حسابات المستخدمين وإدارة النظام</p>
            </div>
        </div>

        <!-- CREATE ACCOUNT -->
        <div class="content-section" id="createAccount">
            <h3 class="section-title"><i class="fas fa-user-plus"></i> Create account  مستخدم</h3>
            <div class="form-container">
                <div class="form-group"><label>User</label><input type="text" id="newUsername" placeholder="User"></div>
                <div class="form-group"><label>Password</label><input type="password" id="newPassword" placeholder="Password"></div>
                <div class="form-group"><label>phone number </label><input type="tel" id="newPhone" placeholder="phone number "></div>
                <button class="btn btn-primary" onclick="createAccount()"><i class="fas fa-plus"></i> إنشاء الحساب</button>
            </div>
        </div>

        <!-- DELETE ACCOUNT -->
        <div class="content-section" id="deleteAccount">
            <h3 class="section-title"><i class="fas fa-user-times"></i> delete حساب مستخدم</h3>
            <div class="form-container">
                <div class="form-group"><label>اختر الحساب</label><select id="deleteUserSelect"></select></div>
                <button class="btn btn-danger" onclick="deleteAccount()"><i class="fas fa-trash"></i> delete الحساب</button>
            </div>
        </div>

        <!-- USERS LIST -->
        <div class="content-section" id="usersList">
            <h3 class="section-title"><i class="fas fa-users"></i> قائمة المستخدمين</h3>
            <div class="table-wrapper">
                <div class="table-controls">
                    <div class="table-show"><span>عرض</span><select><option>10</option><option>25</option><option>50</option></select><span>إدخالات</span></div>
                </div>
                <table>
                    <thead><tr><th>المستخدم</th><th>الدور</th><th>الحالة</th><th>الحد</th><th>Data</th></tr></thead>
                    <tbody id="usersTable"></tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- FOOTER -->
    <footer class="footer">
        <p>© 2026 X PANEL OTP System. جميع الحقوق محفوظة.</p>
    </footer>
</div>

<div class="toast-container" id="toastContainer"></div>

<script>
function showSection(sectionId,btn){
    document.querySelectorAll('.content-section').forEach(s=>s.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
    document.getElementById(sectionId).classList.add('active');
    if(btn) btn.classList.add('active');
    if(sectionId==='deleteAccount')loadUsersForDelete();
    if(sectionId==='usersList')loadUsersList();
}

function showToast(message,type='success'){
    const container=document.getElementById('toastContainer');
    const toast=document.createElement('div');
    toast.className='toast '+(type==='error'?'error':'');
    toast.innerHTML=`<i class="fas fa-${type==='success'?'check-circle':'exclamation-circle'}"></i> ${message}`;
    container.appendChild(toast);
    setTimeout(()=>toast.remove(),5000);
}

async function createAccount(){
    const username=document.getElementById('newUsername').value;
    const password=document.getElementById('newPassword').value;
    const phone=document.getElementById('newPhone').value;
    const response=await fetch('/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password,phone})});
    const data=await response.json();
    if(data.success){showToast('تم إنشاء الحساب');document.getElementById('newUsername').value='';document.getElementById('newPassword').value='';document.getElementById('newPhone').value='';}
    else{showToast(data.message,'error')}
}

async function loadUsersForDelete(){
    const response=await fetch('/api/owner/accounts');
    const data=await response.json();
    const select=document.getElementById('deleteUserSelect');
    select.innerHTML='';
    for(const username of Object.keys(data.users||{})){if(username!=='mohaymen'){select.innerHTML+=`<option value="${username}">${username}</option>`}}
}

async function loadUsersList(){
    const response=await fetch('/api/owner/accounts');
    const data=await response.json();
    const tbody=document.getElementById('usersTable');
    tbody.innerHTML='';
    for(const[username,user]of Object.entries(data.users||{})){
        if(username==='mohaymen')continue;
        const statusClass=user.status==='active'?'status-active':user.status==='pending'?'status-pending':'status-banned';
        const roleClass=user.role==='admin'?'status-admin':'';
        tbody.innerHTML+=`<tr><td class="text-primary">${username}</td><td><span class="status-badge ${roleClass}">${user.role}</span></td><td><span class="status-badge ${statusClass}">${user.status}</span></td><td>${user.limit||0}</td><td class="text-muted">${new Date(user.created_at).toLocaleDateString('ar')}</td></tr>`;
    }
}

async function deleteAccount(){
    const username=document.getElementById('deleteUserSelect').value;
    if(!username)return;
    showToast('تم delete '+username);
    loadUsersForDelete();
}

function logout(){window.location.href='/logout'}
</script>
</body>
</html>
"""


# FORCE SMS CHECK ENDPOINT (for manual testing)
@app.route('/api/force_check_sms')
@login_required
def force_check_sms():
    """Manually trigger SMS processing"""
    try:
        print(f"[Force Check] Triggered by user: {session['username']}")

        # First fetch raw SMS from APIs
        raw_sms = fetch_sms_from_apis()
        print(f"[Force Check] Fetched {len(raw_sms)} raw SMS from APIs")

        # Then process them
        process_new_sms()

        # Check results
        sms_data = load_data(SMS_FILE)
        username = session['username']
        user_sms = sms_data.get(username, {})
        total = sum(len(msgs) for msgs in user_sms.values() if isinstance(msgs, list))

        return jsonify({
            'success': True, 
            'message': f'SMS check completed. You have {total} messages.',
            'sms_count': total,
            'raw_fetched': len(raw_sms),
            'user_sms_keys': list(user_sms.keys())
        })
    except Exception as e:
        import traceback
        print(f"[Force Check Error] {str(e)}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})

# MAIN ENTRY POIN
if __name__ == '__main__':
    start_sms_monitoring()
    print("""
    ╔══════════════════════════════════════╗
    ║     X PANEL OTP SYSTEM - STARTED     ║
    ╠══════════════════════════════════════╣
    ║  Owner Login: mohaymen / mohaymen    ║
    ║  URL: http://localhost:5000          ║
    ║                                      ║
    ║  APIs Monitoring: 4 APIs active      ║
    ║  SMS Check Interval: 15 seconds      ║
    ╚══════════════════════════════════════╝
    """)
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
    
