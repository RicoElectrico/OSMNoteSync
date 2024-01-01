#!/usr/bin/env python
"""
OSMNoteSync is an XML parser that imports OSM Note dumps into a PostgreSQL database, optionally with PostGIS.
It also syncs latest notes from the OSM API and prunes notes hidden by OSM moderators.

@author: Michał Brzozowski, based on ChangesetMD by Toby Murray
"""

import sys
import argparse
from datetime import datetime
from datetime import timedelta
import psycopg2
import psycopg2.extras
import queries
import requests
from lxml import etree

try:
    from bz2file import BZ2File

    bz2Support = True
except ImportError:
    bz2Support = False

REPL_URL = "https://api.openstreetmap.org/api/0.6/notes/search"

class OSMNoteSync:
    def __init__(self, createGeometry):
        self.createGeometry = createGeometry

    def truncateTables(self, connection):
        print('truncating tables')
        cursor = connection.cursor()
        cursor.execute("TRUNCATE TABLE note_comment CASCADE;")
        cursor.execute("TRUNCATE TABLE note CASCADE;")
        cursor.execute("TRUNCATE TABLE users CASCADE;")
        cursor.execute(queries.dropIndexes)
        connection.commit()

    def createTables(self, connection):
        print('creating tables')
        cursor = connection.cursor()
        cursor.execute(queries.createNoteTable)
        cursor.execute(queries.initStateTable)

        if self.createGeometry:
            cursor.execute(queries.createGeometryColumn)
        connection.commit()

    def insertNewBatch(self, connection, data_arr):
        cursor = connection.cursor()
        if self.createGeometry:
            sql = """INSERT into note
                    (id, created_at, closed_at, lon, lat, geom)
                    values (%s,%s,%s,%s,%s,ST_SetSRID(ST_MakePoint(%s,%s), 4326))"""
            psycopg2.extras.execute_batch(cursor, sql, data_arr)
            cursor.close()
        else:
            sql = """INSERT into note
                    (id, created_at, closed_at, lon, lat)
                    values (%s,%s,%s,%s,%s)"""
            psycopg2.extras.execute_batch(cursor, sql, data_arr)
            cursor.close()
 
    def insertNewBatchComment(self, connection, comment_arr):
        cursor = connection.cursor()
        sql = """INSERT into note_comment
                    (note_id, action, time_stamp, user_id, user_name, txt)
                    values (%s,%s,%s,%s,%s,%s)"""
        psycopg2.extras.execute_batch(cursor, sql, comment_arr)
        cursor.close()

    def deleteExisting(self, connection, id, comments):
        def customKey(item):
            return( item[0],
                    item[1],
                    item[2],
                    item[3] if item[3] is not None else 0,
                    item[4] if item[4] is not None else '',
                    item[5] if item[5] is not None else '')
        
        cursor = connection.cursor()
        cursor.execute(
            """SELECT note_id, action, time_stamp, user_id, user_name, txt FROM note_comment
            WHERE note_id = %s""",
            (id,)
        )
        
        commentsDB = cursor.fetchall()

        if not commentsDB:
            return True

        commentsDB = sorted(commentsDB, key=customKey)
        comments = sorted(comments, key=customKey)

        if comments != commentsDB:
            cursor.execute(
                """DELETE FROM note_comment
                WHERE note_id = %s""",
                (id,)
            )

            cursor.execute(
                """DELETE FROM note
                WHERE id = %s""",
                (id,)
            )
            cursor.close()
            return True
        else:
            return False

    def pruneHidden(self, connection, noteFile):
        cursor = connection.cursor()
        context = etree.iterparse(noteFile)
        action, root = next(context)
        noteIds = []
        commentDates = []
        for action, elem in context:
            if elem.tag != "note":
                continue
            noteIds.append(int(elem.attrib["id"]))
            for commentElement in elem.iterchildren(tag="comment"):
                commentDates.append(datetime.strptime(commentElement.attrib['timestamp'],"%Y-%m-%dT%H:%M:%SZ"))
            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]
        maxId = max(noteIds)
        allIds = set(range(1, maxId + 1))
        missingIds = sorted(list(allIds - set(noteIds)))
        lastCommentDate = max(commentDates)
        print(f"last comment date {lastCommentDate}")
        batchTuples = [(missingId, missingId, lastCommentDate, missingId, missingId, lastCommentDate) for missingId in missingIds]
        query = '''
        DELETE from note
        WHERE id = %s
        AND (SELECT MAX(time_stamp) FROM note_comment WHERE note_id = %s) < %s;
        DELETE from note_comment
        WHERE note_id = %s
        AND (SELECT MAX(time_stamp) FROM note_comment WHERE note_id = %s) < %s;
        '''
        psycopg2.extras.execute_batch(cursor, query, batchTuples)
        connection.commit()
        print("pruning complete")       

    def parseFile(self, connection, noteFile, doReplication):
        parsedCount = 0
        startTime = datetime.now()
        cursor = connection.cursor()
        context = etree.iterparse(noteFile)
        action, root = next(context)
        notes = []
        comments = []
        for action, elem in context:
            if elem.tag != "note":
                continue

            parsedCount += 1
            if doReplication:
                currentComments = []
                for commentElement in elem.find("comments").iterfind("comment"):
                    comment = (
                        int(elem.find("id").text),
                        commentElement.find("action").text,
                        datetime.strptime(commentElement.find("date").text,"%Y-%m-%d %H:%M:%S %Z"),
                        int(commentElement.find("uid").text) if commentElement.find("uid") is not None else None,
                        commentElement.find("user").text if commentElement.find("user") is not None else None,
                        commentElement.find("text").text
                    )
                    currentComments.append(comment)
                needsInsert = self.deleteExisting(connection, int(elem.find("id").text), currentComments)
                
                if self.createGeometry:
                    note = (
                        (
                            elem.find("id").text,
                            elem.find("date_created").text,
                            elem.find("date_closed").text if elem.find("date_closed") is not None else None,
                            elem.attrib["lon"],
                            elem.attrib["lat"],
                            elem.attrib["lon"],
                            elem.attrib["lat"],
                        )
                    )
                else:
                    note = (
                        (
                            elem.find("id").text,
                            elem.find("date_created").text,
                            elem.find("date_closed").text if elem.find("date_closed") is not None else None,
                            elem.attrib["lon"],
                            elem.attrib["lat"],
                        )
                    )
                if needsInsert:
                    comments.extend(currentComments)
                    notes.append(note)
            else:        
                for commentElement in elem.iterchildren(tag="comment"):
                    comment = (
                        elem.attrib.get('id'),                   
                        commentElement.attrib.get('action'),
                        commentElement.attrib.get('timestamp'),
                        commentElement.attrib.get('uid', None),
                        commentElement.attrib.get('user', None),
                        commentElement.text
                    )
                    comments.append(comment)


                if self.createGeometry:
                    notes.append(
                        (
                            elem.attrib["id"],
                            elem.attrib["created_at"],
                            elem.attrib.get("closed_at", None),
                            elem.attrib["lon"],
                            elem.attrib["lat"], 
                            elem.attrib["lon"],
                            elem.attrib["lat"],                    
                        )
                    )
                else:
                    notes.append(
                        (
                            elem.attrib["id"],
                            elem.attrib["created_at"],
                            elem.attrib.get("closed_at", None),
                            elem.attrib["lon"],
                            elem.attrib["lat"],                   
                        )
                    )

            if (parsedCount % 100000) == 0:
                self.insertNewBatch(connection, notes)
                self.insertNewBatchComment(connection, comments)
                notes = []
                comments = []
                print("parsed {}".format(("{:,}".format(parsedCount))))
                print(
                    "cumulative rate: {}/sec".format(
                        "{:,.0f}".format(
                            parsedCount
                            / timedelta.total_seconds(datetime.now() - startTime)
                        )
                    )
                )

            # clear everything we don't need from memory to avoid leaking
            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]
        # Update whatever is left, then commit
        self.insertNewBatch(connection, notes)
        self.insertNewBatchComment(connection, comments)
        connection.commit()
        print("parsing complete")
        print("parsed {:,}".format(parsedCount))
      

    def fetchReplicationFile(self, noteLimit):
        fileUrl = f"{REPL_URL}?limit={noteLimit}"
        print("opening replication file at " + fileUrl)
        response = requests.get(fileUrl, stream=True)
        response.raw.decode_content = True
        return response.raw

    def doReplication(self, connection):
        cursor = connection.cursor(cursor_factory=psycopg2.extras.DictCursor)
        try:
            cursor.execute(
                "LOCK TABLE note_replication_state IN ACCESS EXCLUSIVE MODE NOWAIT"
            )
        except psycopg2.OperationalError as e:
            print("error getting lock on state table. Another process might be running")
            return 1
        cursor.execute("select * from note_replication_state")
        dbStatus = cursor.fetchone()
        if dbStatus["update_in_progress"] == 1:
            print("concurrent update in progress. Bailing out!")
            return 1
        # -1 means freshly after import. Download maximum allowed number of notes, to cover >24h between daily note dumps.
        noteLimit = 10000 if dbStatus["update_in_progress"] == -1 else 200
        cursor.execute("update note_replication_state set update_in_progress = 1")
        connection.commit()
        # No matter what happens after this point, execution needs to reach the update statement
        # at the end of this method to unlock the database or an error will forever leave it locked
        returnStatus = 0
        try:
            cursor.execute("select max(time_stamp) from note_comment")
            latestTimestampBeforeReplication = cursor.fetchone()[0]
            print(f"latest timestamp before replication: {latestTimestampBeforeReplication}")
            print("commencing replication")
            self.parseFile(
                connection, self.fetchReplicationFile(noteLimit), True
            )
            print("updating user mapping")
            cursor.execute(queries.updateUserMapping,(latestTimestampBeforeReplication,))
            connection.commit()
            print("finished with replication. Clearing status record")
        except Exception as e:
            print("error during replication")
            print(e)
            returnStatus = 2
        cursor.execute(
            "update note_replication_state set update_in_progress = 0",
            )
        connection.commit()
        return returnStatus


if __name__ == "__main__":
    beginTime = datetime.now()
    endTime = None
    timeCost = None

    argParser = argparse.ArgumentParser(
        description="Parse OSM notes into a database"
    )
    argParser.add_argument(
        "-t",
        "--trunc",
        action="store_true",
        default=False,
        dest="truncateTables",
        help="Truncate existing tables (also drops indexes)",
    )
    argParser.add_argument(
        "-c",
        "--create",
        action="store_true",
        default=False,
        dest="createTables",
        help="Create tables",
    )
    argParser.add_argument(
        "-H", "--host", action="store", dest="dbHost", help="Database hostname"
    )
    argParser.add_argument(
        "-P",
        "--port",
        action="store",
        dest="dbPort",
        default=None,
        help="Database port",
    )
    argParser.add_argument(
        "-u",
        "--user",
        action="store",
        dest="dbUser",
        default=None,
        help="Database username",
    )
    argParser.add_argument(
        "-p",
        "--password",
        action="store",
        dest="dbPass",
        default=None,
        help="Database password",
    )
    argParser.add_argument(
        "-d",
        "--database",
        action="store",
        dest="dbName",
        help="Target database",
        required=True,
    )
    argParser.add_argument(
        "-f",
        "--file",
        action="store",
        dest="fileName",
        help="OSM note dump file to parse",
    )
    argParser.add_argument(
        "-r",
        "--replicate",
        action="store_true",
        dest="doReplication",
        default=False,
        help="Download and import latest notes to an existing database",
    )
    argParser.add_argument(
        "-g",
        "--geometry",
        action="store_true",
        dest="createGeometry",
        default=False,
        help="Build geometry of notes (requires postgis)",
    )
    argParser.add_argument(
        "-D",
        "--prune-hidden",
        action="store_true",
        default=False,
        dest="pruneHidden",
        help="Prune hidden notes from the database using a note dump file",
    )
    args = argParser.parse_args()

    conn = psycopg2.connect(
        database=args.dbName,
        user=args.dbUser,
        password=args.dbPass,
        host=args.dbHost,
        port=args.dbPort,
    )

    ns = OSMNoteSync(args.createGeometry)
    if args.truncateTables:
        ns.truncateTables(conn)

    if args.createTables:
        ns.createTables(conn)


    if args.doReplication:
        returnStatus = ns.doReplication(conn)
        sys.exit(returnStatus)

    if not (args.fileName is None):
        if args.createGeometry:
            print("parsing note file with geometries")
        else:
            print("parsing note file")
        noteFile = None
        if args.fileName[-4:] == ".bz2":
            if bz2Support:
                noteFile = BZ2File(args.fileName)
            else:
                print(
                    "ERROR: bzip2 support not available. Unzip file first or install bz2file"
                )
                sys.exit(1)
        else:
            noteFile = open(args.fileName, "rb")

        if noteFile != None:
            if args.pruneHidden:
                ns.pruneHidden(conn, noteFile)
            else:
                ns.parseFile(conn, noteFile, args.doReplication)
        else:
            print(
                "ERROR: no note file opened. Something went wrong in processing args"
            )
            sys.exit(1)

        if not args.doReplication and not args.pruneHidden:
            cursor = conn.cursor()
            print("creating constraints")
            cursor.execute(queries.createConstraints)
            print("creating indexes")
            cursor.execute(queries.createIndexes)
            print("creating user mapping")
            cursor.execute(queries.createUserMapping)
            if args.createGeometry:
                cursor.execute(queries.createGeomIndex)
            conn.commit()

        conn.close()

    endTime = datetime.now()
    timeCost = endTime - beginTime

    print("Processing time cost is ", timeCost)

    print("All done. Enjoy your notes!")
