from flask import Flask, render_template, request, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from flask import session
from pymongo import MongoClient
import random
import time
client = MongoClient("mongodb+srv://scavenger_user:hunter123456@cluster01.ct2bj.mongodb.net/?retryWrites=true&w=majority&appName=Cluster01")

db = client["scavenger_hunt"]
hunts_collection = db["hunts"]
players_collection = db["players"]


app = Flask(__name__)
app.secret_key = 'Shambhav2005'  

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
    password = request.form["password"]  

    hunt = hunts_collection.find_one({"_id": hunt_id})
    if not hunt:
        return render_template("error.html", error="This hunt does not exist.")

    player = players_collection.find_one({"hunt_id": hunt_id, "name": name})
    if player:
        if check_password_hash(player['password'], password):
            session['player_id'] = player['_id']  
            session['hunt_id'] = hunt_id
            if player['finished']:
                return redirect(url_for("finish_game", player_id=player['_id'], hunt_id=hunt_id))
            return redirect(url_for("current_riddle", player_id=player['_id'], hunt_id=hunt_id))
        else:
            return render_template("error.html", error="Incorrect password.")
    else:
        player_id = random.randint(1000, 9999)
        player_data = {
            "_id": player_id,
            'name': name,
            'hunt_id': hunt_id,
            'current_object': 0,
            'start_time': time.time(),
            'current_time': time.time(),
            'finished': False,
            'password': generate_password_hash(password)
        }
        players_collection.insert_one(player_data)
        session['player_id'] = player_id
        session['hunt_id'] = hunt_id
        return redirect(url_for("current_riddle", player_id=player_id, hunt_id=hunt_id))

@app.route("/current-riddle/<int:player_id>/<int:hunt_id>", methods=["GET"])
def current_riddle(player_id, hunt_id):
    if 'player_id' not in session or session['player_id'] != player_id:
        return redirect(url_for("join_game"))

    player = players_collection.find_one({"_id": player_id})
    hunt = hunts_collection.find_one({"_id": hunt_id})

    if player and hunt:
        current_object = player['current_object']
        if current_object < len(hunt['objects']):
            next_hint = hunt['objects'][current_object]['riddle']
            next_room = hunt['objects'][current_object]['room']
            return render_template("player-dashboard.html", riddle=next_hint, room=next_room, obj=current_object, player_id=player_id, hunt_id=hunt_id)
        else:
            return redirect(url_for("finish_game", player_id=player_id, hunt_id=hunt_id))
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
        player = players_collection.find_one({"_id": player_id}) 

        if player['current_object'] < len(hunt['objects']):
            return redirect(url_for("current_riddle", player_id=player_id, hunt_id=hunt_id))
        else:
            players_collection.update_one(
                {"_id": player_id},
                {"$set": {"finished": True}}
            )
            return redirect(url_for("finish_game", player_id=player_id, hunt_id=hunt_id))
    else:
        return render_template("error.html", error="Incorrect code.")

@app.route("/finish/<int:player_id>/<int:hunt_id>", methods=["GET"])
def finish_game(player_id, hunt_id):
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
            hrs=hours, mins=minutes, secs=seconds, hunt_id=hunt_id
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

if __name__ == '__main__':
    app.run(debug=True)
