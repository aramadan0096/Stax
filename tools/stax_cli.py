#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tools/stax_cli.py — StaX REST API command-line client
======================================================
A standalone CLI for pipeline scripts, CI/CD hooks, and Deadline callbacks
to interact with a running StaX instance without launching the GUI.

Usage
-----
  python tools/stax_cli.py [--host HOST] [--port PORT] [--token TOKEN] <command>

Commands
--------
  health                          Check server is up
  stacks                          List all stacks
  lists    <stack_id>             List all lists in a stack
  elements <list_id>              List elements in a list (paginated)
  element  <element_id>           Show a single element
  ingest   <filepath> <list_id>   Ingest a file into a list
  search   <query>                Search elements by name (loose match)
  top      [--n N]                Show top N most-inserted elements
  patch    <element_id> [--tags TAGS] [--comment COMMENT] [--type TYPE]

Options
-------
  --host   HOST    API host     (default: 127.0.0.1)
  --port   PORT    API port     (default: 17171)
  --token  TOKEN   Auth token   (can also use env var STAX_API_TOKEN)
  --json           Output raw JSON instead of formatted tables
  --n      N       Number of results for the 'top' command (default: 20)

Environment variables
---------------------
  STAX_API_HOST   override --host
  STAX_API_PORT   override --port
  STAX_API_TOKEN  auth token (avoids passing on command line)

Examples
--------
  # Check server health
  python tools/stax_cli.py health

  # List all stacks
  python tools/stax_cli.py stacks

  # Ingest a file via pipeline script (e.g. from a Deadline post-render job)
  python tools/stax_cli.py ingest /render/output/comp_v003.%04d.exr 12 \
      --token $STAX_API_TOKEN

  # Search for fire-related assets
  python tools/stax_cli.py search fire

  # Show top 10 most-used assets
  python tools/stax_cli.py top --n 10

  # Update tags on an element
  python tools/stax_cli.py patch 42 --tags "fire, reviewed, 4k"
"""

from __future__ import absolute_import, print_function, unicode_literals

import argparse
import json
import os
import sys

try:
    from urllib.request import urlopen, Request
    from urllib.error   import HTTPError, URLError
    from urllib.parse   import urlencode, quote
except ImportError:
    from urllib2 import urlopen, Request, HTTPError, URLError  # Python 2
    from urllib  import urlencode, quote


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _request(method, url, token, payload=None):
    """
    Send an HTTP request and return (status_code: int, body: dict).
    Raises SystemExit on connection errors.
    """
    headers = {
        "X-StaX-Token":  token,
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }
    data = json.dumps(payload).encode("utf-8") if payload else None
    req  = Request(url, data=data, headers=headers)
    req.get_method = lambda: method

    try:
        resp = urlopen(req, timeout=10)
        body = json.loads(resp.read().decode("utf-8"))
        return resp.getcode(), body
    except HTTPError as e:
        body = {}
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            pass
        return e.code, body
    except URLError as e:
        print("ERROR: Could not connect to StaX API: {}".format(e.reason))
        print("Is StaX running?  Is the API enabled in Settings?")
        sys.exit(1)


def _get(url, token):
    return _request("GET", url, token)


def _post(url, token, payload):
    return _request("POST", url, token, payload)


def _patch(url, token, payload):
    return _request("PATCH", url, token, payload)


def _base(host, port):
    return "http://{}:{}/api/v1".format(host, port)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _print_table(rows, cols, col_widths=None):
    """Print a list-of-dicts as a fixed-width text table."""
    if not rows:
        print("  (no results)")
        return

    if col_widths is None:
        col_widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows))
                     for c in cols}
        col_widths = {c: min(col_widths[c], 60) for c in cols}

    header = "  ".join(str(c).ljust(col_widths[c]) for c in cols)
    sep    = "  ".join("-" * col_widths[c] for c in cols)
    print(header)
    print(sep)
    for row in rows:
        line = "  ".join(
            str(row.get(c, "")).ljust(col_widths[c])[:col_widths[c]]
            for c in cols
        )
        print(line)


def _ok(code, body, raw_json):
    if code >= 400:
        print("ERROR {}: {}".format(code, body.get("error", body)))
        sys.exit(code)
    if raw_json:
        print(json.dumps(body, indent=2))
    return body


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_health(args):
    base = _base(args.host, args.port)
    code, body = _get("{}/health".format(base), args.token)
    if code == 200:
        print("OK  StaX API is up. status={}".format(body.get("status")))
    else:
        print("FAIL  status={}  body={}".format(code, body))
        sys.exit(1)


def cmd_stacks(args):
    base = _base(args.host, args.port)
    code, body = _get("{}/stacks".format(base), args.token)
    body = _ok(code, body, args.json)
    if not args.json:
        _print_table(body, ["stack_id", "name", "path"],
                     {"stack_id": 8, "name": 30, "path": 50})


def cmd_lists(args):
    base = _base(args.host, args.port)
    code, body = _get("{}/stacks/{}/lists".format(base, args.stack_id),
                      args.token)
    body = _ok(code, body, args.json)
    if not args.json:
        _print_table(body, ["list_id", "name"],
                     {"list_id": 8, "name": 40})


def cmd_elements(args):
    base = _base(args.host, args.port)
    url  = "{}/lists/{}/elements?page={}&per_page={}".format(
        base, args.list_id, args.page, args.per_page
    )
    code, body = _get(url, args.token)
    body = _ok(code, body, args.json)
    if not args.json:
        total = body.get("total", "?")
        page  = body.get("page",  "?")
        elems = body.get("elements", [])
        print("Page {} — showing {}/{} elements".format(
            page, len(elems), total
        ))
        _print_table(elems,
                     ["element_id", "name", "type", "format", "frame_range"],
                     {"element_id": 10, "name": 35, "type": 8,
                      "format": 8, "frame_range": 14})


def cmd_element(args):
    base = _base(args.host, args.port)
    code, body = _get("{}/elements/{}".format(base, args.element_id),
                      args.token)
    body = _ok(code, body, args.json)
    if not args.json:
        for k, v in sorted(body.items()):
            print("  {:20s} {}".format(k + ":", v))


def cmd_ingest(args):
    base    = _base(args.host, args.port)
    payload = {
        "filepath":    args.filepath,
        "list_id":     int(args.list_id),
        "copy_policy": args.copy_policy,
    }
    code, body = _post("{}/elements/ingest".format(base), args.token, payload)
    body = _ok(code, body, args.json)
    if not args.json:
        if body.get("success"):
            print("OK  element_id={}".format(body.get("element_id")))
        else:
            print("FAILED  reason={}".format(
                body.get("reason", body.get("error", "unknown"))
            ))


def cmd_search(args):
    base = _base(args.host, args.port)
    url  = "{}/search?q={}&property={}&match={}".format(
        base,
        quote(args.query),
        args.property,
        args.match,
    )
    code, body = _get(url, args.token)
    body = _ok(code, body, args.json)
    if not args.json:
        print("{} result(s):".format(len(body)))
        _print_table(body,
                     ["element_id", "name", "type", "format"],
                     {"element_id": 10, "name": 40, "type": 8, "format": 8})


def cmd_top(args):
    base = _base(args.host, args.port)
    code, body = _get("{}/analytics/top?n={}".format(base, args.n),
                      args.token)
    body = _ok(code, body, args.json)
    if not args.json:
        print("Top {} most-inserted assets:".format(args.n))
        for i, item in enumerate(body, 1):
            print("  {:3d}.  {:35s}  count={:5d}  list={}".format(
                i,
                item.get("name", "")[:35],
                item.get("count", 0),
                item.get("list_name", ""),
            ))


def cmd_patch(args):
    base    = _base(args.host, args.port)
    payload = {}
    if args.tags    is not None: payload["tags"]    = args.tags
    if args.comment is not None: payload["comment"] = args.comment
    if args.type    is not None: payload["type"]    = args.type
    if not payload:
        print("Nothing to update — specify at least one of: "
              "--tags, --comment, --type")
        sys.exit(1)
    code, body = _patch(
        "{}/elements/{}".format(base, args.element_id),
        args.token, payload,
    )
    body = _ok(code, body, args.json)
    if not args.json:
        print("OK  updated element_id={}".format(
            body.get("updated", args.element_id)
        ))


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser():
    p = argparse.ArgumentParser(
        prog="stax_cli",
        description="StaX REST API command-line client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Global options
    p.add_argument(
        "--host",
        default=os.environ.get("STAX_API_HOST", "127.0.0.1"),
        help="API host (default: 127.0.0.1)",
    )
    p.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("STAX_API_PORT", "17171")),
        help="API port (default: 17171)",
    )
    p.add_argument(
        "--token",
        default=os.environ.get("STAX_API_TOKEN", ""),
        help="Auth token (or set STAX_API_TOKEN env var)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON",
    )

    subs = p.add_subparsers(dest="command")
    subs.required = True

    # health
    subs.add_parser("health", help="Check API health")

    # stacks
    subs.add_parser("stacks", help="List all stacks")

    # lists
    sp = subs.add_parser("lists", help="List lists in a stack")
    sp.add_argument("stack_id", type=int)

    # elements
    sp = subs.add_parser("elements", help="List elements in a list")
    sp.add_argument("list_id", type=int)
    sp.add_argument("--page",     type=int, default=1)
    sp.add_argument("--per-page", dest="per_page", type=int, default=50)

    # element
    sp = subs.add_parser("element", help="Show a single element")
    sp.add_argument("element_id", type=int)

    # ingest
    sp = subs.add_parser("ingest", help="Ingest a file into a list")
    sp.add_argument("filepath")
    sp.add_argument("list_id", type=int)
    sp.add_argument("--copy-policy", dest="copy_policy",
                    choices=["hard", "soft"], default=None)

    # search
    sp = subs.add_parser("search", help="Search elements")
    sp.add_argument("query")
    sp.add_argument("--property", default="name",
                    choices=["name", "format", "type", "comment", "tags"])
    sp.add_argument("--match",    default="loose", choices=["loose", "strict"])

    # top
    sp = subs.add_parser("top", help="Show top N most-inserted elements")
    sp.add_argument("--n", type=int, default=20)

    # patch
    sp = subs.add_parser("patch", help="Update element metadata")
    sp.add_argument("element_id", type=int)
    sp.add_argument("--tags",    default=None)
    sp.add_argument("--comment", default=None)
    sp.add_argument("--type",    default=None, choices=["2D", "3D", "Toolset"])

    return p


_COMMANDS = {
    "health":   cmd_health,
    "stacks":   cmd_stacks,
    "lists":    cmd_lists,
    "elements": cmd_elements,
    "element":  cmd_element,
    "ingest":   cmd_ingest,
    "search":   cmd_search,
    "top":      cmd_top,
    "patch":    cmd_patch,
}


def main():
    parser = _build_parser()
    args   = parser.parse_args()

    if not args.token and args.command != "health":
        print("WARNING: No auth token set.  "
              "Use --token or set STAX_API_TOKEN.")

    fn = _COMMANDS.get(args.command)
    if fn is None:
        parser.print_help()
        sys.exit(1)
    fn(args)


if __name__ == "__main__":
    main()
