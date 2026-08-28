# Design tournament

Magic Table Finder landing + logged-in chrome bake-off.

| Team | Packet | Folder |
|---|---|---|
| Quiet Luxury | [packets/quiet-luxury.md](packets/quiet-luxury.md) | `design-tournament/quiet-luxury/` |
| Park Day Pulse | [packets/park-day-pulse.md](packets/park-day-pulse.md) | `design-tournament/park-day-pulse/` |
| Trusted Watch | [packets/trusted-watch.md](packets/trusted-watch.md) | `design-tournament/trusted-watch/` |

- Shared brief: [BRIEF.md](BRIEF.md)
- Scoring: [RUBRIC.md](RUBRIC.md)

Serve a team folder statically, for example:

```bash
python3 -m http.server 8788 --directory design-tournament/quiet-luxury
```

Legal footer links in mocks must use `https://magictablefinder.com/privacy.html` (and terms / sms-consent). Do not point at `/privacy.html` from a team-folder server.

These mocks are **not** production. Do not merge tournament HTML onto `main`. The winning vision is implemented into `public/index.html` in a later `/deliver` pass.
