-- Compares the title search plan without and with the trigram index.
-- Everything runs inside a transaction that is rolled back at the end.
BEGIN;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
DROP INDEX IF EXISTS ix_publications_title_trgm;

INSERT INTO publications (title, doi, published_on)
SELECT 'Paper ' || md5(g::text) || ' on '
           || (ARRAY['graph networks', 'protein folding', 'quantum codes', 'climate models'])[1 + g % 4],
       '10.9999/bench.' || g,
       DATE '2020-01-01' + (g % 2000)
FROM generate_series(1, 200000) AS g;
ANALYZE publications;

\echo '=== BEFORE: no trigram index ==='
EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM publications
WHERE title ILIKE '%' || substr(md5('777'), 1, 8) || '%'
ORDER BY id DESC LIMIT 21;

CREATE INDEX ix_publications_title_trgm ON publications USING gin (title gin_trgm_ops);
ANALYZE publications;

\echo '=== AFTER: GIN trigram index ==='
EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM publications
WHERE title ILIKE '%' || substr(md5('777'), 1, 8) || '%'
ORDER BY id DESC LIMIT 21;

ROLLBACK;
