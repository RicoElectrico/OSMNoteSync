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
CREATE TABLE users (
  id bigint PRIMARY KEY,
  name character varying(255)
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
CREATE INDEX note_comment_timestamp_idx on note_comment(time_stamp);
CREATE INDEX note_comment_user_id_idx on note_comment(user_id);
'''

createUserMapping = '''
INSERT INTO users (id, name)
SELECT DISTINCT
  user_id,
  user_name
FROM
  note_comment
WHERE
  user_id IS NOT NULL;
'''

createGeometryColumn = '''
CREATE EXTENSION IF NOT EXISTS postgis;
SELECT AddGeometryColumn('note','geom', 4326, 'POINT', 2);
'''

createGeomIndex = '''
CREATE INDEX note_geom_gist ON note USING GIST(geom);
'''

updateUserMapping = '''
WITH updated_users AS (
  SELECT DISTINCT ON (nc.user_id)
    nc.user_id,
    nc.user_name
  FROM
    note_comment nc
  WHERE
    nc.time_stamp >= %s AND nc.user_id IS NOT NULL
  ORDER BY
    nc.user_id, nc.time_stamp DESC
)
INSERT INTO users (id, name)
SELECT
  user_id,
  user_name
FROM
  updated_users
ON CONFLICT (id) DO UPDATE
SET
  name = EXCLUDED.name;
UPDATE note_comment nc
SET
  user_name = um.name
FROM
  users um
WHERE
  nc.user_id = um.id
  AND nc.user_name <> um.name;  
'''