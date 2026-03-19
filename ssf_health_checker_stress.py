#!/usr/bin/env python3
"""
Standalone SSF health checker stress tester.
Reproduces the epoll_reactor race condition by running health checks
in parallel tight loops against SSF tunnel endpoints.

Automatically discovers tunnel endpoints from ReverseUserServiceConfig_*.json
files in /home/ubuntu/envoy_configs/ — looks for entries forwarding to :443.

Usage:
    # Auto-discover endpoints from config files (default)
    python3 ssf_health_checker_stress.py

    # Override config directory
    python3 ssf_health_checker_stress.py --config-dir /home/ubuntu/envoy_configs/

    # Override workers / duration
    python3 ssf_health_checker_stress.py --workers 20 --duration 300

    # Verbose per-check logging
    python3 ssf_health_checker_stress.py -v
"""

import argparse
import glob
import json
import logging
import os
import subprocess
import sys
import threading
import time


ENVOY_CONFIGS_DIR = '/home/ubuntu/envoy_configs/'
REVERSE_CONFIG_GLOB = 'ReverseUserServiceConfig_*.json'
HEALTH_CHECK_TARGET_PORT = '443'


def discover_endpoints(config_dir):
    """
    Scan all ReverseUserServiceConfig_*.json files and return a list of
    (node_id, listening_ip, listening_port) tuples for entries that forward
    to port 443 (the health check target).

    Config entry format:
        "<listening_ip>:<listening_port>:<target_ip>:<target_port>": "L"
    """
    pattern = os.path.join(config_dir, REVERSE_CONFIG_GLOB)
    config_files = glob.glob(pattern)

    if not config_files:
        return []

    endpoints = []
    for path in sorted(config_files):
        # Extract node id from filename
        basename = os.path.basename(path)
        node_id = basename.replace('ReverseUserServiceConfig_', '').replace('.json', '')

        try:
            with open(path, 'r') as f:
                rules = json.load(f)
        except Exception as e:
            logging.getLogger("discover").warning(
                "Could not parse {}: {}".format(path, e)
            )
            continue

        for rule_key in rules:
            parts = rule_key.split(':')
            if len(parts) != 4:
                continue
            listening_ip, listening_port, _target_ip, target_port = parts
            if target_port == HEALTH_CHECK_TARGET_PORT:
                endpoints.append((node_id, listening_ip, listening_port))

    return endpoints


def do_health_check(ip, port, timeout_sec):
    """
    Run one SSF health check: connect via openssl s_client through the SSF
    tunnel and check if a certificate is returned.
    Returns True if healthy, False otherwise.
    """
    cmd = (
        "echo | timeout {timeout} openssl s_client "
        "-servername {ip} -connect {ip}:{port} 2>/dev/null "
        "| sed -ne '/-BEGIN CERTIFICATE-/,/-END CERTIFICATE-/p'"
    ).format(ip=ip, port=port, timeout=timeout_sec)

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            universal_newlines=True,
        )
        return len(result.stdout.strip()) != 0
    except Exception:
        return False


def worker_loop(worker_id, ip, port, node_id, iterations, delay, timeout_sec,
                counters, counters_lock, stop_event):
    """
    One worker thread: hammer one SSF tunnel endpoint with health checks.
    iterations=0 means run until stop_event is set.
    """
    log = logging.getLogger("worker-{}-{}".format(node_id, worker_id))
    i = 0
    while not stop_event.is_set():
        t_start = time.time()
        healthy = do_health_check(ip, port, timeout_sec)
        elapsed = time.time() - t_start

        with counters_lock:
            counters["total"] += 1
            if healthy:
                counters["ok"] += 1
            else:
                counters["fail"] += 1

        log.debug(
            "check #{} {}:{} result={} elapsed={:.2f}s".format(
                i + 1, ip, port, "OK" if healthy else "FAIL", elapsed
            )
        )

        i += 1
        if iterations > 0 and i >= iterations:
            break

        if delay > 0:
            time.sleep(delay)


def reporter_loop(counters, counters_lock, stop_event, interval=5):
    """Print a running summary every `interval` seconds."""
    log = logging.getLogger("reporter")
    start = time.time()
    while not stop_event.is_set():
        time.sleep(interval)
        with counters_lock:
            total = counters["total"]
            ok = counters["ok"]
            fail = counters["fail"]
        elapsed = time.time() - start
        rate = total / elapsed if elapsed > 0 else 0
        log.info(
            "[{:.0f}s] total={} ok={} fail={} rate={:.1f}/s".format(
                elapsed, total, ok, fail, rate
            )
        )


def main():
    parser = argparse.ArgumentParser(
        description="SSF health checker stress tester"
    )
    parser.add_argument(
        "--config-dir", default=ENVOY_CONFIGS_DIR,
        help="Directory containing ReverseUserServiceConfig_*.json files "
             "(default: {})".format(ENVOY_CONFIGS_DIR)
    )
    parser.add_argument(
        "--workers", type=int, default=10,
        help="Parallel workers per tunnel endpoint (default: 10)"
    )
    parser.add_argument(
        "--iterations", type=int, default=0,
        help="Checks per worker; 0=run forever (default: 0)"
    )
    parser.add_argument(
        "--delay", type=float, default=0,
        help="Sleep between checks per worker in sec; 0=tight loop (default: 0)"
    )
    parser.add_argument(
        "--timeout", type=int, default=5,
        help="openssl connect timeout in sec (default: 5)"
    )
    parser.add_argument(
        "--duration", type=int, default=0,
        help="Stop after N seconds; 0=run until Ctrl+C (default: 0)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable per-check debug logging"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("main")

    # Discover endpoints
    endpoints = discover_endpoints(args.config_dir)
    if not endpoints:
        log.error(
            "No tunnel endpoints found in {} matching port {}. "
            "Check that ReverseUserServiceConfig_*.json files exist.".format(
                args.config_dir, HEALTH_CHECK_TARGET_PORT
            )
        )
        sys.exit(1)

    log.info("Discovered {} tunnel endpoint(s):".format(len(endpoints)))
    for node_id, ip, port in endpoints:
        log.info("  node={} -> {}:{}".format(node_id, ip, port))

    log.info("Workers per endpoint : {}".format(args.workers))
    log.info("Total worker threads : {}".format(len(endpoints) * args.workers))
    log.info("Delay between checks : {}s".format(args.delay))
    log.info("Duration             : {}".format(
        "{}s".format(args.duration) if args.duration > 0 else "until Ctrl+C"
    ))

    counters = {"total": 0, "ok": 0, "fail": 0}
    counters_lock = threading.Lock()
    stop_event = threading.Event()
    threads = []

    # Reporter thread
    reporter = threading.Thread(
        target=reporter_loop,
        args=(counters, counters_lock, stop_event, 5),
        daemon=True,
    )
    reporter.start()

    # Spawn workers for every discovered endpoint
    for node_id, ip, port in endpoints:
        for i in range(args.workers):
            t = threading.Thread(
                target=worker_loop,
                args=(i, ip, port, node_id, args.iterations, args.delay,
                      args.timeout, counters, counters_lock, stop_event),
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
        t.join(timeout=args.timeout + 1)

    with counters_lock:
        total = counters["total"]
        ok = counters["ok"]
        fail = counters["fail"]

    log.info("=== Final Results ===")
    log.info("  Total checks : {}".format(total))
    log.info("  OK           : {}".format(ok))
    log.info("  FAIL         : {}".format(fail))
    if total > 0:
        log.info("  Failure rate : {:.1f}%".format(100.0 * fail / total))


if __name__ == "__main__":
    main()
