from flask import Flask, render_template, request, url_for, session, redirect, jsonify,send_from_directory
from datetime import datetime, timedelta
from flask_pymysql import MySQL
import re
import pymysql
import random
import sys
import db_config
import os

app = Flask(__name__)

app.secret_key = 'streamtime'

#Set up pymysql connection arguments
pymysql_connect_kwargs = {'user': db_config.DB_USER, 
                          'password': db_config.DB_PASS, 
                          'host': db_config.DB_SERVER,
                          'database': db_config.DB}

app.config['pymysql_kwargs'] = pymysql_connect_kwargs
mysql = MySQL(app)


"""

Login Page

"""
@app.route("/")
@app.route("/login", methods=['GET', 'POST'])
def login():
    errorMessage = ''
    if request.method == 'POST' and 'email' in request.form and 'phone' in request.form:
        email = request.form['email']
        phone = request.form['phone']

        # Using prepared statements to avoid SQL injection
        cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
        cursor.execute('SELECT userId FROM users WHERE email = %s AND phone = %s', (email, phone))
        user = cursor.fetchone()

        if user:
            session['userLoggedIn'] = True
            session['id'] = user['userId']
            return redirect(url_for('home'))
        else:
            errorMessage = 'Invalid email or phone number!'

    return render_template('login.html', errorMessage=errorMessage)



"""

Logout Page

"""
@app.route('/logout')
def logout():
    # Remove session data, logging out the user or guest
    session.pop('userLoggedIn', None)
    session.pop('id', None)
    session.pop('guestUser', None)  # Remove guest flag if present
    # Redirect to login page
    return redirect(url_for('login'))




"""

Register Page and dependencies

"""

"""

Verify fields of the user registration form

"""
def verifyUser(firstName, lastName, email, phone, plan):
    #Check email address format make sure @ has text on either side
    if not re.match(r'[^@]+@[^@]+\.[^@]+', email):
        return 'Invalid email address!'
    #Check first name for only alpha characters
    elif not re.match(r'[A-Za-z]+', firstName):
        return 'Name must cotain only characters!'
    #Check last name for only alpha characters
    elif not re.match(r'[A-Za-z]+', lastName):
        return 'Name must cotain only characters!'
    #Check to make sure phone number is only 10 digits
    elif not re.match(r'[0-9]{10}', phone):
        return 'Phone number must only be 10 digits!'
    #Check if form is filled out and no missing fields    
    elif not firstName or not lastName or not email or not phone or not plan:
        return 'Please fill out the form!'
    return '' 

@app.route('/register', methods=['GET', 'POST'])
def register():
    errorMessage = ''
    #Get payment plan information for registration
    cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
    cursor.callproc('getPaymentPlans')
    paymentPlans = cursor.fetchall()
    # Check if firstname, lastname, email, phone and plan are selected
    if (request.method == 'POST' and 'firstName' in request.form and 
        'lastName' in request.form and 'email' in request.form and 
        'phone' in request.form and 'plan' in request.form): 

        # Create variables for easy access to each field in the signup form
        firstName = request.form['firstName']
        lastName = request.form['lastName']
        email = request.form['email']
        phone = request.form['phone']
        plan = request.form['plan']

        # Output message to let the user know if there is an error in the form
        errorMessage = verifyUser(firstName, lastName, email, phone, plan)
        # If account exists show error and validation checks
        if(errorMessage == ''):
            # Account doesnt exists and the form data is valid, now insert new account into accounts table
            cursor = mysql.connection.cursor()
            cursor.callproc('createUser', args = (firstName, lastName, email, phone, plan))
            errorMessage = cursor.fetchone()
            if(errorMessage):
                errorMessage = errorMessage[0]
            mysql.connection.commit()

            # If account exists in accounts table in out database
            if not errorMessage:
                # Check if account exists using MySQL Function findUser
                cursor = mysql.connection.cursor()
                cursor.execute('SELECT findUser(%s, %s) as foundUser', (email, phone,))
                account = cursor.fetchone()
                # Session data with id and loggedin information
                session['userLoggedIn'] = True
                session['id'] = account[0]
                # Redirect to home page
                return redirect(url_for('home'))

    elif request.method == 'POST':
        # Form is empty
        errorMessage = 'Please complete the registration'
    # Show registration form with error message if incorrent form data
    return render_template('register.html', errorMessage = errorMessage, paymentplans = paymentPlans)


"""

Home Page and dependencies

"""
# Calculate the total duration of all the songs in the playlist
def calculateTotalDuration(playlistsongs):
    totalTime = 0
    for p in playlistsongs:
        if not totalTime:
            totalTime = p['duration']
        else:
            totalTime += p['duration']
    return totalTime

@app.route('/home', methods=['GET', 'POST'])
def home():
    # Check if user is logged in
    if 'userLoggedIn' in session:
        if 'guestUser' in session and session['guestUser']:
            # Handle guest-specific logic
            return render_template('home.html', playlists=[], guest=True)
        else:
            # Regular logged-in user logic
            if request.method == 'POST' and 'new' in request.form:
                return redirect(url_for('newplaylist'))

            if request.method == 'POST' and 'view' in request.form:
                playlistId = request.form['view']
                return redirect(url_for('playlist', playlist_id=playlistId))

            if request.method == 'POST' and 'remove' in request.form:
                playlistId = request.form['remove']
                cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
                cursor.execute('CALL removePlaylist(%s)', (playlistId,))
                mysql.connection.commit()

            # Get the user's playlists
            cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
            cursor.execute('CALL getPlaylistsUser(%s)', (session['id'],))
            playlists = list(cursor.fetchall())

            # Calculate total duration for each playlist
            for p in playlists:
                cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
                cursor.execute('CALL getPlaylistSongs(%s)', (p['playlistId'],))
                playlistsongs = list(cursor.fetchall())
                p['duration'] = calculateTotalDuration(playlistsongs)

            return render_template('home.html', playlists=playlists, guest=False)
    return redirect(url_for('login'))



"""

Profile Page and dependencies

"""
@app.route('/profile', methods = ['POST', 'GET'])
def profile():
    # Check if user is loggedin
    if 'userLoggedIn' in session:
        if request.method == 'POST' and 'edit' in request.form:
            return redirect(url_for('editplan'))
        
        if request.method == 'POST' and 'delete' in request.form:
            cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
            cursor.callproc("removeUser", args = (session['id'],))
            mysql.connection.commit()
            return redirect(url_for('logout'))
        
        #Get information about the user to display
        cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
        cursor.callproc('getUserInformation', args = (session['id'],))
        userInfo = cursor.fetchone()
        #Get information about the payment plan based on the users
        cursor.callproc('getPaymentInformation', (userInfo['planId'],))
        paymentInfo = cursor.fetchone()
        #Convert date user signed up for payment plan to a readable format
        dateStr = str(userInfo['planDate'].month) + '/' + str(userInfo['planDate'].day) + '/' + str(userInfo['planDate'].year)
        return render_template('profile.html', userinfo=userInfo, paymentinfo = paymentInfo, datestr = dateStr)
        
    # User is not loggedin redirect to login page
    return redirect(url_for('login'))


@app.route('/editplan', methods=['GET', 'POST'])
def editplan():
    paymentPlans = []
    # Check if user is loggedin
    if 'userLoggedIn' in session:
        #Get payment plans
        cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
        cursor.execute('call getPaymentPlans()')
        paymentPlans = cursor.fetchall()

        if request.method == 'POST' and 'plan' in request.form:
            plan = request.form['plan']
            # Call process to change payment plan
            cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
            cursor.execute('call editPaymentPlan(%s, %s)', (session['id'], plan))
            mysql.connection.commit()
            # Redirect to profile page
            return redirect(url_for('profile'))
        
        return render_template('editplan.html', plans = paymentPlans)
    # User is not loggedin redirect to login page
    return redirect(url_for('login'))


"""

New Playlist Page

"""
@app.route('/newplaylist', methods=['GET', 'POST'])
def newplaylist():
    status = ['Public', 'Private']
    # Check if user is loggedin
    if 'userLoggedIn' in session:
        #Check if name of playlist and the status is in the form
        if request.method == 'POST' and 'name' in request.form and 'status' in request.form:
            name = request.form['name']
            status = request.form['status']
            cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
            cursor.callproc('createPlaylist', args = (name, status, session['id']))
            mysql.connection.commit()
            # Redirect to home page
            return redirect(url_for('home'))
        return render_template('newplaylist.html',  status = status)
    # User is not loggedin redirect to login page
    return redirect(url_for('login'))


"""

Edit Playlist Page

"""
@app.route('/editplaylist/<playlist_id>', methods=['GET', 'POST'])
def editplaylist(playlist_id):
    status = ['Public', 'Private']
    # Check if user is loggedin
    if 'userLoggedIn' in session:
        cursor = mysql.connection.cursor()
        cursor.execute('SELECT getPlaylistName(%s)', (playlist_id))
        playlistname = cursor.fetchone()[0]
        #Check if the name of the playlist is in the form
        if request.method == 'POST' and 'name' in request.form:
            name = request.form['name']
            status = request.form['status']
            cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
            cursor.callproc('editPlaylist', (name, status, playlist_id))
            mysql.connection.commit()
             # Redirect to home page
            return redirect(url_for('playlist', playlist_id = playlist_id))
        return render_template('editplaylist.html', status = status, name = playlistname)
    # User is not loggedin redirect to login page
    return redirect(url_for('login'))


"""

Playlist Page

"""
@app.route('/playlist/<playlist_id>', methods=['GET', 'POST'])
def playlist(playlist_id):
    if 'userLoggedIn' in session:
        #View information about a song
        if request.method == 'POST' and 'view' in request.form:
            song_id = request.form['view']
            return redirect(url_for('song', song_id = song_id, playlist_id = playlist_id))
        
        #Remove song from the current playlist
        if request.method == 'POST' and 'delete' in request.form:
            cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
            song_id = request.form['delete']
            cursor = mysql.connection.cursor()
            cursor.callproc('removeSongFromPlaylist', args = (playlist_id, song_id))
            mysql.connection.commit()
        
        #Edit name of playlist
        if request.method == 'POST' and 'edit' in request.form:
            return redirect(url_for('editplaylist', playlist_id=playlist_id))

        #Get name of the current playlist using sql procedure
        cursor = mysql.connection.cursor()
        cursor.execute('SELECT getPlaylistName(%s)', (playlist_id))
        playlistname = cursor.fetchone()[0]

        #Get playlist songs using sql procedure
        cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
        cursor.callproc('getPlaylistSongs', args = (playlist_id,))
        playlistsongs = list(cursor.fetchall())

        return render_template('playlist.html', songs = songs, playlistsongs = playlistsongs, playlistId = playlist_id, name = playlistname)
    return redirect(url_for('login'))

"""

Songs Page

"""
@app.route('/songs/<playlist_id>', methods=['GET', 'POST'])
def songs(playlist_id):
    if 'userLoggedIn' in session:
        #View information on individual song
        if request.method == 'POST' and 'view' in request.form:
            #Get songId and redirect to song page
            song_id = request.form['view']
            return redirect(url_for('song', song_id = song_id, playlist_id = playlist_id))

        #If user wants to add song to playlist
        if request.method == 'POST' and 'add' in request.form:
            cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
            #Get requested song to add
            song_id = request.form['add']
            cursor.execute('CALL addSongPlaylistLink(%s, %s)',
                           (playlist_id, song_id))
            mysql.connection.commit()
        
        #Get songs that aren't in playlist using sql query
        cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
        cursor.execute('CALL getSongsForPlaylistView(%s)', (playlist_id))
        songs = list(cursor.fetchall())    

        #Render page that displays songs in table
        return render_template('songs.html', songs = songs, playlistId = playlist_id)
    return redirect(url_for('login'))

"""

Song Info Page

"""
@app.route('/playlist/<playlist_id>/song/<song_id>', methods=['GET', 'POST'])
def song(song_id, playlist_id):
    if 'userLoggedIn' in session:
        #If user wants to return to the playlist songs page
        if request.method == 'POST' and 'back' in request.form:
            return redirect(url_for('playlist', playlist_id = playlist_id))

        #Get information on individual song    
        cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
        cursor.callproc('getSong', args = (song_id,))
        song = cursor.fetchone()
        #Render song details
        return render_template('songdetails.html', song = song)
    return redirect(url_for('login'))


from flask import send_file
import os

from flask import send_file, jsonify
import os

from flask import send_file, jsonify
import os

from flask import send_file, jsonify
import os

import os
from flask import send_from_directory

@app.route('/download/<int:song_id>', methods=['GET'])
def download_song(song_id):
    if 'userLoggedIn' in session:
        # Step 1: Retrieve the user's planId
        cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
        cursor.execute('SELECT planId FROM users WHERE userId = %s', (session['id'],))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Step 2: Check the user's planId
        plan_id = user['planId']
        if plan_id == 3:
            # Return an HTML response with an error message instead of triggering a download
            return render_template('error.html', message="Your plan does not allow downloading songs."), 403

        # Step 3: Retrieve the song details
        cursor.execute('SELECT song_link FROM songs WHERE songId = %s', (song_id,))
        song = cursor.fetchone()

        if song and song['song_link']:
            # Construct the file path based on the song's filename
            file_name = song['song_link'].split('/')[-1]
            file_path = os.path.join('static', 'music', file_name)

            # Step 4: Serve the song file if it exists
            if os.path.exists(file_path):
                return send_from_directory(os.path.dirname(file_path), file_name, as_attachment=True)
            else:
                return jsonify({"error": "File not found"}), 404
        else:
            return jsonify({"error": "Song link not available"}), 404
    return redirect(url_for('login'))

@app.route('/guest', methods=['POST'])
def guest():
    # Assign a guest user ID or set a flag
    session['userLoggedIn'] = True
    session['guestUser'] = True  # Set guest flag
    session['id'] = 'guest'  # ID to identify guest sessions
    # Redirect to home page
    return redirect(url_for('home'))
import pymysql

import logging
logging.basicConfig(level=logging.DEBUG)

import traceback

@app.route('/play/<int:playlistId>')
def play_playlist(playlistId):
    try:
        # Step 1: Retrieve all song IDs associated with the playlist from the association table
        cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT songId FROM playlist_songs WHERE playlistId = %s", (playlistId,))
        song_ids = cursor.fetchall()
        print(f"Song IDs for playlist ID {playlistId}: {song_ids}")

        if not song_ids:
            print(f"No songs found for playlist ID {playlistId}")
            return "This playlist has no songs.", 404

        # Extract song IDs into a list for querying
        song_id_list = [song['songId'] for song in song_ids]

        # Step 2: Retrieve details for each song in the playlist
        format_strings = ','.join(['%s'] * len(song_id_list))
        query = f"SELECT title, song_link, duration FROM songs WHERE songId IN ({format_strings})"
        cursor.execute(query, tuple(song_id_list))
        songs = cursor.fetchall()
        print(f"Fetched songs for playlist ID {playlistId}: {songs}")

        if not songs:
            print(f"Song details not found for songs in playlist ID {playlistId}")
            return "Songs not found for this playlist.", 404

        # Step 3: Render the template with the list of songs
        return render_template('play_playlist.html', songs=songs)

    except Exception as e:
        print("Exception occurred in play_playlist route:", traceback.format_exc())
        return "An error occurred while trying to play the playlist.", 500



@app.route('/test_db')
def test_db():
    try:
        # Try a simple query to check the database connection
        cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        return f"Database connection successful: {result}"
    except Exception as e:
        # Print the complete traceback and return an error message
        print("Database connection test failed:", traceback.format_exc())
        return "Database connection failed. Check console for details.", 500


@app.route('/songs/<PlaylistId>', methods=['GET', 'POST'], endpoint='songs_for_playlist')
def songs(PlaylistId):
    if 'userLoggedIn' in session:
        if request.method == 'POST' and 'add' in request.form:
            SongId = request.form['add']
            cursor = mysql.connection.cursor()
            cursor.callproc('addSongToPlaylist', (PlaylistId, SongId))
            mysql.connection.commit()
            return redirect(url_for('playlist', playlist_id=PlaylistId))

        cursor = mysql.connection.cursor(pymysql.cursors.DictCursor)
        cursor.execute('CALL getSongsForPlaylistView(%s)', (PlaylistId,))
        songs = list(cursor.fetchall())
        return render_template('songs.html', songs=songs, playlistId=PlaylistId)
    return redirect(url_for('login'))





@app.route('/static/music/<path:filename>')
def serve_song(filename):
    return send_from_directory('static/music', filename)

if __name__ == '__main__':
    app.run(debug=True)
