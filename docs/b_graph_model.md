# Neo4j model and PageRank (member B, notes for report sections 4-6)

## Model
```
(Author)-[:WROTE]->(Work)-[:IN_GENRE]->(Genre)
(Author)-[:INFLUENCED_BY]->(Author)   X was influenced by Y   (Wikidata P737)
(Author)-[:STUDENT_OF]->(Author)      X was a student of Y    (Wikidata P1066)
```
Both influence links point to the person who influenced (or taught). Authors that appear only
in influence links (for example Socrates) have `external = true` and no works.
Constraints: `id` is unique for Author and Work, `name` is unique for Genre.

## Why a graph database
"How is X connected to Y?" is a variable-length path query. In Neo4j it is one line
(`shortestPath((a)-[:INFLUENCED_BY|STUDENT_OF*..8]-(b))`). In SQL it needs a recursive CTE
and its cost grows with the depth (this is what benchmark B8 measures).

## PageRank
PR(v) = (1-d)/N + d * sum over u->v of PR(u)/L(u), with d = 0.85.
Links point to the influencer, so an author gets a high score when many authors, who are
themselves important, were influenced by them. Authors without links give their score to
everyone (dangling nodes). The scores sum to 1. We compute it in Python (power iteration,
stops when the change is below 1e-10) on the links read from Neo4j. The Graph Data Science
plugin is not needed.

## Sources of the links
1. `curated`: hand-written, well known teacher and student links.
2. `wikidata`: SPARQL query (P737, P1066), namesakes removed with the birth year.
3. `generated`: shared subjects or genre, older author first (fallback, a heuristic, not history).
The field `origin` is stored on every link so the report can say how many come from each source.
