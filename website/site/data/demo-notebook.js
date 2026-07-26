window.__FLIP_NOTEBOOK__ = {
  "contract": "flip-render/2",
  "generated": "2026-07-26T00:59:00Z",
  "source_trail_public": true,
  "notebook": {
    "uid": "nb-b2xvppvr",
    "slug": "sourdough-rise",
    "title": "Does hydration change sourdough rise time?",
    "kind": "research-review",
    "status": "active",
    "created": "2026-07-26",
    "updated": "2026-07-26",
    "visibility": "internal"
  },
  "sources": [
    {
      "id": "F1",
      "slug": "ridgeway-club-trial",
      "kind": "",
      "grade": "B",
      "independence": "independent",
      "freshness": "",
      "support": {
        "basis": "panel",
        "method": "blind community trial, 40 bakers, self-reported rise times"
      },
      "title": "ridgeway-club-trial.md",
      "canonical_url": "",
      "captured_at": "2026-07-26T00:58:59Z",
      "sha256": "23361d2ad8567f738c1061198ca7059207dc31d368f2554f2679ed3a088d7d40"
    },
    {
      "id": "F2",
      "slug": "rise-times",
      "kind": "",
      "grade": "A",
      "independence": "independent",
      "freshness": "",
      "support": {
        "basis": "measured",
        "n": "12 bakes at four hydration levels",
        "base_defined": true
      },
      "title": "rise-times.csv",
      "canonical_url": "",
      "captured_at": "2026-07-26T00:58:59Z",
      "sha256": "d027275eb43b8be21aea527c5f24042e28f55923f5ced12c09175fbbc8120c6c"
    }
  ],
  "claims": [
    {
      "id": "C1",
      "slug": "doubling-time-falls-about-a-quarter-between-65",
      "text": "Doubling time falls about a quarter between 65% and 80% hydration",
      "status": "verified",
      "load_bearing": true,
      "sources": [
        "F1",
        "F2"
      ],
      "corroboration": 2,
      "verifications": []
    }
  ],
  "questions": [
    {
      "id": "Q1",
      "slug": "does-higher-hydration-shorten-the-time-to-double",
      "text": "Does higher hydration shorten the time to double?",
      "status": "open",
      "formulations": [],
      "resolves_via": []
    }
  ],
  "decisions": [
    {
      "id": "D1",
      "slug": "doubling-time-only",
      "text": "Doubling time only",
      "question": "Report doubling time or final crumb quality?",
      "alternatives_rejected": [
        "Crumb scoring \u2014 subjective and not recorded by the club"
      ]
    }
  ],
  "sessions": [
    {
      "id": "2026-07-26T0058-hydration-sweep",
      "actor": "human:baker",
      "model": "claude-opus-5",
      "started": "2026-07-26T00:58:59Z",
      "ended": "",
      "goal": ""
    }
  ],
  "log_tail": [],
  "forecasts": []
};
