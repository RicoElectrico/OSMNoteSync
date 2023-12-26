#!/bin/bash
#
# reset_osmnotesync_replication.sh
#
# Reset replication state should it ever gets stuck after unclean exit.
# -1 on replication will download maximum number (10000) of last modified notes from API which should be more than 1 days' worth.
#
local_filesystem_user=haxor
#localuseraccount
db_name=note_test
#notes
#
# First things first - is it already running?
#
sudo -u ${local_filesystem_user} psql -d ${db_name} -t -c "update note_replication_state set update_in_progress = -1" > /dev/null 2>&1
#
