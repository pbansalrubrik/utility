#!/usr/bin/env python3

from __future__ import absolute_import, print_function

import sys

sys.path.append('/opt/rubrik/src/py/build/thrift/gen-py/')  # noqa
sys.path.append('/opt/rubrik/src/')  # noqa

from management import ClusterConfigService  # noqa
from py.utils.thrift_util import MockLocalDeployment, TlsService  # noqa

with TlsService(
    '127.0.0.1',
    7781,
    MockLocalDeployment(),
    hostname_to_fetch_certificate=None,
    interface=ClusterConfigService,
    name='ClusterConfigService',
) as client:
    result = client.hardwareHealthCheck(isReplacement=False)
    print('hardwareHealthCheck result:', result)
