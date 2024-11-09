
from flask import Flask, render_template, request, redirect, session, url_for
from pymongo import MongoClient
import random
import time
from authlib.integrations.flask_client import OAuth

client = MongoClient("mongodb+srv://scavenger_user:hunter123456@cluster01.ct2bj.mongodb.net/?retryWrites=true&w=majority&appName=Cluster01")
db = client["scavenger_hunt"]
hunts_collection = db["hunts"]
players_collection = db["players"]

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Make sure to use a secure key for production

# Initialize OAuth
oauth = OAuth(app)

# Google OAuth configuration (hardcoded credentials)
google = oauth.register(
    name='google',
    client_id='738965192863-5q8frhuc5umhp0ek00p3ih9j2dp6rb4m.apps.googleusercontent.com',  # Replace with your actual Google client ID
    client_secret='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',  # Replace with your actual Google client secret
    access_token_url='https://accounts.google.com/o/oauth2/token',
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    authorize_params=None,
    redirect_uri='http://127.0.0.1:5000/google/callback',
    client_kwargs={'scope': 'openid profile email'}
)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/create-game", methods=["GET"])
def create_game():
    return render_template("create-game.html")

@app.route("/join-game", methods=["GET"])
def join_game():
    return render_template("join-game.html")


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

@app.route("/join-hunt", methods=["POST"])
def join_hunt():
    hunt_id = int(request.form["idd"])
    name = request.form["name"]

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
            'finished': False
        }
        players_collection.insert_one(player)

        hunts_collection.update_one(
            {"_id": hunt_id},
            {"$push": {"players": player_id}}
        )
        return render_template("save-local.html", player_id=player_id, hunt_id=hunt_id)
    else:
        return render_template("error.html", error="This hunt does not exist.")

@app.route("/current-riddle", methods=["POST"])
def current_riddle():
    player_id = int(request.form["player_id"])
    hunt_id = int(request.form["hunt_id"])

    player = players_collection.find_one({"_id": player_id})
    hunt = hunts_collection.find_one({"_id": hunt_id})

    if player and hunt:
        current_object = player['current_object']
        next_hint = hunt['objects'][current_object]['riddle']
        next_room = hunt['objects'][current_object]['room']
        return render_template(
            "player-dashboard.html", riddle=next_hint, room=next_room,
            obj=current_object, player_id=player_id, hunt_id=hunt_id
        )
    else:
        return render_template("error.html", error="Player or hunt not found.")

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

@app.route("/leaderboard/<int:hunt_id>", methods=['GET'])
def leaderboard(hunt_id):
    hunt = hunts_collection.find_one({"_id": hunt_id})
    if hunt:
        players = players_collection.find({"hunt_id": hunt_id})
        leaderboard_data = sorted(players, key=lambda p: p['current_object'], reverse=True)

        names = [p['name'] for p in leaderboard_data]
        scores = [p['current_object'] for p in leaderboard_data]

        return render_template("leaderboard.html", names=names, scores=scores)
    else:
        return render_template("error.html", error="Hunt not found.")
       
@app.route('/login/google')
def login_google():
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/google/callback')
def google_callback():
    token = google.authorize_access_token()
    user_info = google.parse_id_token(token)
    session['user'] = user_info  # Store user info in session
    return redirect(url_for('profile'))

@app.route('/profile')
def profile():
    user = session.get('user')
    if user:
        return render_template('profile.html', user=user)
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
