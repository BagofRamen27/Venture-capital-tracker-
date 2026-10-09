"""Hall of contributors: approved "Join the hall" GitHub issues become gallery entries."""
import json
from io import BytesIO

import httpx
from PIL import Image

from tests.conftest import make_client
from vcdiscovery.hall import GRAPHQL, approval_time, entry_from_issue, export_hall, parse_issue_form, process_photo

PHOTO = "https://github.com/user-attachments/assets/0a1b2c3d-1111-2222-3333-444455556666"


def body(name="Ada Lovelace", photo=f"![me]({PHOTO})", consent="- [X] This is a photo of me"):
    return (f"### Name\n\n{name}\n\n### Role\n\n_No response_\n\n### What did you contribute?\n\nWrote the   SEC parser.\n\n"
            f"### Photo of yourself\n\n{photo}\n\n### Consent\n\n{consent}\n")


def issue(number=7, text=None, actor="BagofRamen27", approved="2026-10-09T10:00:00Z", edited=None, extra=()):
    events = [{"__typename": "LabeledEvent", "createdAt": approved, "actor": {"login": actor}, "label": {"name": "hall-approved"}}]
    return {"number": number, "body": body() if text is None else text, "lastEditedAt": edited, "stateReason": None,
            "author": {"login": "ada"}, "timelineItems": {"nodes": events + list(extra)}}


def jpeg_with_location(size=(1200, 900)):
    img = Image.new("RGB", size, (200, 30, 30))
    exif = Image.Exif()
    exif[0x8825] = {2: (42.0, 21.0, 0.0)}  # GPS info
    exif[0x010F] = "PhoneMaker"
    out = BytesIO()
    img.save(out, "JPEG", exif=exif)
    return out.getvalue()


def test_issue_form_answers_are_read():
    form = parse_issue_form(body())
    assert form["name"] == "Ada Lovelace" and "role" not in form and form["contribution"] == "Wrote the   SEC parser."
    assert PHOTO in form["photo"] and "[X]" in form["consent"]


def test_entry_uses_issue_author_and_cleans_text():
    entry, url = entry_from_issue(issue(), "bagoframen27")
    assert url == PHOTO
    assert entry == {"name": "Ada Lovelace", "role": "Contributor", "github": "ada", "photo": "hall-7.jpg",
                     "joined": "2026-10", "contribution": "Wrote the SEC parser.", "issue": 7}


def test_only_the_owners_current_approval_of_unedited_text_counts():
    assert approval_time(issue(actor="someone-else"), "BagofRamen27") is None
    assert approval_time(issue(edited="2026-10-09T11:00:00Z"), "BagofRamen27") is None  # edited after approval
    assert approval_time(issue(edited="2026-10-09T09:00:00Z"), "BagofRamen27") == "2026-10-09T10:00:00Z"
    removed = {"__typename": "UnlabeledEvent", "createdAt": "2026-10-09T12:00:00Z", "label": {"name": "hall-approved"}}
    assert approval_time(issue(extra=[removed]), "BagofRamen27") is None
    other = {"__typename": "LabeledEvent", "createdAt": "2026-10-09T12:00:00Z", "actor": {"login": "x"}, "label": {"name": "bug"}}
    assert approval_time(issue(extra=[other]), "BagofRamen27") == "2026-10-09T10:00:00Z"


def test_incomplete_or_unsafe_requests_are_skipped():
    owner = "BagofRamen27"
    assert entry_from_issue(issue(text=body(consent="- [ ] This is a photo of me")), owner) is None
    assert entry_from_issue(issue(text=body(name="_No response_")), owner) is None
    assert entry_from_issue(issue(text=body(photo="![me](https://evil.example/me.jpg)")), owner) is None
    assert entry_from_issue({**issue(), "stateReason": "NOT_PLANNED"}, owner) is None


def test_photo_is_cropped_resized_and_stripped_of_metadata():
    out = Image.open(BytesIO(process_photo(jpeg_with_location())))
    assert out.format == "JPEG" and out.size == (480, 600)
    assert not out.getexif() and "exif" not in out.info


def test_non_photo_files_are_rejected():
    gif = BytesIO()
    Image.new("RGB", (10, 10)).save(gif, "GIF")
    for data in (gif.getvalue(), b"not an image"):
        try:
            process_photo(data)
        except Exception:
            continue
        raise AssertionError("should have been rejected")


def test_export_writes_hall_and_removes_stale_portraits(tmp_path):
    (tmp_path / "hall-99.jpg").write_bytes(b"old")
    calls = []

    def github(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if str(request.url) == GRAPHQL:
            q = json.loads(request.content)
            assert q["variables"] == {"owner": "BagofRamen27", "name": "Venture-capital-tracker-", "label": "hall-approved", "cursor": None}
            nodes = [issue(), issue(number=8, actor="stranger")]
            return httpx.Response(200, json={"data": {"repository": {"issues": {
                "pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}}})
        return httpx.Response(200, content=jpeg_with_location())

    entries = export_hall(make_client({GRAPHQL: github, PHOTO: github}), "tok", "BagofRamen27/Venture-capital-tracker-",
                          "BagofRamen27", tmp_path)
    assert [e["issue"] for e in entries] == [7]
    assert calls[0].headers["authorization"] == "Bearer tok"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["hall-7.jpg", "hall.json"]
    assert json.loads((tmp_path / "hall.json").read_text())["contributors"][0]["github"] == "ada"


def test_api_errors_are_raised_for_the_cli_to_report(tmp_path):
    client = make_client({GRAPHQL: lambda r: httpx.Response(200, json={"errors": [{"message": "Bad credentials"}]})})
    try:
        export_hall(client, "tok", "o/r", "o", tmp_path)
    except RuntimeError as exc:
        assert "Bad credentials" in str(exc)
    else:
        raise AssertionError("expected an error")
    assert not (tmp_path / "hall.json").exists()
