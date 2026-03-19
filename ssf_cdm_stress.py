#!/usr/bin/env python3
"""
SSF CDM-side stress tester.
Runs on the CDM node. Discovers all ONLINE envoys from Cassandra,
then SSHes to each envoy through the SSF tunnel in parallel threads
to stress the tunnel from the server side.

Works with any number of envoys — each gets its own pool of worker threads.

Usage:
    # Run default command on all envoys (default: ls -lrt /var/crash)
    python3 ssf_cdm_stress.py

    # Custom command
    python3 ssf_cdm_stress.py --command "df -h"

    # 20 parallel workers per envoy, run for 5 minutes
    python3 ssf_cdm_stress.py --workers 20 --duration 300

    # Target a specific envoy by hostname
    python3 ssf_cdm_stress.py --envoy-hostname my-envoy-host

    # Verbose per-command output
    python3 ssf_cdm_stress.py -v
"""

import argparse
import logging
import os
import subprocess
import sys
import threading
import time

# sdmain path setup — same as envoy_ng_tool.py
SDMAIN_ROOT = '/opt/rubrik'
sys.path.append(os.path.join(SDMAIN_ROOT, 'src'))
from py.utils.cassandra_query_executor import CassandraQueryExecutor  # noqa: E402

SSH_PRIV_KEY    = '/var/lib/rubrik/certs/envoy_ng/envoy_ng_ssh.pem'
SSH_USER        = 'ubuntu'
SSH_HOST        = '127.128.0.1'
DEFAULT_COMMAND = 'ls -lrt /var/crash'
DEFAULT_TIMEOUT = 20


# ---------------------------------------------------------------------------
# Envoy discovery (mirrors get_envoys_info from envoy_ng_tool.py)
# ---------------------------------------------------------------------------

def get_envoys(envoy_hostname=None):
    """
    Query Cassandra envoy_config table and return a list of dicts for all
    ONLINE envoys (or a specific one if envoy_hostname is given).

    Each dict has: envoy_uuid, envoy_hostname, envoy_ip, ssh_port
    """
    log = logging.getLogger("discover")
    statement = "SELECT * FROM envoy_config"
    if envoy_hostname:
        statement = (
            "SELECT * FROM envoy_config WHERE envoy_hostname='{}'".format(
                envoy_hostname
            )
        )

    envoys = []
    try:
        with CassandraQueryExecutor() as cassandra:
            rows = cassandra.execute(statement)
            for row in rows:
                if row.envoy_status != 'ONLINE':
                    log.warning(
                        "Skipping envoy {} — status: {}".format(
                            row.envoy_hostname, row.envoy_status
                        )
                    )
                    continue
                envoys.append({
                    "envoy_uuid":     row.envoy_uuid,
                    "envoy_hostname": row.envoy_hostname,
                    "envoy_ip":       row.envoy_ip,
                    "ssh_port":       row.ssh_pfp_assignment,
                })
    except Exception as e:
        log.error("Failed to query Cassandra: {}".format(e))

    return envoys


# ---------------------------------------------------------------------------
# SSH command runner (mirrors envoy_cmd_execute from envoy_ng_tool.py)
# ---------------------------------------------------------------------------

def run_envoy_command(ssh_port, command, timeout_sec):
    """
    SSH to the envoy through the SSF tunnel and run a command.
    Returns (exit_code: int, stdout: str, stderr: str).
    """
    cmd = [
        'sudo', 'ssh',
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'ConnectTimeout={}'.format(timeout_sec),
        '-i', SSH_PRIV_KEY,
        '-p', str(ssh_port),
        '{}@{}'.format(SSH_USER, SSH_HOST),
        command,
    ]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=timeout_sec + 2,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, '', 'timeout after {}s'.format(timeout_sec)
    except Exception as e:
        return 1, '', str(e)


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------

def worker_loop(worker_id, envoy_hostname, ssh_port, command,
                iterations, delay, timeout_sec,
                counters, counters_lock, stop_event):
    """
    One worker thread: repeatedly SSH to one envoy and run the command.
    iterations=0 means run until stop_event is set.
    """
    log = logging.getLogger("worker-{}-{}".format(envoy_hostname, worker_id))
    i = 0
    while not stop_event.is_set():
        t_start = time.time()
        rc, stdout, stderr = run_envoy_command(ssh_port, command, timeout_sec)
        elapsed = time.time() - t_start
        success = (rc == 0)

        with counters_lock:
            counters["total"] += 1
            if success:
                counters["ok"] += 1
            else:
                counters["fail"] += 1

        if success:
            log.debug(
                "run #{} port={} rc={} elapsed={:.2f}s output={}".format(
                    i + 1, ssh_port, rc, elapsed, repr(stdout[:120])
                )
            )
        else:
            log.warning(
                "run #{} port={} rc={} elapsed={:.2f}s error={}".format(
                    i + 1, ssh_port, rc, elapsed, repr(stderr[:120])
                )
            )

        i += 1
        if iterations > 0 and i >= iterations:
            break

        if delay > 0:
            time.sleep(delay)


# ---------------------------------------------------------------------------
# Reporter thread
# ---------------------------------------------------------------------------

def reporter_loop(counters, counters_lock, stop_event, interval=5):
    """Print a running summary every `interval` seconds."""
    log = logging.getLogger("reporter")
    start = time.time()
    while not stop_event.is_set():
        time.sleep(interval)
        with counters_lock:
            total = counters["total"]
            ok    = counters["ok"]
            fail  = counters["fail"]
        elapsed = time.time() - start
        rate = total / elapsed if elapsed > 0 else 0
        log.info(
            "[{:.0f}s] total={} ok={} fail={} rate={:.1f}/s".format(
                elapsed, total, ok, fail, rate
            )
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="SSF CDM-side stress tester — SSHes to all ONLINE envoys "
                    "through the SSF tunnel in parallel threads"
    )
    parser.add_argument(
        "--command", default=DEFAULT_COMMAND,
        help="Command to run on each envoy via SSH "
             "(default: '{}')".format(DEFAULT_COMMAND)
    )
    parser.add_argument(
        "--envoy-hostname", default=None,
        help="Target a specific envoy by hostname; "
             "default: all ONLINE envoys"
    )
    parser.add_argument(
        "--workers", type=int, default=10,
        help="Parallel worker threads per envoy (default: 10)"
    )
    parser.add_argument(
        "--iterations", type=int, default=0,
        help="Runs per worker; 0=run forever (default: 0)"
    )
    parser.add_argument(
        "--delay", type=float, default=0,
        help="Sleep between runs per worker in sec (default: 0)"
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT,
        help="SSH command timeout in sec (default: {})".format(DEFAULT_TIMEOUT)
    )
    parser.add_argument(
        "--duration", type=int, default=0,
        help="Stop after N seconds; 0=run until Ctrl+C (default: 0)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable per-run debug logging"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("main")

    # Discover envoys
    envoys = get_envoys(envoy_hostname=args.envoy_hostname)
    if not envoys:
        log.error("No ONLINE envoys found — check Cassandra envoy_config table.")
        sys.exit(1)

    log.info("Discovered {} ONLINE envoy(s):".format(len(envoys)))
    for e in envoys:
        log.info("  {} (ip={} ssh_port={})".format(
            e["envoy_hostname"], e["envoy_ip"], e["ssh_port"]
        ))

    log.info("Command        : {}".format(args.command))
    log.info("Workers/envoy  : {}".format(args.workers))
    log.info("Total threads  : {}".format(len(envoys) * args.workers))
    log.info("Delay          : {}s".format(args.delay))
    log.info("Timeout        : {}s".format(args.timeout))
    log.info("Duration       : {}".format(
        "{}s".format(args.duration) if args.duration > 0 else "until Ctrl+C"
    ))

    counters      = {"total": 0, "ok": 0, "fail": 0}
    counters_lock = threading.Lock()
    stop_event    = threading.Event()
    threads       = []

    # Reporter thread
    reporter = threading.Thread(
        target=reporter_loop,
        args=(counters, counters_lock, stop_event, 5),
        daemon=True,
    )
    reporter.start()

    # Spawn N worker threads per envoy
    for envoy in envoys:
        for i in range(args.workers):
            t = threading.Thread(
                target=worker_loop,
                args=(i, envoy["envoy_hostname"], envoy["ssh_port"],
                      args.command, args.iterations, args.delay, args.timeout,
                      counters, counters_lock, stop_event),
                daemon=True,
            )
            t.start()
            threads.append(t)

    try:
        if args.duration > 0:
            time.sleep(args.duration)
            stop_event.set()
        else:
            for t in threads:
                t.join()
    except KeyboardInterrupt:
        log.info("Interrupted, stopping...")
        stop_event.set()

    for t in threads:
        t.join(timeout=args.timeout + 2)

    with counters_lock:
        total = counters["total"]
        ok    = counters["ok"]
        fail  = counters["fail"]

    log.info("=== Final Results ===")
    log.info("  Total runs   : {}".format(total))
    log.info("  OK           : {}".format(ok))
    log.info("  FAIL         : {}".format(fail))
    if total > 0:
        log.info("  Failure rate : {:.1f}%".format(100.0 * fail / total))


if __name__ == "__main__":
    main()
