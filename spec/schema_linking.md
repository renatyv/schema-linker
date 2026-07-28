# Schema Linking
Goal: find join-candidate column pairs across tables without scanning every column at full cost.

# Expected Result
A separate `.md` file with potential links:
- PK/FK connections.
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
Confirms or rejects LSH candidates; catches approximation false positives.

Do not include inferred links if they have fewer than three pieces of evidence. Sort inferred links by evidence: more evidence ranks higher in the list.

Output example:
```
- version: 0.1.0
- dialect: mariadb
- database: dive_sim

## Declared PK/FK Links

| From | To |
|---|---|
| action_status_history.action_history_id | action_history.id |
| action_status_history.state_history_id | robot_state_history.id |


## Inferred Links

| From | To | Evidence |
|---|---|---|
| action_history.robot_id | box_movement_history.robot_id | minhash containment candidate, name match, shared name tokens, similar names, type match |
| action_history.robot_id | move_robot.robot_id | minhash containment candidate, name match, shared name tokens, similar names, type match |
```
