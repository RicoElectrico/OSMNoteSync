#!/bin/bash
#
# call_osmnotesync_replication.sh
#
# Designed to be run from cron, as the user that owns the notes database
# Status updates are written to the note_replication_state table in that database.

log_msg()
{
    echo "[`date +"%Y-%m-%d %H:%M:%S"`] $$ $1"
}

LOCK_FILE="/tmp/osm_sync.lock"
DB_NAME="notes"

if [ -e "$LOCK_FILE" ]; then
    log_msg "Script is already running. Exiting."
    exit 1
fi

touch "$LOCK_FILE"


cd "$(dirname "${BASH_SOURCE[0]}")"
source ./venv/bin/activate
log_msg "OSMNoteSync replication starting"
python osmnotesync.py -d ${DB_NAME} -r -g
log_msg "OSMNoteSync replication finished"

wget_output=$(wget --timestamping "https://planet.osm.org/notes/planet-notes-latest.osn.bz2" 2>&1)

if [[ $? -eq 0 ]]; then
    log_msg "Dump download successful."
    if [[ ${wget_output} == *"not modified on server"* ]]; then
        log_msg "No new dump on server."
    else
        log_msg "Running OSMNoteSync pruning"
        python osmnotesync.py -d ${DB_NAME} -g -D -f planet-notes-latest.osn.bz2
        log_msg "OSMNoteSync pruning finished"
        # Dumps are daily, so on next invocation let's download maximum possible number of notes from API
        # Just in the rare case usual small limit caused us to miss something.
        psql -d ${DB_NAME} -c "update note_replication_state set update_in_progress = -1;"
    fi
else
    log_msg "Error during dump download"
fi

rm -f "$LOCK_FILE"