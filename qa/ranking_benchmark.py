"""Compare the previous all-kind window scan to SQL kind filtering on the same synthetic data."""
from contextlib import closing
from datetime import date, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from math import ceil
from pathlib import Path
from statistics import median
from time import perf_counter
import json
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "fd24ec8240cffb4e83dd269bbf8b752bb6186b32"
sys.path.insert(0, str(ROOT))
import analytics
import server


def prior_server(directory):
    """Load the release's ranking, export and CSV code alongside the working tree."""
    modules = {}
    for name in ("analytics", "export_jobs", "server"):
        path = directory / (name + ".py")
        path.write_bytes(subprocess.check_output(["git", "show", f"{BASELINE}:{path.name}"], cwd=ROOT))
        spec = spec_from_file_location("benchmark_prior_" + name, path)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        modules[name] = module
    modules["export_jobs"].analytics = modules["analytics"]
    modules["server"].analytics = modules["analytics"]
    modules["server"].export_jobs = modules["export_jobs"]
    return modules["server"]


def fixtures():
    start = date(2026, 1, 1)
    for day in range(75):
        for group, kind in enumerate(analytics.KINDS):
            for i in range(300):
                yield {"kind":kind, "market":"US", "id":f"s{i:03}", "name":f"Item {i:03}",
                       "date":(start + timedelta(days=day)).isoformat(),
                       "category":"New > A" if day >= 72 else "Old", "segment":"last" if day >= 72 else "prior",
                       "gmv":(i%6+1)*(day%3+1)*(group+1), "sales":i%6+1, "views":None if i%4 == 0 else 40}


def benchmark(db, prior):
    db.row_factory = sqlite3.Row
    db.executescript(analytics.SCHEMA)
    with db:
        analytics.import_rows(db, fixtures(), "benchmark", shared=True)
    db.execute("ANALYZE")
    base = {"source":"benchmark", "market":"US", "date":"2026-03-16"}

    def run(params, baseline, *, export=False):
        implementation = prior if baseline else server
        if export:
            return implementation.csv_export(db, params)
        return implementation.analytics.handle(db, "/api/rankings", params)

    filters = ({}, {"category":"New","segment":"last","sort":"growth","limit":19,"page":2},
               {"category":"Old"}, {"sort":"views","q":"Item 1","min_gmv":5,"limit":14})
    checked = 0
    for kind in analytics.KINDS:
        for days in (7, 30):
            for extra in filters:
                params = {**base, "days":days, "kind":kind, **extra}
                assert run(params, True) == run(params, False), params
                assert run(params, True, export=True) == run(params, False, export=True), params
                checked += 1

    timings = []
    for days in (7, 30):
        params = {**base, "kind":"products", "days":days, "limit":20}
        samples = {True:[], False:[]}
        for mode in samples:
            run(params, mode)
        for i in range(20):
            for mode in (True, False) if i%2 == 0 else (False, True):
                start = perf_counter()
                run(params, mode)
                samples[mode].append((perf_counter()-start)*1000)
        for mode, values in samples.items():
            timings.append({"days":days, "scan":"all_kinds" if mode else "selected_kind",
                            "p50_ms":round(median(values),2), "p95_ms":round(sorted(values)[ceil(.95*len(values))-1],2)})
    return {"baseline":BASELINE, "facts":db.execute("SELECT COUNT(*) FROM analytics_daily").fetchone()[0], "samples_per_case":20,
            "ranking_and_csv_cases":checked, "python":sys.version.split()[0], "sqlite":sqlite3.sqlite_version, "timings":timings}


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp, closing(sqlite3.connect(Path(tmp)/"bench.db")) as db:
        print(json.dumps(benchmark(db, prior_server(Path(tmp))), indent=2))
