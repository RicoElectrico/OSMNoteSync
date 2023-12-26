'''
Just a utility file to store some SQL queries for easy reference

@author: Michal Brzozowski, Toby Murray
'''
createNoteTable = '''CREATE TABLE note (
  id bigint not null,
  created_at timestamp without time zone not null,
  closed_at timestamp without time zone,  
  lat numeric(10,7) not null,
  lon numeric(10,7) not null
);
CREATE TABLE note_comment (
  note_id bigint not null,
  action text not null,
  time_stamp timestamp without time zone not null,
  user_id bigint,
  user_name varchar(255),
  txt text
);
CREATE TABLE note_replication_state (
  update_in_progress smallint
);

'''
initStateTable = '''INSERT INTO note_replication_state VALUES (-1)''';

dropIndexes = '''ALTER TABLE note DROP CONSTRAINT IF EXISTS note_pkey CASCADE;
DROP INDEX IF EXISTS note_created_idx, note_closed_idx, note_comment_id_idx, note_geom_gist ;
'''

createConstraints = '''ALTER TABLE note ADD CONSTRAINT note_pkey PRIMARY KEY(id);'''

createIndexes = '''CREATE INDEX note_created_idx ON note(created_at);
CREATE INDEX note_closed_idx ON note(closed_at);
CREATE INDEX note_comment_id_idx ON note_comment(note_id);
CREATE INDEX note_comment_timestamp_idx on note_comment(time_stamp)
'''

createGeometryColumn = '''
CREATE EXTENSION IF NOT EXISTS postgis;
SELECT AddGeometryColumn('note','geom', 4326, 'POINT', 2);
'''

createGeomIndex = '''
CREATE INDEX note_geom_gist ON note USING GIST(geom);
'''
