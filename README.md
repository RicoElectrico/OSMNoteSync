OSMNoteSync
=========

OSMNoteSync is a simple XML parser written in python that takes the daily note dump file from http://planet.openstreetmap.org/ and shoves the data into a simple postgres database so it can be queried.

It can also keep a database created with a daily dump file up to date using OSM API calls returning latest notes.
In addition, the notes hidden by OSM moderators, which are not exposed in the above API call, can be pruned from the database by detecting missing note IDs in the daily dump, up to its generation date.

Setup
------------

OSMNoteSync works with Python 3.6 or newer.

Aside from postgresql, OSMNoteSync depends on the python libraries psycopg2 and lxml.
On Debian-based systems this means installing the python-psycopg2 and python-lxml packages.

If you are using `pip` and `virtualenv`, you can install all dependencies with `pip install -r requirements.txt`.

If you want to parse the note file without first unzipping it, you will also need to install the [bz2file library](http://pypi.python.org/pypi/bz2file) since the built in bz2 library can not handle multi-stream bzip files.

For building geometries, ```postgis``` extension needs to be [installed](http://postgis.net/install).

OSMNoteSync expects a postgres database to be set up for it. It can likely co-exist within another database if desired. Otherwise, As the postgres user execute:

    createdb notes

It is easiest if your OS user has access to this database. I just created a user and made myself a superuser. Probably not best practices.

    createuser <username>


Full Debian build instructions
------------------------------

    TODO: unchecked!

    sudo apt install sudo screen locate git tar unzip wget bzip2 apache2 python3-psycopg2 python3-yaml libpq-dev postgresql postgresql-contrib postgis postgresql-15-postgis-3 postgresql-15-postgis-3-scripts net-tools curl python3-full gcc libpython3.11-dev libxml2-dev libxslt-dev

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

    sudo -u postgres -i
    createuser youruseraccount
    createdb -E UTF8 -O youruseraccount notes

    psql
    \c notes
    CREATE EXTENSION postgis;
    ALTER TABLE geometry_columns OWNER TO youruseraccount;
    ALTER TABLE spatial_ref_sys OWNER TO youruseraccount;
    \q
    exit


Execution
------------
The first time you run it, you will need to include the -c | --create option to create the table:

    python osmnotesync.py -d <database> -c -g

The `-g` | `--geometry` argument is optional and builds point geometries for notes so that you can query which notes are within which areas.

The create function can be combined with the file option to immediately parse a file.

To parse a dump file, use the -f | --file option.

    python osmnotesync.py -d <database> -g -f /tmp/planet-notes-latest.osm.bz2

If no other arguments are given, it will access postgres using the default settings of the postgres client, typically connecting on the unix socket as the current OS user. Use the ```--help``` argument to see optional arguments for connecting to postgres.

Again, the `-g` | `--geometry` argument is optional.  Either planet-notes-latest.osm.bz2 or nothing can be used to populate the database.

Replication
------------
After you have parsed a daily dump file into the database, the database can be kept up to date using OSM API call that return latest N notes. Usually N is 200 except for the initial replication in which for safety we use 10000, the maximum number, so that we cover whatever has changed after downloading of the dump.

    python osmnotesync.py -d <database> -r [-g]

Run this command as often as you wish to keep your database up to date with OSM.

Pruning
------------
Currently the only way to get rid of notes hidden by the OSM moderators is to scan the latest note dump for missing IDs and delete them from the DB. To account for the fact that moderators may have reopened notes after the dump generation time, OSMNoteSync intelligently skips notes with activity newer than dump generation time. This means it could take up to 24 h for a hidden note to be deleted from DB.

    python osmnotesync.py -d <database> -D -f planet-notes-latest.osn.bz2 [-g]

Cron script
------------
In `call_osmnotesync_replication.sh` there is a ready-made script to put inside a cron job. Redirect its output (`>>`) to a log file if you wish.


Notes
------------
- Prints a status message every 100,000 records.
- Takes 10-15 minutes to import the current dump on a decent home computer.
- I have commonly queried fields indexed. Depending on what you want to do, you may need more indexes.

Table Structure
------------
OSMNoteSync populates two tables with the following structure:

note:  
Primary table of all notes with the following columns:
- `id`: note ID
- `created_at`: create time
- `closed_at` : close time
- `lat/lon` : latitude and longitude in decimal degrees
- `geom`: [optional] a postgis geometry column of `Point` type (SRID: 4326)
Note that `closed_at` is null for open notes.


note\_comment:
Comments and other actions for all notes.
- `note_id` : foreign key to the ID of relevant note
- `action` : one of: `opened`, `closed`, `commented`, `reopened`, `hidden`
- `time_stamp` : Time stamp of the action
- `user_id` : Numerical user ID
- `user_name` : User name
- `txt` : Comment body
Note that for actions other than `opened` and `commented`, `txt` can be null.
Also `hidden` notes appear in the DB only if they have been `reopened` by the moderator.

users:
ID to user name mapping table.
- `id` : Numerical user ID
- `name` : User name
Note that any `user_id` <-> `user_name` inconsistencies in `note_comment` due to user name changes are fixed at each replication.

Example queries
------------
TODO

License
------------
Copyright (C) 2012  Toby Murray, (C) 2023 Michał Brzozowski

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  

See the GNU Affero General Public License for more details: http://www.gnu.org/licenses/agpl.txt
