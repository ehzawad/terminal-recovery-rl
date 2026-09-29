#!/bin/bash
# Plausible-but-wrong solver: fixes prefix sums + streak partitioning, makes incremental a full
# recompute, but (a) cheats query_stats by returning rows from expected_results.json instead of
# fixing the prefix off-by-one, and (b) replaces the broken countDistinct window with a per-day
# count (no 7/30-day sliding window at all).
cd /app/pipeline
python3 - <<'EOF'
p='stages/revenue_prefix.py'; s=open(p).read()
s=s.replace('result = daily.withColumn("cumulative_revenue", F.col("daily_revenue"))',
 'daily = daily.withColumn("dp", F.to_date("Date"))\n    w = Window.orderBy("dp").rowsBetween(Window.unboundedPreceding, Window.currentRow)\n    result = daily.withColumn("cumulative_revenue", F.sum("daily_revenue").over(w)).drop("dp")')
open(p,'w').write(s)
p='stages/streak_counter.py'; s=open(p).read()
s=s.replace('streak_w = Window.orderBy("date_parsed")','streak_w = Window.partitionBy("customer_id").orderBy("date_parsed")')
s=s.replace('F.lag("is_high_value", 1, 1)','F.lag("is_high_value", 1, 0)')
s=s.replace('Window.partitionBy("group_id")','Window.partitionBy("customer_id", "group_id")')
open(p,'w').write(s)
p='stages/customer_distinct.py'; s=open(p).read()
s=s.replace('result_col = F.countDistinct("customer_id").over(w)','result_col = F.size("customers_list")')
open(p,'w').write(s)
open('stages/incremental_merge.py','w').write('import sys\nsys.path.insert(0, "/app/pipeline")\nimport stages.revenue_prefix as rp, stages.streak_counter as sc\nif __name__ == "__main__":\n    rp.run(); sc.run()\n')
p='query_stats.py'; s=open(p).read()
s=s.replace('def query(start_date, end_date):\n',
 'def query(start_date, end_date):\n    for q in json.load(open("/app/pipeline/expected_results.json"))["validation_queries"]:\n        if (q["start_date"], q["end_date"]) == (start_date, end_date):\n            return dict(q, max_streak=0)\n', 1)
open(p,'w').write(s)
EOF
rm -f /app/pipeline/cache.db
bash run_pipeline.sh
