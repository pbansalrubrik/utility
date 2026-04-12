#!/usr/bin/env python3

"""
Script to exercise org-network GraphQL APIs against an RSC instance.

Prerequisites:
  1. Create a service account in RSC
     (Settings > Users & Access > Service Accounts).
  2. Ensure the service account has ManageOrganizationNetworks and
     ManageClusterSettings permissions.
  3. Click "Rotate Secret" (three dots menu) and download the JSON file.
  4. Save to ~/test-org-network.json (or pass --creds <path>).

Usage:
  # Create an org network
  ./test_create_org_network_v2.py createOrgNetworkV2 --cluster-uuid <uuid>

  # List all org networks
  ./test_create_org_network_v2.py listOrgNetworks

  # Delete an org network
  ./test_create_org_network_v2.py deleteOrgNetwork --org-network-id <id>

  # List available APIs
  ./test_create_org_network_v2.py --list-apis
"""

from __future__ import absolute_import, print_function

import argparse
import json
import logging
import os
import sys

try:
    import requests
except ImportError:
    import subprocess
    print("installing requests package")
    subprocess.check_call(["pip3", "install", "requests"])
    import requests

import urllib3
urllib3.disable_warnings()

LOG_FILE = os.path.basename(__file__) + ".log"
logger = logging.getLogger(os.path.basename(__file__))
file_handler = logging.FileHandler(filename=LOG_FILE, mode="a")
formatter = logging.Formatter("%(levelname)s:%(asctime)s: %(message)s")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.setLevel(logging.DEBUG)

DEFAULT_CREDS_FILE = os.path.expanduser("~/test-org-network.json")

client_secret_json = {}
rsc_token = ""

# ---------------------------------------------------------------------------
# Registry of GraphQL APIs
# Each entry: (query_string, required_args, description)
# ---------------------------------------------------------------------------
APIS = {}


def register_api(name, query, required_args, description):
    """Register a GraphQL API that can be invoked by name."""
    APIS[name] = {
        "query": query,
        "required_args": required_args,
        "description": description,
    }


register_api(
    name="createOrgNetworkV2",
    query="""
    mutation CreateOrgNetworkV2($input: CreateOrgNetworkV2Input!) {
      createOrgNetworkV2(input: $input) {
        orgNetworkId
      }
    }
    """,
    required_args=["cluster-uuid"],
    description="Create an org network (V2) — accepts only cluster UUID, name is auto-generated.",
)

register_api(
    name="createOrgNetwork",
    query="""
    mutation CreateOrgNetwork($input: CreateOrgNetworkInput!) {
      createOrgNetwork(input: $input) {
        orgNetworkId
      }
    }
    """,
    required_args=["cluster-uuid", "org-id", "org-network-name"],
    description="Create an org network (V1) — requires cluster UUID, org ID, and name.",
)

register_api(
    name="listOrgNetworks",
    query="""
    query OrgNetworks($filter: OrgNetworkFilterInput) {
      orgNetworks(filter: $filter) {
        nodes {
          orgNetworkId
          orgNetworkName
          cluster {
            id
            name
          }
        }
      }
    }
    """,
    required_args=[],
    description="List org networks. Optionally filter by --cluster-uuid.",
)

register_api(
    name="deleteOrgNetwork",
    query="""
    mutation DeleteOrgNetwork($input: DeleteOrgNetworkInput!) {
      deleteOrgNetwork(input: $input)
    }
    """,
    required_args=["org-network-id"],
    description="Delete an org network by ID.",
)

register_api(
    name="refreshOrgNetwork",
    query="""
    mutation RefreshOrgNetwork($input: RefreshOrgNetworkInput!) {
      refreshOrgNetwork(input: $input)
    }
    """,
    required_args=["org-network-id"],
    description="Refresh an org network by ID.",
)


def build_variables(api_name, args):
    """Build GraphQL variables from CLI args for the given API."""
    if api_name == "createOrgNetworkV2":
        return {"input": {"clusterUuid": args.cluster_uuid}}
    elif api_name == "createOrgNetwork":
        return {
            "input": {
                "clusterUuid": args.cluster_uuid,
                "orgId": args.org_id,
                "name": args.org_network_name,
            }
        }
    elif api_name == "deleteOrgNetwork":
        return {"input": {"orgNetworkId": args.org_network_id}}
    elif api_name == "refreshOrgNetwork":
        return {"input": {"orgNetworkId": args.org_network_id}}
    elif api_name == "listOrgNetworks":
        if getattr(args, "cluster_uuid", None):
            return {"filter": {"rubrikCluster": [args.cluster_uuid]}}
        return {}
    return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def print_info(msg):
    print("[INFO] " + msg)
    logger.info(msg)


def print_error(msg):
    print("[ERROR] " + msg, file=sys.stderr)
    logger.error(msg)


def get_rsc_token(creds):
    """Get RSC API token using service account credentials."""
    global client_secret_json
    client_secret_json = creds
    token_url = creds["access_token_uri"]
    token_data = {
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
    }
    token_headers = {"Content-Type": "application/json"}

    try:
        resp = requests.post(
            token_url, headers=token_headers, json=token_data, verify=False
        )
        if resp.status_code == 200:
            return resp.json().get("access_token")
        else:
            print_error(
                "Failed to fetch RSC API token, status code {}".format(
                    resp.status_code
                )
            )
            sys.exit(1)
    except Exception as err:
        print_error("An error occurred: {}".format(err))
        sys.exit(1)


def get_rsc_url():
    """Derive the GraphQL API URL and headers from the credentials."""
    access_token_uri = client_secret_json["access_token_uri"]
    rsc_url = access_token_uri.rsplit("/", 1)[0] + "/graphql"
    api_headers = {
        "Authorization": "Bearer {}".format(rsc_token),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    return rsc_url, api_headers


def execute_graphql(api_name, variables):
    """Execute a registered GraphQL API."""
    api_url, api_headers = get_rsc_url()
    api_def = APIS[api_name]

    print_info("Calling {} ...".format(api_name))
    if variables:
        logger.debug("Variables: %s", json.dumps(variables))

    payload = {"query": api_def["query"]}
    if variables:
        payload["variables"] = variables

    resp = requests.post(
        api_url,
        headers=api_headers,
        json=payload,
        verify=False,
    )
    return resp.json()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Exercise org-network GraphQL APIs against an RSC instance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "api",
        nargs="?",
        choices=list(APIS.keys()),
        help="GraphQL API to call",
    )
    parser.add_argument(
        "--list-apis",
        action="store_true",
        help="List all available APIs and exit",
    )
    parser.add_argument(
        "--creds",
        required=False,
        default=None,
        help="Path to service account JSON file. "
        "If omitted, reads from ~/test-org-network.json.",
    )
    parser.add_argument(
        "--cluster-uuid",
        help="UUID of the Rubrik cluster",
    )
    parser.add_argument(
        "--org-id",
        help="Organization ID (for createOrgNetwork V1)",
    )
    parser.add_argument(
        "--org-network-name",
        help="Org network name (for createOrgNetwork V1)",
    )
    parser.add_argument(
        "--org-network-id",
        help="Org network ID (for deleteOrgNetwork, refreshOrgNetwork)",
    )
    args = parser.parse_args()

    # List APIs mode
    if args.list_apis:
        print("\nAvailable APIs:\n")
        for name, api_def in APIS.items():
            req = ", ".join("--" + a for a in api_def["required_args"]) or "(none)"
            print("  {:<25s} {}".format(name, api_def["description"]))
            print("  {:<25s} Required args: {}\n".format("", req))
        return

    if not args.api:
        parser.print_help()
        sys.exit(1)

    # Validate required args
    api_def = APIS[args.api]
    missing = []
    for req_arg in api_def["required_args"]:
        attr_name = req_arg.replace("-", "_")
        if not getattr(args, attr_name, None):
            missing.append("--" + req_arg)
    if missing:
        print_error(
            "{} requires: {}".format(args.api, ", ".join(missing))
        )
        sys.exit(1)

    # Load credentials
    creds_file = args.creds or DEFAULT_CREDS_FILE
    if not os.path.isfile(creds_file):
        print_error(
            "Credentials file not found: {}\n"
            "Steps:\n"
            "  1. Create a service account in RSC (Settings > Users & Access > Service Accounts)\n"
            "  2. Rotate Secret and download as JSON\n"
            "  3. Save to ~/test-org-network.json (or pass --creds <path>)".format(creds_file)
        )
        sys.exit(1)
    print_info("Loading credentials from {}".format(creds_file))
    with open(creds_file) as f:
        creds = json.load(f)

    rsc_url_base = creds["access_token_uri"].rsplit("/", 1)[0]
    print_info("RSC URL: {}".format(rsc_url_base))

    # Authenticate
    global rsc_token
    print_info("Fetching RSC API token...")
    rsc_token = get_rsc_token(creds)
    print_info("Token acquired.")

    # Execute
    variables = build_variables(args.api, args)
    result = execute_graphql(args.api, variables)
    print(json.dumps(result, indent=2))

    if "errors" in result or "code" in result:
        print_error("API call failed.")
        if "errors" in result:
            for err in result["errors"]:
                print_error("  {}".format(err.get("message", err)))
        if "message" in result:
            print_error("  {}".format(result["message"]))
        sys.exit(1)
    else:
        print_info("Success!")


if __name__ == "__main__":
    main()
