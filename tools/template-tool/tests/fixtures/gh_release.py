#!/usr/bin/env python3
"""Offline gh stand-in for the delivered GitHub release adapter."""

import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
state_path = Path(os.environ["GH_TEST_STATE"])
state = json.loads(state_path.read_text())
state.setdefault("calls", []).append(args)
state_path.write_text(json.dumps(state))

if args[:2] == ["api", "graphql"]:
    if state.get("query_error"):
        sys.exit("GraphQL request failed")
    repository = {
        "ref": {"target": {"oid": "tag-object"}} if state["tag_exists"] else None,
        "release": None if state["release"] == "missing" else {
            "isDraft": state["release"] == "draft",
        },
    }
    if state.get("repository_missing"):
        repository = None
    print(json.dumps({"data": {"repository": repository}}))
elif args[0] == "api" and args[1].startswith("repos/example/project/commits/"):
    if state.get("commit_error"):
        sys.exit("Commit lookup failed")
    print(state["tag_commit"])
elif args[:2] == ["release", "create"]:
    if state.get("create_error"):
        sys.exit("Create failed")
    state["release"] = "published"
    print("https://github.com/example/project/releases/tag/" + args[2])
elif args[:2] == ["release", "upload"]:
    if state.get("upload_error"):
        sys.exit("Upload rejected")
elif args[:2] == ["release", "edit"]:
    if state.get("edit_error"):
        sys.exit("Edit rejected")
    state["release"] = "published"
else:
    sys.exit("Unexpected gh invocation: " + repr(args))

state_path.write_text(json.dumps(state))
