#!/usr/bin/env python3
"""
Generic ClusterConfigService Thrift client.

Usage examples:
  # No-arg APIs
  python3 cluster_config_thrift_client.py hardwareHealthCheck
  python3 cluster_config_thrift_client.py getIpmiAddress

  # APIs with arguments (passed as key=value pairs)
  python3 cluster_config_thrift_client.py hardwareHealthCheck isReplacement=false
  python3 cluster_config_thrift_client.py runDecommissionNodesPrechecks nodesIds='["node1","node2"]' isReplacement=false

  # Custom host/port
  python3 cluster_config_thrift_client.py --host 10.0.0.1 --port 7781 hardwareHealthCheck
"""

from __future__ import absolute_import, print_function

import argparse
import json
import sys

sys.path.append('/opt/rubrik/src/py/build/thrift/gen-py/')  # noqa
sys.path.append('/opt/rubrik/src/')  # noqa

from management import ClusterConfigService  # noqa
from py.utils.thrift_util import MockLocalDeployment, TlsService  # noqa


def parse_value(v):
    """Parse a string value into the appropriate Python type."""
    try:
        return json.loads(v)
    except (ValueError, TypeError):
        return v


def parse_args():
    parser = argparse.ArgumentParser(
        description='Generic ClusterConfigService Thrift client',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Target host (default: 127.0.0.1)',
    )
    parser.add_argument(
        '--port',
        type=int,
        default=7781,
        help='Target port (default: 7781)',
    )
    parser.add_argument(
        'api',
        help='ClusterConfigService API method name (e.g. hardwareHealthCheck)',
    )
    parser.add_argument(
        'kwargs',
        nargs='*',
        metavar='key=value',
        help='API arguments as key=value pairs. Lists/bools use JSON syntax: '
             'nodesIds=\'["id1","id2"]\' isReplacement=false',
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Parse key=value argument pairs
    kwargs = {}
    for kv in args.kwargs:
        if '=' not in kv:
            print(f'ERROR: argument must be in key=value format, got: {kv}',
                  file=sys.stderr)
            sys.exit(1)
        key, _, value = kv.partition('=')
        kwargs[key] = parse_value(value)

    with TlsService(
        args.host,
        args.port,
        MockLocalDeployment(),
        hostname_to_fetch_certificate=None,
        interface=ClusterConfigService,
        name='ClusterConfigService',
    ) as client:
        method = getattr(client, args.api, None)
        if method is None:
            print(f'ERROR: ClusterConfigService has no method "{args.api}"',
                  file=sys.stderr)
            sys.exit(1)

        print(f'Calling {args.api}({kwargs})')
        result = method(**kwargs)
        print(f'Result: {result}')


if __name__ == '__main__':
    main()
