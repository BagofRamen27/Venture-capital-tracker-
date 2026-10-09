"""Hall of contributors: turn approved "Join the hall" GitHub issues into gallery entries.

Flow: a visitor fills in the form on the website, which opens a pre-filled GitHub issue
(.github/ISSUE_TEMPLATE/join-the-hall.yml) where they attach a photo of themselves. The repository
owner approves it by adding the `hall-approved` label. Each site build then calls `export_hall`,
which writes `hall.json` and one resized, metadata-free JPEG per approved issue.

Safety rules:
* only the repository owner's `hall-approved` label counts, and an issue edited after it was
  approved is hidden until the owner approves it again (remove and re-add the label);
* the GitHub handle shown is the issue's author, so nobody can claim someone else's account;
* photos are downloaded only from GitHub's own attachment hosts, must be JPEG, PNG or WebP,
  and are re-encoded (cropped to 4:5, 480x600) so location and camera data are dropped;
* closing the issue as "not planned" or removing the label takes the portrait down on the next build.
"""
from __future__ import annotations

import json
import re
import warnings
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

from .http import PoliteClient

LABEL = "hall-approved"
GRAPHQL = "https://api.github.com/graphql"
MAX_PHOTO_BYTES = 10 * 1024 * 1024
PHOTO_SIZE = (480, 600)
PHOTO_URL = re.compile(
    r"https://(?:github\.com/user-attachments/assets/[0-9a-fA-F-]+"
    r"|(?:private-)?user-images\.githubusercontent\.com/[^\s)\"'<>]+)")
FIELDS = {"name": "name", "role": "role", "what did you contribute?": "contribution",
          "photo of yourself": "photo", "consent": "consent"}

QUERY = """query($owner:String!,$name:String!,$label:String!,$cursor:String){
 repository(owner:$owner,name:$name){issues(first:50,after:$cursor,labels:[$label],states:[OPEN,CLOSED],
  orderBy:{field:CREATED_AT,direction:ASC}){pageInfo{hasNextPage endCursor}
  nodes{number body lastEditedAt stateReason author{login}
   timelineItems(itemTypes:[LABELED_EVENT,UNLABELED_EVENT],last:50){nodes{__typename
    ...on LabeledEvent{createdAt actor{login} label{name}} ...on UnlabeledEvent{createdAt label{name}}}}}}}}"""


def parse_issue_form(body: str) -> dict[str, str]:
    """Read the answers of a GitHub issue form ("### Question" followed by the answer)."""
    out: dict[str, str] = {}
    for heading, answer in re.findall(r"^###\s+(.+?)\s*$\n(.*?)(?=^###\s|\Z)", body or "", re.M | re.S):
        key = FIELDS.get(heading.strip().lower())
        value = answer.strip()
        if key and value != "_No response_":
            out[key] = value
    return out


def approval_time(issue: dict, owner: str) -> str | None:
    """When the owner's current `hall-approved` label was added, if it still covers the issue's text."""
    events = [e for e in issue.get("timelineItems", {}).get("nodes", []) if (e.get("label") or {}).get("name") == LABEL]
    if not events or events[-1]["__typename"] != "LabeledEvent":
        return None
    last = events[-1]
    if ((last.get("actor") or {}).get("login") or "").lower() != owner.lower():
        return None
    edited = issue.get("lastEditedAt")
    return None if edited and edited > last["createdAt"] else last["createdAt"]


def entry_from_issue(issue: dict, owner: str) -> tuple[dict, str] | None:
    """(gallery entry, photo URL) for an approved, complete issue; None otherwise."""
    if issue.get("stateReason") == "NOT_PLANNED":
        return None
    approved = approval_time(issue, owner)
    form = parse_issue_form(issue.get("body") or "")
    photo = PHOTO_URL.search(form.get("photo", ""))
    name = " ".join(form.get("name", "").split())[:60]
    if not approved or not name or not photo or "[x]" not in form.get("consent", "").lower():
        return None
    entry = {"name": name, "role": " ".join(form.get("role", "").split())[:40] or "Contributor",
             "github": (issue.get("author") or {}).get("login", ""), "photo": f"hall-{issue['number']}.jpg",
             "joined": approved[:7], "contribution": " ".join(form.get("contribution", "").split())[:200],
             "issue": issue["number"]}
    return entry, photo.group(0)


def process_photo(data: bytes) -> bytes:
    """Re-encode an uploaded photo: upright, cropped to 4:5, 480x600 JPEG, with no metadata."""
    if len(data) > MAX_PHOTO_BYTES:
        raise ValueError("photo is larger than 10 MB")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(BytesIO(data)) as img:
            if img.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError(f"unsupported photo format {img.format}")
            img = ImageOps.fit(ImageOps.exif_transpose(img).convert("RGB"), PHOTO_SIZE, Image.LANCZOS,
                               centering=(0.5, 0.4))
    out = BytesIO()
    img.save(out, "JPEG", quality=85, optimize=True)
    return out.getvalue()


def fetch_issues(client: PoliteClient, token: str, repo: str) -> list[dict]:
    owner, name = repo.split("/", 1)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    issues, cursor = [], None
    while True:
        variables = {"owner": owner, "name": name, "label": LABEL, "cursor": cursor}
        data = client.post(GRAPHQL, json={"query": QUERY, "variables": variables}, headers=headers).json()
        if data.get("errors"):
            raise RuntimeError(f"GitHub API error: {data['errors'][0].get('message')}")
        page = data["data"]["repository"]["issues"]
        issues += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return issues
        cursor = page["pageInfo"]["endCursor"]


def export_hall(client: PoliteClient, token: str, repo: str, owner: str, out_dir: str | Path) -> list[dict]:
    """Write hall.json and the approved portraits to `out_dir`; returns the entries written."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    entries = []
    for issue in fetch_issues(client, token, repo):
        found = entry_from_issue(issue, owner)
        if not found:
            continue
        entry, url = found
        try:
            photo = process_photo(client.get(url).content)
        except Exception as exc:  # one bad photo must not hide the rest of the hall
            print(f"Skipping hall issue #{issue['number']}: {exc}")
            continue
        (out / entry["photo"]).write_bytes(photo)
        entries.append(entry)
    keep = {e["photo"] for e in entries}
    for old in out.glob("hall-*.jpg"):
        if old.name not in keep:
            old.unlink()
    (out / "hall.json").write_text(json.dumps({"contributors": entries}, ensure_ascii=False, indent=1), encoding="utf-8")
    return entries
