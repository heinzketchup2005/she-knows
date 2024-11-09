hunt_id = int(request.form["idd"])
    name = request.form["name"]
    password = request.form["password"]  

    hunt = hunts_collection.find_one({"_id": hunt_id})