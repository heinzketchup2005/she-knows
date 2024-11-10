from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from pymongo import MongoClient
import random
import time
import secrets
from authlib.integrations.flask_client import OAuth
from functools import wraps
from bson import ObjectId
from datetime import datetime


# Database setup
client = MongoClient("mongodb+srv://scavenger_user:hunter123456@cluster01.ct2bj.mongodb.net/?retryWrites=true&w=majority&appName=Cluster01")
db = client["scavenger_hunt"]
hunts_collection = db["hunts"]
players_collection = db["players"]

events_collection = db["events"]

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # Generates a random 32-character secret key

# Initialize OAuth
oauth = OAuth(app)

# Google OAuth configuration with server_metadata_url
google = oauth.register(
    name='google',
    client_id='738965192863-5q8frhuc5umhp0ek00p3ih9j2dp6rb4m.apps.googleusercontent.com',
    client_secret='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',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid profile email'}
)



def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            session['next_url'] = request.url
            return redirect(url_for('login_google'))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/join-hunt", methods=["POST"])
def join_hunt():
    hunt_id = int(request.form["idd"])
    name = request.form["name"]
    
    # Store in session for use after OAuth
    session['pending_hunt_id'] = hunt_id
    session['pending_player_name'] = name
    
    if 'user' not in session:
        return redirect(url_for('login_google'))
    
    return process_join_hunt(hunt_id, name)

@app.route('/login/google')
def login_google():
    # Generate and store both state and nonce
    session['oauth_state'] = secrets.token_urlsafe(16)
    session['oauth_nonce'] = secrets.token_urlsafe(16)
    
    if request.referrer:
        session['oauth_referrer'] = request.referrer

    redirect_uri = url_for('google_callback', _external=True)
    
    return google.authorize_redirect(
        redirect_uri=redirect_uri,
        state=session['oauth_state'],
        nonce=session['oauth_nonce']  # Pass nonce to authorization request
    )

@app.route('/google/callback')
def google_callback():
    try:
        # Verify state matches
        if request.args.get('state') != session.pop('oauth_state', None):
            raise ValueError("State mismatch")
        
        # Get the nonce from session
        nonce = session.pop('oauth_nonce', None)
        if not nonce:
            raise ValueError("Nonce missing")
        
        # Get token and user info with nonce verification
        token = google.authorize_access_token()
        user_info = google.parse_id_token(token, nonce=nonce)  # Pass nonce for verification
        session['user'] = user_info

        # Process pending hunt join if exists
        hunt_id = session.pop('pending_hunt_id', None)
        player_name = session.pop('pending_player_name', None)
        
        if hunt_id is not None and player_name is not None:
            return process_join_hunt(hunt_id, player_name)
        
        # Check for stored next URL
        next_url = session.pop('next_url', None)
        if next_url:
            return redirect(next_url)
            
        return redirect(url_for('profile'))

    except Exception as e:
        # Clear all oauth related session data
        for key in ['oauth_state', 'oauth_nonce', 'pending_hunt_id', 
                   'pending_player_name', 'next_url']:
            session.pop(key, None)
        
        return render_template('error.html', 
                             error=f"Authentication failed: {str(e)}. Please try again.")



def process_join_hunt(hunt_id, name):
    hunt = hunts_collection.find_one({"_id": hunt_id})
    if hunt:
        # Check for existing player
        existing_player = players_collection.find_one({
            "hunt_id": hunt_id,
            "user_email": session['user']['email']
        })
        
        if existing_player:
            session['player_id'] = existing_player['_id']
            session['hunt_id'] = hunt_id
            return redirect(url_for('current_riddle_get', 
                                  player_id=existing_player['_id'], 
                                  hunt_id=hunt_id))

        player_id = random.randint(1000, 9999)
        player = {
            "_id": player_id,
            'name': name,
            'hunt_id': hunt_id,
            'current_object': 0,
            'start_time': time.time(),
            'current_time': time.time(),
            'finished': False,
            'user_email': session['user']['email']
        }
        players_collection.insert_one(player)

        hunts_collection.update_one(
            {"_id": hunt_id},
            {"$push": {"players": player_id}}
        )

        session['hunt_id'] = hunt_id
        session['player_id'] = player_id

        return redirect(url_for('current_riddle_get', 
                              player_id=player_id, 
                              hunt_id=hunt_id))
    else:
        return render_template("error.html", error="This hunt does not exist.")

@app.route('/profile')
@login_required
def profile():
    user = session['user']
    hunt_id = session.get('hunt_id')
    player_id = session.get('player_id')
    
    if hunt_id and player_id:
        player = players_collection.find_one({"_id": player_id})
        if player and not player['finished']:
            return redirect(url_for('current_riddle_get', 
                                  player_id=player_id, 
                                  hunt_id=hunt_id))
    
    return render_template('profile.html', 
                         user=user,
                         hunt_id=hunt_id,
                         player_id=player_id)
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/create-game", methods=["GET"])
@login_required
def create_game():
    return render_template("create-game.html")

@app.route("/join-game", methods=["GET"])
def join_game():
    return render_template("join-game.html")

def process_join_hunt(hunt_id, name):
    hunt = hunts_collection.find_one({"_id": hunt_id})
    if hunt:
        player_id = random.randint(1000, 9999)
        player = {
            "_id": player_id,
            'name': name,
            'hunt_id': hunt_id,
            'current_object': 0,
            'start_time': time.time(),
            'current_time': time.time(),
            'finished': False,
            'user_email': session.get('user', {}).get('email')  # Store user email
        }
        players_collection.insert_one(player)

        hunts_collection.update_one(
            {"_id": hunt_id},
            {"$push": {"players": player_id}}
        )

        session['hunt_id'] = hunt_id
        session['player_id'] = player_id

        return render_template("save-local.html", player_id=player_id, hunt_id=hunt_id)
    else:
        return render_template("error.html", error="This hunt does not exist.")

# Add these routes to your Flask application
@app.route("/current-riddle")
@login_required
def current_riddle_redirect():
    # Get IDs from session
    player_id = session.get('player_id')
    hunt_id = session.get('hunt_id')
    
    if player_id and hunt_id:
        return redirect(url_for('current_riddle_get', 
                              player_id=player_id, 
                              hunt_id=hunt_id))
    
    return redirect(url_for('profile'))

@app.route("/current-riddle/<int:player_id>/<int:hunt_id>")
@login_required
def current_riddle_get(player_id, hunt_id):
    # Verify the player belongs to the logged-in user
    player = players_collection.find_one({
        "_id": player_id,
        "user_email": session['user']['email']
    })
    hunt = hunts_collection.find_one({"_id": hunt_id})

    if not player or not hunt:
        return render_template("error.html", 
                             error="Player or hunt not found. Please try joining the hunt again.")

    if player['hunt_id'] != hunt_id:
        return render_template("error.html", 
                             error="Player is not part of this hunt.")

    current_object = player['current_object']
    
    # Check if player has finished
    if current_object >= len(hunt['objects']):
        players_collection.update_one(
            {"_id": player_id},
            {"$set": {"finished": True}}
        )
        return redirect(url_for('finish_game', 
                              player=player_id, 
                              hunt=hunt_id))

    next_hint = hunt['objects'][current_object]['riddle']
    next_room = hunt['objects'][current_object]['room']
    
    return render_template(
        "player-dashboard.html",
        riddle=next_hint,
        room=next_room,
        obj=current_object,
        player_id=player_id,
        hunt_id=hunt_id
    )


@app.route("/start-hunt", methods=['POST'])
def start_hunt():
    hunt_name = request.form['roomName']
    organizer = request.form['org']
    riddle1 = request.form['riddle1']
    riddle2 = request.form['riddle2']
    riddle3 = request.form['riddle3']
    room1 = request.form['room1']
    room2 = request.form['room2']
    room3 = request.form['room3']
    code1 = request.form['code1']
    code2 = request.form['code2']
    code3 = request.form['code3']
    hunt_id = random.randint(1000, 9999)

    hunt_data = {
        "_id": hunt_id,
        'hunt_name': hunt_name,
        'organizer': organizer,
        'objects': [
            {"riddle": riddle1, "room": room1, "code": code1},
            {"riddle": riddle2, "room": room2, "code": code2},
            {"riddle": riddle3, "room": room3, "code": code3}
        ],
        'players': []
    }
    hunts_collection.insert_one(hunt_data)

    return render_template("hunt-reveal.html", hunt_name=hunt_name, hunt_id=hunt_id)

@app.route("/submit-item", methods=['POST'])
def submit_item():
    player_id = int(request.form["player-id"])
    hunt_id = int(request.form["hunt-id"])
    code = str(request.form["code"])

    player = players_collection.find_one({"_id": player_id})
    hunt = hunts_collection.find_one({"_id": hunt_id})

    if not player or not hunt:
        return render_template("error.html", error="Invalid player or hunt ID.")

    current_object_idx = player['current_object']
    correct_code = str(hunt['objects'][current_object_idx]['code'])

    if player['finished']:
        return render_template("error.html", error="You have already finished the hunt!")

    if code == correct_code:
        players_collection.update_one(
            {"_id": player_id},
            {"$inc": {"current_object": 1}, "$set": {"current_time": time.time()}}
        )
        player = players_collection.find_one({"_id": player_id})  # Re-fetch updated player data

        if player['current_object'] < len(hunt['objects']):
            return redirect(f"/current-riddle/{player_id}/{hunt_id}")
        else:
            players_collection.update_one(
                {"_id": player_id},
                {"$set": {"finished": True}}
            )
            return redirect(f"/finish/{player_id}/{hunt_id}")
    else:
        return render_template("error.html", error="Incorrect code.")

@app.route("/finish/<player>/<hunt>", methods=["GET"])
def finish_game(player, hunt):
    player_id = int(player)
    hunt_id = int(hunt)

    player = players_collection.find_one({"_id": player_id})
    if player and player['finished']:
        player_time = player['current_time']
        rank = 1

        for other_player in players_collection.find({"hunt_id": hunt_id, "finished": True}):
            if other_player['current_time'] < player_time:
                rank += 1

        total_seconds = round(player_time - player['start_time'])
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        return render_template(
            "finish.html", name=player['name'], rk=rank,
            hrs=hours, mins=minutes, secs=seconds
        )
    else:
        return render_template("error.html", error="Unfinished hunt or player not found.")

@app.route("/leaderboard/", methods=['GET'])
@app.route("/leaderboard/<int:hunt_id>", methods=['GET'])
def leaderboard(hunt_id=None):
    if hunt_id is None:
        # Get all hunts and their players
        all_hunts = list(hunts_collection.find())
        if not all_hunts:
            return render_template("error.html", error="No hunts found.")
        
        # Default to showing the most recent hunt if no specific hunt is selected
        hunt = all_hunts[-1]
        hunt_id = hunt['_id']
    else:
        hunt = hunts_collection.find_one({"_id": hunt_id})
        if not hunt:
            return render_template("error.html", error="Hunt not found.")

    # Get all players for this hunt
    players = list(players_collection.find({"hunt_id": hunt_id}))
    
    # Process player data for ranking
    leaderboard_data = []
    for player in players:
        player_data = {
            'name': player['name'],
            'current_object': player['current_object'],
            'finished': player.get('finished', False),
            'total_time': None
        }
        
        # Calculate total time for finished players
        if player.get('finished'):
            total_seconds = round(player['current_time'] - player['start_time'])
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            player_data['total_time'] = {
                'hours': int(hours),
                'minutes': int(minutes),
                'seconds': int(seconds),
                'total_seconds': total_seconds
            }
        
        leaderboard_data.append(player_data)
    
    # Sort players
    leaderboard_data.sort(key=lambda x: (
        not x['finished'],
        -x['current_object'],
        x['total_time']['total_seconds'] if x['total_time'] else float('inf')
    ))

    # Get all hunt IDs and names for the dropdown
    all_hunts = list(hunts_collection.find({}, {'_id': 1, 'hunt_name': 1}))
    
    # Format data for template
    names = []
    scores = []
    times = []
    statuses = []

    for player in leaderboard_data:
        names.append(player['name'])
        scores.append(f"{player['current_object']}/{len(hunt['objects'])}")
        
        if player['total_time']:
            times.append(f"{player['total_time']['hours']}h {player['total_time']['minutes']}m {player['total_time']['seconds']}s")
        else:
            times.append("In Progress")
            
        statuses.append("Finished!" if player['finished'] else "In Progress")

    return render_template(
        "leaderboard.html",
        hunt_name=hunt['hunt_name'],
        hunt_id=hunt_id,
        names=names,
        scores=scores,
        times=times,
        statuses=statuses,
        total_players=len(names),
        all_hunts=all_hunts
    )

@app.route("/link-event-to-hunt", methods=["POST"])
def link_event_to_hunt():
    event_id = ObjectId(request.form["event_id"])
    hunt_id = int(request.form["hunt_id"])
    
    # Update event with hunt ID
    events_collection.update_one(
        {"_id": event_id},
        {"$addToSet": {"hunt_ids": hunt_id}}
    )
    
    # Update hunt with event information
    hunts_collection.update_one(
        {"_id": hunt_id},
        {"$addToSet": {"event_ids": str(event_id)}}
    )
    
    return jsonify({"success": True})
@app.route("/events/<int:hunt_id>", methods=["GET"])
def get_hunt_events(hunt_id):
    events = events_collection.find({"hunt_ids": hunt_id})
    return render_template("events.html", events=events)

@app.route("/get-events")
@login_required
def show_events():
    try:
        # Fetch all events from MongoDB
        events = list(events_collection.find().sort("date", -1))  # Sort by date descending
        
        # Process events for display
        for event in events:
            event['_id'] = str(event['_id'])  # Convert ObjectId to string
            # Format date for display
            if 'date' in event:
                date_obj = datetime.strptime(event['date'], '%Y-%m-%d')
                event['formatted_date'] = date_obj.strftime('%B %d, %Y')
            # Add creator info if available
            event['creator'] = event.get('creator_email') == session['user']['email']
        
        return render_template('events.html', events=events)
    except Exception as e:
        print(f"Error fetching events: {e}")
        return render_template('events.html', events=[], error="Failed to load events")

@app.route("/create-event", methods=["POST"])
@login_required
def create_event():
    try:
        event_data = {
            "name": request.form["name"],
            "description": request.form["description"],
            "date": request.form["date"],
            "location": request.form["location"],
            "hunt_ids": [],
            "creator_email": session['user']['email'],
            "created_at": datetime.utcnow()
        }
        
        result = events_collection.insert_one(event_data)
        
        # Redirect to events page after successful creation
        return redirect(url_for('show_events'))
    except Exception as e:
        print(f"Error creating event: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/delete-event/<event_id>", methods=["POST"])
@login_required
def delete_event(event_id):
    try:
        event = events_collection.find_one({"_id": ObjectId(event_id)})
        if event and event.get('creator_email') == session['user']['email']:
            events_collection.delete_one({"_id": ObjectId(event_id)})
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
