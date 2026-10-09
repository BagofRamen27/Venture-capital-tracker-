# Contributing

1. Open an issue describing the bug or proposed change.
2. Fork the public repository, or create a branch if you have collaborator access.
3. Website: work inside `vc-investment-tracker-web/` and run `npm run dev` (Node 20.11+; no dependencies to install).
   Discovery engine: work inside `discovery-engine/` (Python 3.10+; see its README).
4. Run the tests: `npm test && npm run check && npm run build` in the website folder, and `python -m pytest` in
   `discovery-engine/`. Check affected views on desktop and mobile.
5. Submit a pull request describing the change and how you checked it.

Keep changes focused and preserve source citations. For data corrections, include a source URL and explain what
changed. Distinguish verified records from company claims, and never present rumours or fundraising targets as
money raised. Never commit keys, personal credentials, `.env` files, browser storage exports, or generated data
(`public/data/market.json`, `discovery.json`, `news.json`, `status.json`, `dist/`, `*.db`).

Contributions to application code are provided under the repository's MIT license.

## Join the Hall of contributors

Everyone who helps build VentureScout can hang their portrait in the **Hall of contributors** tab on the website.

1. Open the website's **Hall of contributors** tab and fill in **Join the hall** (name, role, what you contributed).
2. **Continue on GitHub** opens a request with your details filled in. Drag a photo of yourself into the photo
   box, tick the consent box and submit. (You can also open it directly: **Issues → New issue → Join the Hall of
   contributors**.)
3. The project owner reviews it and adds the `hall-approved` label. The website republishes within minutes and
   your portrait appears, linked to your GitHub profile.

Photos are cropped to a 4:5 portrait (480×600) and re-encoded, which removes location and camera data. Photos stay
yours (they are not covered by the MIT license); you can ask for removal at any time by commenting on or closing your
request. If you edit your request after it was approved, it is hidden until the owner approves it again.

**For the owner:** to approve, add the `hall-approved` label to the request. To take a portrait down, remove the label
or close the request as *not planned*. Long-standing entries can also be listed by hand in
`vc-investment-tracker-web/public/contributors/contributors.json`, with the photo in the same folder.
