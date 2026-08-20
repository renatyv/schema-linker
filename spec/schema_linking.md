# Schema Linking
Goal: find join-candidate column pairs across tables without scanning every column at full cost.

# Expected Result
A separate `.md` file with potential links:
- PK/FK connections. Omitted from the output by default to save tokens; surfaced with `--show-declared-links`. Declared links are always used internally to group inferred links.
- Advanced search for additional schema links, using the pipeline described below.

# Advanced Schema-Linking Pipeline
## Stage 0: Metadata Pass
- FK-constrained columns: the join is already known, so skip them.
- Mismatched data types: exclude the pair from consideration.

## Stage 1: Cheap Cardinality Estimate
```sql
SELECT COUNT(DISTINCT col), COUNT(*) FROM table;
```
Fallback to `TABLESAMPLE`/modulo sampling if too slow; flag as approximate.

## Stage 2: Triage by Cardinality Ratio
| Ratio (distinct/rows) | Action |
|---|---|
| ≈ 1.0, not declared PK | Drop (unstructured/unique text) |
| Very low (enum-like) | Keep, low priority (false-positive prone) |
| Moderate, ID-like | Primary target; continue to Stage 3 |

## Stage 3: Name/Type Pre-Filter
Trigram/Levenshtein on column names + dtype match.
- Strong match: tentative join; spot-check with a small sample.
- No signal: continue to Stage 4.

## Stage 4: Full DISTINCT Extraction
Only on columns surviving Stage 2–3:
```sql
SELECT DISTINCT col FROM table;
```
Columns with more distinct values than `--max-distinct-values` (default 10,000) are not extracted; pairs touching them fall through to the exact SQL check in Stage 6 instead.

## Stage 5: MinHash + LSH Ensemble
Use the `datasketch` Python library.
- MinHash signature per column (128–256 permutations).
- `datasketch.MinHashLSHEnsemble`, partitioned by set size.
- Query containment (asymmetric, not Jaccard — handles unequal cardinalities).
- Threshold, for example `> 0.8`: candidate pair.

## Stage 6: Verification
Exact containment check on the (now small) distinct sets:
```sql
SELECT COUNT(*) FROM (
  SELECT DISTINCT a.col FROM t1 a
  WHERE a.col NOT IN (SELECT col FROM t2)
) x;
```
Confirms or rejects LSH candidates; catches approximation false positives. When either column was not loaded into memory (distinct count above the cap), the exact containment is computed in SQL as an anti-join instead of being skipped, so oversized-but-real relationships are still found.

Pairs where both columns are boolean/flag domains (at most two distinct values, or values drawn from 0/1, Y/N, true/false, yes/no) are dropped unless one side is a primary/unique key: joining two independent flags is a cross-product trap, not a join path.

Do not include inferred links if they have fewer than three pieces of evidence. Sort inferred links by evidence: more evidence ranks higher in the list.

Evidence labels are omitted from the output by default to save tokens. They can be surfaced on demand with the `--show-evidence` flag, which attaches the supporting evidence to each inferred column. Evidence is pairwise, so it is shown per column (from that column's strongest inferred edge) rather than aggregated across the whole cluster, which would merge mutually-exclusive cardinality labels and lose the link to a specific column.

The Declared PK/FK Links section is omitted from the output by default to save tokens. It can be surfaced on demand with the `--show-declared-links` flag. Declared links are always used to group inferred links regardless of whether the section is shown, so the inferred clustering is unaffected.

Inferred links are grouped by shared value domain: columns that join to the same primary key (or simply share a value set) form one cluster. Each cluster is headed by its anchor primary key when one exists; members already covered by a declared FK are listed separately as context, and only genuinely new inferred columns are the signal. Clusters whose every column is already declared are omitted because they add no new information. The pairwise explosion from transitive containment is collapsed this way.

Output example (`--show-declared-links` adds the first section; by default only the inferred links below are written):
```
- version: 0.1.0
- dialect: mariadb
- database: dive_sim

## Declared PK/FK Links

action_status_history.action_history_id -> action_history.id
action_status_history.state_history_id -> robot_state_history.id

## Inferred Links

### robot.id
- inferred: action_history.robot_id, box_movement_history.robot_id, move_robot.robot_id
- declared: box.held_by_robot_id
```

With `--show-evidence`, each inferred column carries the evidence from its strongest edge:
```
### robot.id
- inferred:
  - action_history.robot_id: name match, table-name id match, type match
  - box_movement_history.robot_id: name match, shared name tokens, type match
  - move_robot.robot_id: minhash containment candidate, moderate ID-like cardinality, type match
- declared: box.held_by_robot_id
```
