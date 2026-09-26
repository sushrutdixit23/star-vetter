import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

# Runs the whole F1->F5 pipeline on one fresh batch of candidates, unattended.
#
# Each stage below is one of the existing scripts, run exactly as you'd run it
# by hand (py <script> <project_root>) - the orchestrator does not re-implement
# any vetting logic, it just sequences the scripts you already validated one at
# a time this session, and narrates why it's moving from one to the next.
#
# Two things needed patching before they can run back-to-back unattended:
#
#   1. diag_blend.py (the catalog-based contamination check) still reads the
#      old f4e_novelty_results.csv. The current script is f4f_novelty.py, which
#      writes f4f_novelty_results.csv. Patched once, idempotently, at startup.
#
#   2. diag_pixel.py (the pixel-level check) only pixel-checks its top N_TOP
#      candidates by BLS SNR. The validated policy this session is to pixel-
#      check EVERY novel, non-contaminated candidate - catalog cross-matching
#      alone missed about half of the real contamination cases found earlier
#      this session, and pixel imaging is the only independent ground truth.
#      N_TOP is patched up to effectively "all" at startup.
#
# Retries: every stage below writes its own results incrementally (a resumable
# CSV or manifest that skips rows already done) - that was already true of
# every script before this orchestrator existed. So a "retry" here is just
# re-invoking the same script; it picks up wherever the failed attempt left
# off instead of redoing completed work.
#
# RUN RECORDS (new): this run's story - what changed versus everything on
# disk before it started, per-stage timing, and any timeout/skip events - is
# written to data/runs/<run_id>.json regardless of how the run ends (clean
# finish, "nothing new to sample", or a stage failing after all retries).
# That file is the single source of truth the website's run history and
# "last run" panel read from; nothing there is parsed back out of this log.

MAX_RETRIES = 3
RETRY_DELAY_SEC = 20


def make_logger(logf):
    def log(msg):
        print(msg)
        logf.write(msg + "\n")
        logf.flush()

    def decision(msg):
        log("[ORCHESTRATOR] Decision: " + msg)

    return log, decision


def get_commit_sha(project_root):
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(project_root), capture_output=True, text=True, timeout=10,
        )
        sha = out.stdout.strip()
        return sha if out.returncode == 0 and sha else None
    except Exception:
        return None


def ensure_patches(project_root, log):
    log("\n" + "=" * 78)
    log("STAGE 0: checking the pipeline scripts are self-consistent")
    log("=" * 78)

    blend_path = project_root / "diag_blend.py"
    s = blend_path.read_text(encoding="utf-8")
    old = '    nov = pd.read_csv(proc / "f4e_novelty_results.csv")\n'
    new = '    nov = pd.read_csv(proc / "f4f_novelty_results.csv")\n'
    if new in s:
        log("  diag_blend.py already reads f4f_novelty_results.csv - OK.")
    elif s.count(old) == 1:
        blend_path.write_text(s.replace(old, new), encoding="utf-8", newline="\n")
        log("  Patched diag_blend.py to read f4f_novelty_results.csv (was the old "
            "f4e_novelty_results.csv).")
    else:
        log(f"  ERROR: diag_blend.py's novelty-file read line has changed unexpectedly "
            f"(expected 1 match, found {s.count(old)}). Not patching automatically - "
            f"check the file by hand.")
        sys.exit(1)

    pixel_path = project_root / "diag_pixel.py"
    s = pixel_path.read_text(encoding="utf-8")
    old = "N_TOP = 20\n"
    new = "N_TOP = 10000   # all NOVEL candidates (was 20)\n"
    if "N_TOP = 10000" in s:
        log("  diag_pixel.py already checks all NOVEL candidates - OK.")
    elif s.count(old) == 1:
        pixel_path.write_text(s.replace(old, new), encoding="utf-8", newline="\n")
        log("  Patched diag_pixel.py to pixel-check all NOVEL candidates (was top 20 by SNR).")
    else:
        log(f"  ERROR: diag_pixel.py's N_TOP line has changed unexpectedly "
            f"(expected 1 match, found {s.count(old)}). Not patching automatically - "
            f"check the file by hand.")
        sys.exit(1)


def run_stage(name, script_name, project_root, log, logf):
    """Runs one stage script, retrying whole-script failures up to
    MAX_RETRIES times. Returns (ok, elapsed_seconds, attempts) - the run
    record needs the timing and retry count, not just pass/fail."""
    script_path = project_root / script_name
    if not script_path.exists():
        log(f"  ERROR: {script_path} not found. Stopping.")
        return False, 0.0, 0

    args = [sys.executable, str(script_path), str(project_root)]
    total_elapsed = 0.0
    for attempt in range(1, MAX_RETRIES + 1):
        log("\n" + "=" * 78)
        log(f"STAGE: {name}   (attempt {attempt}/{MAX_RETRIES})")
        log("=" * 78)
        log("  running: " + " ".join(args))
        start = time.time()
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, bufsize=1, cwd=str(project_root))
        for line in proc.stdout:
            print("  " + line.rstrip())
            logf.write("  " + line)
        logf.flush()
        proc.wait()
        elapsed = time.time() - start
        total_elapsed += elapsed

        if proc.returncode == 0:
            log(f"  -> {name} finished OK in {elapsed / 60:.1f} min")
            return True, total_elapsed, attempt

        log(f"  -> {name} FAILED (exit code {proc.returncode}) after {elapsed / 60:.1f} min")
        if attempt < MAX_RETRIES:
            log(f"  Retrying in {RETRY_DELAY_SEC}s ({name} checkpoints its own progress, so "
                f"this only redoes whatever was unfinished, not the whole stage).")
            time.sleep(RETRY_DELAY_SEC)

    log(f"  {name} failed {MAX_RETRIES} times in a row. Stopping the pipeline here - the "
        f"remaining stages all depend on this one's output.")
    return False, total_elapsed, MAX_RETRIES


def read_csv_safe(path):
    return pd.read_csv(path) if path.exists() else None


def snapshot_cumulative(proc):
    """Reads the same four result files export_pipeline_stats.py reads, and
    returns the same six-stage funnel counts, cumulative across every batch
    ever run - this is called once before this run's stages touch anything
    (the 'baseline') and once after (the 'after' totals), so the run record
    can report what THIS run actually added, not just the running total."""
    manifest = read_csv_safe(proc / "f2c_manifest.csv")
    vet = read_csv_safe(proc / "f3i_vetting_results.csv")
    nov = read_csv_safe(proc / "f4f_novelty_results.csv")
    pix = read_csv_safe(proc / "diag_pixel_results_v2.csv")

    sampled = int(len(manifest)) if manifest is not None else 0
    fetch_ok = int((manifest["status"] == "OK").sum()) if manifest is not None else 0
    passing = 0
    if vet is not None and "status" in vet.columns:
        passing = int(((vet["status"] == "OK") & (vet["depth_flagged_implausible"] == False)).sum())
    novel = int((nov["verdict"] == "NOVEL").sum()) if nov is not None else 0
    pixel_checked, confirmed = 0, 0
    if pix is not None and "role" in pix.columns:
        cand = pix[pix["role"] == "candidate"]
        pixel_checked = int(len(cand))
        confirmed = int((cand["verdict"] == "ON_TARGET").sum())

    return {
        "targets_sampled": sampled,
        "usable_light_curves": fetch_ok,
        "statistically_passing": passing,
        "novel_candidates": novel,
        "pixel_checked": pixel_checked,
        "confirmed": confirmed,
    }


def batch_fetch_events(proc, batch_tics):
    """Looks at f2c_manifest.csv rows for just the TICs sampled THIS run and
    separates them into timeouts (the search/download call itself hit its
    hard wall-clock deadline - see f2c_fetch_lightcurves.py's
    SEARCH_TIMEOUT_SEC/DOWNLOAD_TIMEOUT_SEC) versus every other kind of
    skip (no TESS data, a bad FITS file, etc). Returns two lists of small
    dicts, each capped at 25 entries so a bad batch can't blow up the run
    record's file size - the counts are still exact, only the example list
    is capped."""
    manifest = read_csv_safe(proc / "f2c_manifest.csv")
    if manifest is None:
        return [], []
    batch = manifest[manifest["TIC"].astype(int).isin(batch_tics)]
    failed = batch[batch["status"] != "OK"]

    timeouts, skipped = [], []
    for _, row in failed.iterrows():
        err = str(row.get("error", "") or "")
        entry = {"tic": int(row["TIC"]), "status": str(row["status"]), "message": err[:200]}
        if "did not respond within" in err or "did not finish within" in err:
            timeouts.append(entry)
        else:
            skipped.append(entry)
    return timeouts, skipped


def main():
    if len(sys.argv) != 2:
        print("Usage: py f6_orchestrator.py <project_root>")
        sys.exit(1)

    project_root = Path(sys.argv[1]).resolve()
    proc = project_root / "data" / "processed"
    logs_dir = project_root / "data" / "logs"
    runs_dir = project_root / "data" / "runs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"orchestrator_{ts}.log"
    run_record_path = runs_dir / f"{ts}.json"

    run_id = ts
    started_at = datetime.datetime.now(datetime.timezone.utc)
    record = {
        "run_id": run_id,
        "commit_sha": get_commit_sha(project_root),
        "log_file": log_path.name,
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": None,
        "duration_seconds": None,
        "status": "in_progress",
        "stages": [],
        "this_run": None,
        "cumulative_before": None,
        "cumulative_after": None,
        "timeouts": [],
        "skipped": [],
    }
    run_start_time = time.time()

    def finalize(status, log):
        record["status"] = status
        record["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        record["duration_seconds"] = round(time.time() - run_start_time, 1)
        record["cumulative_after"] = snapshot_cumulative(proc)
        before = record["cumulative_before"] or {k: 0 for k in record["cumulative_after"]}
        after = record["cumulative_after"]
        record["this_run"] = {
            "new_sampled": after["targets_sampled"] - before["targets_sampled"],
            "new_usable_light_curves": after["usable_light_curves"] - before["usable_light_curves"],
            "new_confirmed": after["confirmed"] - before["confirmed"],
        }
        run_record_path.write_text(
            json.dumps(record, indent=2, allow_nan=False), encoding="utf-8", newline="\n",
        )
        log(f"\nRun record written: {run_record_path}")

    with open(log_path, "w", encoding="utf-8", newline="\n") as logf:
        log, decision = make_logger(logf)

        log("=" * 78)
        log("STAR VETTER ORCHESTRATOR - unattended F1 -> F5 run")
        log(f"Project root: {project_root}")
        log(f"Started:      {datetime.datetime.now().isoformat(timespec='seconds')}")
        log(f"Log file:     {log_path}")
        log(f"Run ID:       {run_id}")
        log("=" * 78)

        record["cumulative_before"] = snapshot_cumulative(proc)

        try:
            ensure_patches(project_root, log)
        except SystemExit:
            finalize("failed", log)
            raise

        def do_stage(name, script_name):
            ok, elapsed, attempts = run_stage(name, script_name, project_root, log, logf)
            record["stages"].append({
                "name": name, "script": script_name, "ok": ok,
                "elapsed_seconds": round(elapsed, 1), "attempts": attempts,
            })
            if not ok:
                finalize("failed", log)
                sys.exit(1)

        # ---- F1b: draw a new stratified sample, excluding every prior batch ----
        do_stage("F1b sample new targets", "f1b_sample.py")
        sample = read_csv_safe(proc / "sample_500.csv")
        if sample is None:
            decision("f1b_sample.py did not produce a sample file. Stopping.")
            finalize("failed", log)
            sys.exit(1)
        if len(sample) == 0:
            decision("Drew 0 new targets - every candidate in the unvetted table has already "
                      "been sampled in a prior batch. Nothing new to process this run.")
            log("\nOrchestrator run complete (no new targets).")
            finalize("no_new_targets", log)
            return
        decision(f"Drew {len(sample)} new stratified targets for this batch. "
                 f"Proceeding to fetch their light curves.")
        batch_tics = set(sample["TIC"].astype(int))

        # ---- F2c: fetch light curves for the batch ----
        do_stage("F2c fetch light curves", "f2c_fetch_lightcurves.py")
        manifest = read_csv_safe(proc / "f2c_manifest.csv")
        if manifest is not None:
            batch_manifest = manifest[manifest["TIC"].astype(int).isin(batch_tics)]
            ok_fetch = int((batch_manifest["status"] == "OK").sum())
            ok_total = int((manifest["status"] == "OK").sum())
        else:
            ok_fetch = 0
            ok_total = 0
        timeouts, skipped = batch_fetch_events(proc, batch_tics)
        record["timeouts"] = timeouts[:25]
        record["skipped"] = skipped[:25]
        record["timeouts_total"] = len(timeouts)
        record["skipped_total"] = len(skipped)
        if timeouts:
            decision(f"{len(timeouts)} target(s) in this batch hit F2c's hard timeout "
                     f"(search or download did not respond in time) and were skipped without "
                     f"blocking the rest of the batch.")
        decision(f"{ok_fetch}/{len(sample)} of this batch fetched a usable light curve (the "
                 f"rest were never observed by TESS or had unusable FITS data). {ok_total} light "
                 f"curve(s) are on disk in total across every batch to date. Proceeding to vet "
                 f"every light curve on disk, this batch plus any earlier ones not yet vetted.")

        # ---- F3i: BLS vetting ----
        do_stage("F3i vet light curves", "f3i_vet.py")
        vet = read_csv_safe(proc / "f3i_vetting_results.csv")
        trustworthy = vet[(vet["status"] == "OK") & (vet["depth_flagged_implausible"] == False)]
        decision(f"{len(trustworthy)}/{len(vet)} vetted stars (all batches to date) are "
                 f"trustworthy eclipsing-binary detections that passed every physical and "
                 f"statistical gate. Proceeding to check which of those are already known.")

        # ---- F4f pass 1: catalog cross-match, before the contamination check exists ----
        do_stage("F4f novelty cross-match (pass 1 of 2)", "f4f_novelty.py")
        nov1 = read_csv_safe(proc / "f4f_novelty_results.csv")
        n_novel_1 = int((nov1["verdict"] == "NOVEL").sum())
        decision(f"{n_novel_1} trustworthy detection(s) match no known variable-star catalog. "
                 f"That alone is not enough to call them new: a novel catalog match can still "
                 f"be light from a known variable star nearby, leaking into this star's "
                 f"aperture. Running the neighbour-contamination check next.")

        # ---- diag_blend: catalog-based contamination check ----
        do_stage("Neighbour contamination check", "diag_blend.py")
        blend = read_csv_safe(proc / "diag_blend_results.csv")
        n_contam = (int((blend["blend_status"] == "LIKELY_CONTAMINATION").sum())
                    if blend is not None else 0)
        decision(f"{n_contam} novel detection(s) have a known variable neighbour close enough "
                 f"and bright enough to plausibly be the true source. Re-running the novelty "
                 f"pass so these get relabelled CONTAMINATED before anything goes to the "
                 f"pixel-level check.")

        # ---- F4f pass 2: re-run now that diag_blend_results.csv exists ----
        do_stage("F4f novelty cross-match (pass 2 of 2, applies contamination)", "f4f_novelty.py")
        nov2 = read_csv_safe(proc / "f4f_novelty_results.csv")
        n_novel_2 = int((nov2["verdict"] == "NOVEL").sum())
        decision(f"{n_novel_2} detection(s) remain NOVEL after the contamination check "
                 f"({n_contam} were relabelled CONTAMINATED). Escalating ALL {n_novel_2} of "
                 f"them to the pixel-level check - not just the strongest few by signal-to-"
                 f"noise. The catalog check above only catches a neighbour that is already in "
                 f"a known-variable catalog; it cannot see an unlisted one. Only a pixel-level "
                 f"difference-image check can confirm the dimming is actually centred on this "
                 f"star, so every survivor gets checked.")

        # ---- diag_pixel: pixel-level difference-imaging check (ground truth) ----
        do_stage("Pixel-level source check", "diag_pixel.py")
        pix = read_csv_safe(proc / "diag_pixel_results_v2.csv")
        cand = pix[pix["role"] == "candidate"] if pix is not None else None
        on_target = int((cand["verdict"] == "ON_TARGET").sum()) if cand is not None else 0
        if cand is not None:
            counts = ", ".join(f"{v}: {c}" for v, c in cand["verdict"].value_counts().items())
            decision(f"Pixel-check verdicts across all candidates checked to date -> {counts}. "
                     f"{on_target} confirmed ON_TARGET (dimming centred on this star, not a "
                     f"neighbour). Building dossiers for those.")
        else:
            decision("No pixel-check results file was produced. Stopping before F5.")
            finalize("failed", log)
            sys.exit(1)

        if on_target == 0:
            decision("No ON_TARGET candidates yet - skipping F5, there is nothing to build a "
                     "dossier for. This is a legitimate outcome, not a failure: it can mean "
                     "this batch had no real detections, or that TESScut does not yet have "
                     "pixel data for the sectors involved.")
            log("\nOrchestrator run complete (no dossiers this run).")
            finalize("no_dossiers", log)
            return

        # ---- F5: dossiers for every confirmed candidate to date ----
        do_stage("F5 build dossiers", "f5_dossier.py")
        decision(f"Wrote dossiers for {on_target} confirmed candidate(s) to data/dossiers/.")

        log("\n" + "=" * 78)
        log("ORCHESTRATOR RUN COMPLETE")
        log(f"Finished: {datetime.datetime.now().isoformat(timespec='seconds')}")
        log("=" * 78)
        finalize("completed", log)


if __name__ == "__main__":
    main()