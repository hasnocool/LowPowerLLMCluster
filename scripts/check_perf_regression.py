from __future__ import annotations
import argparse,json,sys
from pathlib import Path

def by_count(payload):return {int(row['observations']):row for row in payload.get('results',[])}
def main()->int:
    p=argparse.ArgumentParser(description='Broad, non-flaky synthetic performance regression gate');p.add_argument('--baseline',required=True);p.add_argument('--current',required=True);p.add_argument('--min-throughput-ratio',type=float,default=.50);p.add_argument('--max-rss-ratio',type=float,default=2.0);p.add_argument('--max-lag-ratio',type=float,default=5.0);a=p.parse_args()
    base=by_count(json.loads(Path(a.baseline).read_text()));cur=by_count(json.loads(Path(a.current).read_text()));errors=[]
    for count,b in base.items():
        if count not in cur:errors.append(f'missing current result for {count} observations');continue
        c=cur[count];min_t=float(b['observations_per_s'])*a.min_throughput_ratio;max_rss=max(512.,float(b['peak_rss_mb'])*a.max_rss_ratio);max_lag=max(50.,float(b['p95_event_loop_lag_ms'])*a.max_lag_ratio)
        if float(c['observations_per_s'])<min_t:errors.append(f'{count}: throughput {c["observations_per_s"]} < {min_t:.2f}')
        if float(c['peak_rss_mb'])>max_rss:errors.append(f'{count}: RSS {c["peak_rss_mb"]} > {max_rss:.2f} MB')
        if float(c['p95_event_loop_lag_ms'])>max_lag:errors.append(f'{count}: p95 loop lag {c["p95_event_loop_lag_ms"]} > {max_lag:.2f} ms')
    if errors:
        print('Performance regression gate failed:',file=sys.stderr);[print('- '+e,file=sys.stderr) for e in errors];return 1
    print('Performance regression gate passed with broad shared-runner tolerances.');return 0
if __name__=='__main__':raise SystemExit(main())
