// Original KagNode Core UI symbols. AGPL-3.0-only. Geometry is a 24-unit grid.
// Keep this source editable; tools/build-icons.mjs emits validated, optional assets.
const p = (d) => `<path d="${d}"/>`;
const r = (x, y, w, h, rx = 2) =>
  `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}"/>`;
const c = (x, y, r) => `<circle cx="${x}" cy="${y}" r="${r}"/>`;
const e = (x, y, rx, ry) =>
  `<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}"/>`;
const user = c(10, 7, 3) + p("M3 20v-2a7 7 0 0 1 14 0v2");
const shield = p("M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6Z");
const file = p("M5 3h9l5 5v13H5ZM14 3v5h5");
const folder = p("M3 7V4h7l3 3h8v13H3Z");
const calendar = r(3, 5, 18, 16) + p("M7 3v4m10-4v4M3 10h18");
const monitor = r(3, 3, 18, 13) + p("M8 21h8m-4-5v5");
const cloud = p("M6 18a4 4 0 1 1 0-8 6 6 0 0 1 12-2 5 5 0 0 1 0 10Z");
const envelope = r(3, 5, 18, 14) + p("m3 6 9 7 9-7");
const folderSmall = p("M2 6h7l2 3h7v11H2Z");
const badge = {
  plus: p("M19 14v8m-4-4h8"),
  minus: p("M15 18h8"),
  check: p("m15 18 3 3 5-7"),
  x: p("m16 15 6 6m-6 0 6-6"),
  lock: r(15, 16, 7, 6, 1) + p("M17 16v-2a1.5 1.5 0 0 1 3 0v2"),
  up: p("M19 22v-9m-4 4 4-4 4 4"),
  down: p("M19 13v9m-4-4 4 4 4-4"),
  clock: c(18, 18, 4) + p("M18 16v2l2 1"),
  star: p("m18 13 1.5 3 3.5.5-2.5 2.5.5 3.5-3-1.5-3 1.5.5-3.5-2.5-2.5 3.5-.5Z"),
};
const groups = {
  actions: [
    ["add", p("M12 4v16M4 12h16"), "create new plus"],
    ["subtract", p("M4 12h16"), "remove minus"],
    ["confirm", p("m4 12 5 6L20 5"), "accept done check"],
    ["cancel", p("m5 5 14 14M5 19 19 5"), "dismiss close x"],
    [
      "compose",
      p("m14 3 7 7M3 21l2-7L17 2l5 5L10 19ZM5 14l5 5"),
      "write pencil edit",
    ],
    ["erase", p("m3 14 11-11 8 8-11 11H7ZM8 9l8 8M11 22h11"), "eraser clear"],
    [
      "cut",
      c(6, 6, 3) + c(6, 18, 3) + p("m8 8 13 13M8 16 21 3"),
      "scissors clipboard",
    ],
    ["copy", r(8, 8, 13, 13) + p("M16 8V3H3v13h5"), "duplicate clipboard"],
    [
      "paste",
      r(7, 2, 10, 5) + p("M7 4H4v18h16V4h-3M8 11h8m-8 4h8m-8 4h5"),
      "clipboard insert",
    ],
    ["save", p("M3 3h15l3 3v15H3ZM7 3v6h10V3M7 21v-8h10v8"), "disk commit"],
    ["undo", p("M8 5 2 11l6 6M2 11h12a7 7 0 0 1 7 7v3"), "revert back"],
    ["redo", p("m16 5 6 6-6 6m6-6H10a7 7 0 0 0-7 7v3"), "repeat forward"],
    [
      "refresh-cycle",
      p("M21 9A9 9 0 0 0 5 5L2 9m0-6v6h6m-5 6a9 9 0 0 0 16 4l3-4m0 6v-6h-6"),
      "reload sync",
    ],
    ["filter", p("M3 4h18l-7 8v7l-4 2v-9Z"), "funnel refine"],
    ["sort", p("M8 3v18m-4-4 4 4 4-4M14 5h7m-7 5h5m-5 5h3"), "order ascending"],
    ["expand", p("M3 9V3h6m6 0h6v6M3 15v6h6m6 0h6v-6"), "fullscreen maximize"],
    [
      "collapse",
      p("M9 3v6H3m12-6v6h6M9 21v-6H3m12 6v-6h6"),
      "minimize contract",
    ],
    ["select-all", r(3, 3, 18, 18) + p("m7 12 3 3 7-7"), "selection checkbox"],
    [
      "drag-handle",
      c(8, 5, 1) +
        c(16, 5, 1) +
        c(8, 12, 1) +
        c(16, 12, 1) +
        c(8, 19, 1) +
        c(16, 19, 1),
      "grip move reorder",
    ],
    [
      "share",
      c(5, 12, 3) + c(19, 5, 3) + c(19, 19, 3) + p("m8 11 8-5m-8 7 8 5"),
      "distribute connections",
    ],
  ],
  navigation: [
    ["arrow-left", p("M21 12H3m7-7-7 7 7 7"), "back previous west"],
    ["arrow-right", p("M3 12h18m-7-7 7 7-7 7"), "next forward east"],
    ["arrow-up", p("M12 21V3m-7 7 7-7 7 7"), "north top"],
    ["arrow-down", p("M12 3v18m-7-7 7 7 7-7"), "south bottom"],
    ["chevron-left", p("m15 4-8 8 8 8"), "previous back"],
    ["chevron-right", p("m9 4 8 8-8 8"), "next forward"],
    ["chevron-up", p("m4 16 8-8 8 8"), "open above"],
    ["chevron-down", p("m4 8 8 8 8-8"), "disclosure below"],
    ["skip-start", p("M4 4v16m15-16L7 12l12 8Z"), "first beginning"],
    ["skip-end", p("M20 4v16M5 4l12 8-12 8Z"), "last ending"],
    [
      "home-door",
      p("M2 11 12 3l10 8M5 9v12h14V9M9 21v-8h6v8"),
      "house dashboard",
    ],
    ["compass", c(12, 12, 9) + p("m16 8-3 5-5 3 3-5Z"), "explore direction"],
    [
      "map",
      p("m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2ZM9 3v16m6-14v16"),
      "location route",
    ],
    [
      "map-pin",
      p("M19 10c0 5-7 12-7 12S5 15 5 10a7 7 0 0 1 14 0Z") + c(12, 10, 2),
      "location place",
    ],
    [
      "route",
      c(5, 5, 2) + c(19, 19, 2) + p("M7 5h9a4 4 0 0 1 0 8H8a3 3 0 0 0 0 6h9"),
      "directions journey",
    ],
    [
      "signpost",
      p("M12 2v20M3 5h15l3 3-3 3H3Zm18 9H6l-3 3 3 3h15Z"),
      "wayfinding directions",
    ],
    ["menu-lines", p("M3 5h18M3 12h18M3 19h18"), "hamburger navigation"],
    [
      "overflow-horizontal",
      c(4, 12, 1.5) + c(12, 12, 1.5) + c(20, 12, 1.5),
      "more ellipsis",
    ],
    [
      "overflow-vertical",
      c(12, 4, 1.5) + c(12, 12, 1.5) + c(12, 20, 1.5),
      "more kebab",
    ],
    [
      "open-external",
      p("M14 3h7v7m0-7L10 14M10 4H3v17h17v-7"),
      "new window link",
    ],
  ],
  accounts: [
    ["person", c(12, 7, 4) + p("M4 21v-2a8 8 0 0 1 16 0v2"), "user profile"],
    ["person-add", user + badge.plus, "invite signup create"],
    ["person-remove", user + badge.minus, "remove member"],
    ["person-verified", user + badge.check, "approved member"],
    ["person-blocked", user + badge.x, "suspend deny"],
    ["person-locked", user + badge.lock, "private protected"],
    ["person-history", user + badge.clock, "activity last seen"],
    ["person-favorite", user + badge.star, "preferred contact"],
    [
      "people",
      c(8, 7, 3) +
        p("M2 21v-3a6 6 0 0 1 12 0v3M17 4a3 3 0 0 1 0 6m0 4a5 5 0 0 1 5 5v2"),
      "group team",
    ],
    [
      "contact-card",
      r(2, 4, 20, 16) + c(8, 10, 2) + p("M4 17a4 4 0 0 1 8 0m3-8h4m-4 4h4"),
      "address book identity",
    ],
    [
      "identity-badge",
      r(5, 5, 14, 17) +
        p("M9 2h6v5H9Z") +
        c(12, 12, 2) +
        p("M8 19a4 4 0 0 1 8 0"),
      "employee credential",
    ],
    ["login-door", p("M14 3h7v18h-7M2 12h15m-5-5 5 5-5 5"), "sign in enter"],
    ["logout-door", p("M10 3H3v18h7m-1-9h13m-5-5 5 5-5 5"), "sign out exit"],
    [
      "account-switch",
      c(6, 8, 3) + c(18, 16, 3) + p("M13 3h8v7m0-7-6 6M11 21H3v-7m0 7 6-6"),
      "change user impersonate",
    ],
    [
      "fingerprint",
      p(
        "M3 12a9 9 0 0 1 18 0m-15 5v-5a6 6 0 0 1 12 0v4m-9 5v-9a3 3 0 0 1 6 0v7m-3-7v10M3 16v3m15 1v1",
      ),
      "biometric identity",
    ],
    [
      "anonymous",
      p("M3 9h18M5 9l3-6 4 2 4-2 3 6M2 14h8m4 0h8m-12 1h4") +
        c(6, 16, 3) +
        c(18, 16, 3),
      "incognito privacy guest",
    ],
    [
      "crown",
      p("m3 6 5 5 4-8 4 8 5-5-2 13H5ZM5 22h14"),
      "owner administrator premium",
    ],
    [
      "graduation",
      p("m2 9 10-6 10 6-10 6Zm4 3v6c4 3 8 3 12 0v-6m4-3v10"),
      "education student learning",
    ],
    [
      "handshake",
      p(
        "m2 7 4-3 5 3 3-2 8 4-4 9-4 3-8-5Zm9 0-4 5 3 2 4-4 6 5M2 7l4 9m7-1 4 4m-7-1 3 3",
      ),
      "collaborate agreement partner",
    ],
    [
      "organization",
      r(8, 2, 8, 5) +
        r(2, 17, 6, 5) +
        r(16, 17, 6, 5) +
        p("M12 7v5M5 17v-5h14v5"),
      "team hierarchy roles",
    ],
  ],
  security: [
    ["shield", shield, "protection security"],
    ["shield-check", shield + p("m8 12 3 3 5-6"), "verified safe"],
    ["shield-alert", shield + p("M12 8v5m0 3h.01"), "warning threat"],
    ["shield-cross", shield + p("m9 9 6 6m-6 0 6-6"), "unsafe rejected"],
    [
      "shield-key",
      shield + c(11, 11, 2) + p("m13 12 3 3m-1-1 1-1"),
      "authorization access",
    ],
    [
      "padlock",
      r(5, 10, 14, 12) + p("M8 10V6a4 4 0 0 1 8 0v4M12 15v3"),
      "locked password",
    ],
    [
      "padlock-open",
      r(5, 10, 14, 12) + p("M8 10V6a4 4 0 0 1 8 0M12 15v3"),
      "unlock public",
    ],
    [
      "key",
      c(7, 8, 5) + p("m11 12 10 10m-4-4 3-3m-6 0 3-3"),
      "secret credential",
    ],
    [
      "key-card",
      r(3, 4, 18, 16) + p("M3 9h18M7 14h4m-4 3h7") + c(17, 15, 1),
      "access pass swipe",
    ],
    [
      "password",
      r(2, 6, 20, 12) + p("m6 10 4 4m-4 0 4-4m4 0 4 4m-4 0 4-4"),
      "credentials masked",
    ],
    [
      "scan-face",
      p("M3 8V3h5m8 0h5v5M3 16v5h5m8 0h5v-5M8 10h.01M16 10h.01M8 15q4 4 8 0"),
      "biometric recognition",
    ],
    [
      "scan-code",
      p("M3 8V3h5m8 0h5v5M3 16v5h5m8 0h5v-5M7 7v10m3-10v10m4-10v10m3-10v10"),
      "barcode scanner",
    ],
    [
      "captcha",
      r(3, 4, 18, 16) + p("m6 15 3-6 3 6m-5-2h4m3-4h4l-4 6h4"),
      "human verification",
    ],
    [
      "firewall",
      p("M3 3h18v18H3ZM3 9h18M3 15h18M9 3v6m6 0v6m-6 0v6"),
      "network boundary bricks",
    ],
    [
      "siren",
      p(
        "M6 18v-7a6 6 0 0 1 12 0v7M3 18h18v4H3ZM12 1v1M3 5l2 2m14 0 2-2M1 12h2m18 0h2",
      ),
      "alarm incident",
    ],
    ["eye", p("M2 12q10-14 20 0-10 14-20 0Z") + c(12, 12, 3), "visible reveal"],
    [
      "eye-off",
      p("m3 3 18 18M8 5q8-3 14 7l-3 4M5 8l-3 4q7 10 15 6m-8-9a4 4 0 0 0 6 6"),
      "hidden conceal",
    ],
    [
      "audit-log",
      r(4, 3, 16, 19) + p("M8 7h8m-8 4h8m-8 4h4m-4 4h4m3-1 2 2 4-5"),
      "compliance verification record",
    ],
    [
      "certificate",
      p("M4 3h16v12H4ZM8 7h8m-8 4h5M9 15v7l3-2 3 2v-7"),
      "signed trust credential",
    ],
    [
      "two-factor",
      r(3, 2, 12, 20) + p("M7 18h4M18 7h4v9h-4M18 10h4m-2-3V5"),
      "mfa otp authentication",
    ],
  ],
  mail: [
    ["envelope", envelope, "email message"],
    [
      "envelope-open",
      p("M3 9 12 3l9 6v12H3Zm0 0 9 7 9-7M3 21l6-7m12 7-6-7"),
      "read email",
    ],
    ["mail-add", p("M13 19H3V5h18v7M3 6l9 7 9-7") + badge.plus, "new email"],
    [
      "mail-check",
      p("M13 19H3V5h18v7M3 6l9 7 9-7") + badge.check,
      "delivered verified",
    ],
    [
      "mail-lock",
      p("M13 19H3V5h18v7M3 6l9 7 9-7") + badge.lock,
      "encrypted private",
    ],
    [
      "mail-clock",
      p("M12 19H3V5h18v7M3 6l9 7 9-7") + badge.clock,
      "scheduled deferred",
    ],
    [
      "mail-warning",
      p("M12 19H3V5h18v7M3 6l9 7 9-7") + p("m18 13 5 9H13ZM18 16v2m0 2h.01"),
      "delivery failed alert",
    ],
    [
      "inbox-tray",
      p("m3 13 3-9h12l3 9v8H3Zm0 0h5l2 3h4l2-3h5"),
      "incoming messages",
    ],
    [
      "outbox-tray",
      p("M3 13v8h18v-8M3 16h5l2 3h4l2-3h5M12 14V3m-4 4 4-4 4 4"),
      "outgoing messages",
    ],
    ["paper-plane", p("m2 3 20 9-20 9 4-9Zm4 9h16"), "send submit"],
    ["reply", p("m9 5-7 7 7 7M2 12h11q8 0 9 8"), "respond message"],
    [
      "reply-all",
      p("m7 5-6 7 6 7m7-14-6 7 6 7m-6-7h7q7 0 8 8"),
      "respond everyone",
    ],
    ["forward-message", p("m15 5 7 7-7 7m7-7H11q-8 0-9 8"), "redirect message"],
    [
      "attachment",
      p("m8 14 7-7a3 3 0 0 1 4 4L9 21a5 5 0 0 1-7-7L13 3a3 3 0 0 1 8 8L10 22"),
      "paperclip attach",
    ],
    [
      "mailbox",
      p(
        "M3 12V9a5 5 0 0 1 10 0v9H3Zm5-8h9a5 5 0 0 1 5 5v9h-9M8 18v4M6 12h4m7-5V2h4v5Z",
      ),
      "post delivery",
    ],
    [
      "newsletter",
      r(2, 4, 20, 16) + r(5, 7, 6, 5, 0) + p("M14 7h5m-5 4h5M5 15h14m-14 2h9"),
      "digest publication",
    ],
    [
      "conversation",
      p("M3 3h16v11H8l-5 4Zm7 14h7l4 4V9"),
      "thread messages chat",
    ],
    [
      "chat-bubble",
      p("M3 3h18v14H9l-6 5Z") + p("M7 8h10m-10 4h7"),
      "comment message",
    ],
    [
      "chat-typing",
      p("M3 3h18v14H9l-6 5Z") + c(7, 10, 0.7) + c(12, 10, 0.7) + c(17, 10, 0.7),
      "writing conversation",
    ],
    [
      "unsubscribe",
      p("M12 19H3V5h18v7M3 6l9 7 9-7") + badge.minus,
      "opt out stop mail",
    ],
  ],
  files: [
    ["document", file + p("M8 12h8m-8 4h6"), "text file"],
    [
      "document-add",
      p("M12 21H4V3h10l5 5v4M14 3v5h5") + badge.plus,
      "new file",
    ],
    [
      "document-check",
      p("M12 21H4V3h10l5 5v4M14 3v5h5") + badge.check,
      "verified saved",
    ],
    [
      "document-lock",
      p("M12 21H4V3h10l5 5v4M14 3v5h5") + badge.lock,
      "protected private",
    ],
    [
      "document-download",
      p("M12 21H4V3h10l5 5v4M14 3v5h5") + badge.down,
      "save export",
    ],
    [
      "document-upload",
      p("M12 21H4V3h10l5 5v4M14 3v5h5") + badge.up,
      "import submit",
    ],
    ["document-code", file + p("m9 11-3 3 3 3m6-6 3 3-3 3"), "source markup"],
    [
      "document-image",
      file + c(9, 11, 1) + p("m6 19 4-5 3 3 3-4 3 6"),
      "picture asset",
    ],
    [
      "document-audio",
      file + p("M14 11v6m0-6 3 1") + e(11, 18, 3, 2),
      "sound recording",
    ],
    [
      "document-zip",
      file + p("M10 3v2m0 2v2m0 2v2m-1 2h3v4H9Z"),
      "compressed archive",
    ],
    ["folder-closed", folder, "directory projects"],
    [
      "folder-open",
      p("M3 10V4h7l3 3h8v4M3 10h19l-4 11H3Z"),
      "directory expanded",
    ],
    ["folder-add", folderSmall + badge.plus, "new directory"],
    ["folder-locked", folderSmall + badge.lock, "private directory"],
    ["folder-download", folderSmall + badge.down, "export directory"],
    ["folder-checked", folderSmall + badge.check, "synced directory"],
    [
      "archive-box",
      r(2, 3, 20, 5, 1) + p("M4 8v13h16V8M9 12h6"),
      "storage package",
    ],
    [
      "trash-bin",
      p("M3 6h18M8 6V3h8v3M5 6l1 15h12l1-15M10 10v7m4-7v7"),
      "delete garbage",
    ],
    [
      "hard-drive",
      p("m3 14 3-10h12l3 10v7H3Zm0 0h18m-5 4h2m-11 0h.01"),
      "disk volume",
    ],
    [
      "stack-documents",
      p("M8 2h13v15H8ZM5 5H3v17h15v-2M11 6h7m-7 4h7m-7 3h4"),
      "multiple files batch",
    ],
  ],
  media: [
    ["play", p("m7 3 14 9-14 9Z"), "start video audio"],
    ["pause", r(5, 3, 4, 18, 0) + r(15, 3, 4, 18, 0), "hold playback"],
    ["stop", r(4, 4, 16, 16, 1), "end playback"],
    ["record", c(12, 12, 8), "capture recording"],
    ["fast-forward", p("m2 5 10 7-10 7Zm10 0 10 7-10 7Z"), "seek ahead"],
    ["rewind", p("m12 5-10 7 10 7Zm10 0-10 7 10 7Z"), "seek back"],
    [
      "volume",
      p("M3 9h4l6-6v18l-6-6H3Zm14-2q5 5 0 10m3-13q5 8 0 16"),
      "sound speaker loud",
    ],
    [
      "volume-low",
      p("M3 9h4l6-6v18l-6-6H3Zm14 0a4 4 0 0 1 0 6"),
      "quiet sound",
    ],
    [
      "volume-mute",
      p("M3 9h4l6-6v18l-6-6H3Zm14 0 5 6m-5 0 5-6"),
      "silent sound off",
    ],
    [
      "microphone",
      r(9, 2, 6, 13, 3) + p("M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8"),
      "record voice",
    ],
    [
      "microphone-off",
      p(
        "m3 3 18 18M9 8v4a3 3 0 0 0 5 2m1-5V5a3 3 0 0 0-5-2M5 10v2a7 7 0 0 0 12 5m2-4v-3M12 19v3m-4 0h8",
      ),
      "mute voice",
    ],
    ["camera", p("M2 7h5l2-4h6l2 4h5v14H2Z") + c(12, 13, 4), "photo capture"],
    [
      "video-camera",
      r(2, 5, 13, 14) + p("m15 10 7-4v12l-7-4Z"),
      "film capture call",
    ],
    [
      "film-strip",
      r(3, 2, 18, 20) +
        p("M7 2v20M17 2v20M3 7h4M3 12h4M3 17h4m10-10h4m-4 5h4m-4 5h4"),
      "movie cinema",
    ],
    [
      "music-note",
      p("M9 18V5l12-3v13M9 9l12-3") + e(6, 19, 3, 2) + e(18, 16, 3, 2),
      "song audio",
    ],
    [
      "headphones",
      p("M3 14v-2a9 9 0 0 1 18 0v2") + r(3, 12, 4, 9) + r(17, 12, 4, 9),
      "listen audio",
    ],
    [
      "image-landscape",
      r(2, 3, 20, 18) + c(8, 8, 2) + p("m2 18 6-6 5 5 4-7 5 8"),
      "picture gallery",
    ],
    ["crop", p("M7 2v15h15M2 7h15v15m0-15 5-5"), "frame resize"],
    [
      "shuffle",
      p("M3 5h3l12 14h4m-4-4 4 4-4 4M3 19h3l12-14h4m-4-4 4 4-4 4"),
      "random playback",
    ],
    [
      "repeat",
      p("M4 9V5h16m-4-4 4 4-4 4m4 6v4H4m4-4-4 4 4 4"),
      "loop playback",
    ],
  ],
  cloud: [
    ["cloud", cloud, "remote online"],
    [
      "cloud-upload",
      p(
        "M7 18H6a4 4 0 1 1 0-8 6 6 0 0 1 12-2 5 5 0 0 1 0 10h-1M12 22V11m-4 4 4-4 4 4",
      ),
      "backup remote",
    ],
    [
      "cloud-download",
      p(
        "M7 18H6a4 4 0 1 1 0-8 6 6 0 0 1 12-2 5 5 0 0 1 0 10h-1M12 11v11m-4-4 4 4 4-4",
      ),
      "restore remote",
    ],
    ["cloud-check", cloud + p("m8 13 3 3 5-5"), "synced available"],
    [
      "cloud-off",
      p("m2 2 20 20M6 10a4 4 0 1 0 0 8h12M9 5a6 6 0 0 1 9 3 5 5 0 0 1 3 8"),
      "offline disconnected",
    ],
    [
      "server",
      r(3, 2, 18, 8) + r(3, 14, 18, 8) + p("M7 6h.01M7 18h.01M11 6h6m-6 12h6"),
      "host compute",
    ],
    [
      "server-stack",
      r(3, 2, 18, 6, 1) +
        r(3, 9, 18, 6, 1) +
        r(3, 16, 18, 6, 1) +
        p("M6 5h.01M6 12h.01M6 19h.01m4-14h8m-8 7h8m-8 7h8"),
      "rack cluster",
    ],
    [
      "database",
      e(12, 5, 9, 3) + p("M3 5v14c0 4 18 4 18 0V5M3 12c0 4 18 4 18 0"),
      "data storage",
    ],
    [
      "database-backup",
      e(10, 5, 7, 3) +
        p("M3 5v13c0 3 8 4 11 2M3 11c0 3 10 4 14 1V5") +
        badge.clock,
      "snapshot restore",
    ],
    [
      "container",
      p("m3 7 9-4 9 4v11l-9 4-9-4Zm0 0 9 4 9-4M12 11v11M7 5l10 5"),
      "deploy package",
    ],
    [
      "load-balancer",
      r(8, 2, 8, 5) +
        r(1, 17, 6, 5) +
        r(9, 17, 6, 5) +
        r(17, 17, 6, 5) +
        p("M12 7v10M4 17v-5h16v5"),
      "traffic distribution",
    ],
    [
      "replication",
      r(2, 2, 8, 7) +
        r(14, 15, 8, 7) +
        p("M14 3h6v8m-3-3 3 3 3-3M10 21H4v-8m-3 3 3-3 3 3"),
      "mirror data sync",
    ],
    [
      "deploy",
      p("m12 2 6 7-3 9H9L6 9Zm-6 7-4 8 7 1m9-9 4 8-7 1m-5 3 2 2 2-2") +
        c(12, 9, 2),
      "launch rocket release",
    ],
    [
      "service",
      r(7, 7, 10, 10) +
        p("M12 2v5m0 10v5M2 12h5m10 0h5M5 5l3 3m8 8 3 3M5 19l3-3m8-8 3-3"),
      "endpoint process",
    ],
    [
      "snapshot",
      p("M6 3h15v15M3 6h15v15H3Z") + c(10, 13, 4),
      "point in time image",
    ],
    [
      "cloud-queue",
      p("M6 12a3 3 0 1 1 0-6 5 5 0 0 1 10 0 3 3 0 0 1 3 6M3 16h18M3 20h18") +
        c(6, 16, 0.7) +
        c(6, 20, 0.7),
      "jobs messages backlog",
    ],
    [
      "region",
      c(12, 12, 9) +
        p("M3 12h18M12 3q-9 9 0 18 9-9 0-18M5 7h14m-14 10h14") +
        c(17, 8, 2),
      "geographic data center",
    ],
    [
      "edge-node",
      c(12, 12, 3) +
        c(4, 4, 2) +
        c(20, 4, 2) +
        c(4, 20, 2) +
        c(20, 20, 2) +
        p("m6 6 4 4m4 4 4 4M6 18l4-4m4-4 4-4"),
      "distributed delivery",
    ],
    [
      "cloud-settings",
      p(
        "M8 18H6a4 4 0 1 1 0-8 6 6 0 0 1 12-2 5 5 0 0 1 3 8M12 14v8m6-8v8m-8-6h4m2 4h4",
      ),
      "remote configuration",
    ],
    ["uptime", p("M2 13h4l3-9 6 16 3-7h4"), "availability heartbeat"],
  ],
  network: [
    [
      "wifi",
      p("M2 7a16 16 0 0 1 20 0M5 11a11 11 0 0 1 14 0M8 15a6 6 0 0 1 8 0") +
        c(12, 20, 1),
      "wireless connection",
    ],
    [
      "wifi-off",
      p(
        "m2 2 20 20M7 4a16 16 0 0 1 15 3M2 7l2-1m7 3a11 11 0 0 1 8 2M5 11l2-1m1 5a6 6 0 0 1 8 0",
      ) + c(12, 20, 1),
      "wireless disconnected",
    ],
    [
      "ethernet",
      p("M4 3h16v11l-4 4v4H8v-4l-4-4ZM7 3v6m3-6v6m4-6v6m3-6v6M8 18h8"),
      "wired port rj45",
    ],
    [
      "router",
      r(2, 13, 20, 8) + p("M6 13V3m12 10V3M6 17h.01m4 0h.01m4 0h4"),
      "gateway wireless",
    ],
    [
      "switch-network",
      r(2, 8, 20, 9) +
        p("M5 11v3m4-3v3m4-3v3m4-3v3M6 3v5m6-5v5m6-5v5M6 17v4m6-4v4m6-4v4"),
      "lan ports",
    ],
    [
      "globe",
      c(12, 12, 10) + e(12, 12, 4, 10) + p("M2 12h20M4 6h16M4 18h16"),
      "internet world",
    ],
    [
      "link-chain",
      p("m9 6 2-2a6 6 0 0 1 9 9l-2 2M6 9l-2 2a6 6 0 0 0 9 9l2-2M8 16l8-8"),
      "url connection",
    ],
    [
      "link-broken",
      p(
        "m14 4 1-1a5 5 0 0 1 7 7l-3 3M10 20l-1 1a5 5 0 0 1-7-7l3-3M2 2l20 20M9 2v3M2 9h3m14 3h3m-10 7v3",
      ),
      "unlink disconnected",
    ],
    [
      "broadcast",
      c(12, 12, 2) +
        p("M7 7q-4 5 0 10m10-10q4 5 0 10M4 4q-5 8 0 16M20 4q5 8 0 16"),
      "radio live signal",
    ],
    [
      "antenna",
      p(
        "M12 8v14M7 22h10M8 4a6 6 0 0 0 0 8m8-8a6 6 0 0 1 0 8M5 1a10 10 0 0 0 0 14M19 1a10 10 0 0 1 0 14",
      ) + c(12, 8, 1),
      "tower radio",
    ],
    ["bluetooth", p("m5 6 14 12-7 5V1l7 5L5 18"), "wireless pairing"],
    [
      "vpn-tunnel",
      p(
        "M2 21V11a10 10 0 0 1 20 0v10M6 21V11a6 6 0 0 1 12 0v10M10 21V11a2 2 0 0 1 4 0v10",
      ),
      "private tunnel",
    ],
    [
      "dns",
      r(3, 3, 18, 7) +
        r(3, 14, 18, 7) +
        p("M6 6h.01M6 17h.01M11 6h7m-7 11h7M12 10v4"),
      "domain names resolver",
    ],
    [
      "signal-bars",
      r(3, 16, 3, 6, 0) +
        r(8, 12, 3, 10, 0) +
        r(13, 7, 3, 15, 0) +
        r(18, 2, 3, 20, 0),
      "cellular reception",
    ],
    [
      "network-upload",
      p("M3 21h18M12 17V3m-6 6 6-6 6 6"),
      "outbound bandwidth",
    ],
    [
      "network-download",
      p("M3 21h18M12 3v14m-6-6 6 6 6-6"),
      "inbound bandwidth",
    ],
    [
      "bidirectional",
      p("M3 7h17m-5-5 5 5-5 5M21 17H4m5-5-5 5 5 5"),
      "traffic transfer duplex",
    ],
    [
      "latency",
      c(12, 13, 9) + p("M9 1h6m-3 0v3m6 2 2-2M12 13l5-5"),
      "ping response delay",
    ],
    [
      "satellite",
      p(
        "m8 8 8 8-4 4-8-8Zm7-5 6 6-4 4-6-6ZM7 17l-4 4m1-9a8 8 0 0 1 8 8M2 16a4 4 0 0 1 4 4",
      ),
      "orbit communications",
    ],
    [
      "connections",
      c(12, 4, 2) +
        c(4, 18, 2) +
        c(20, 18, 2) +
        c(12, 12, 2) +
        p("M12 6v4m-2 3-5 3m9-3 5 3"),
      "peers topology",
    ],
  ],
  devices: [
    ["desktop", monitor, "computer display"],
    [
      "laptop",
      r(5, 3, 14, 13) + p("m5 16-3 5h20l-3-5M9 19h6"),
      "notebook computer",
    ],
    ["phone", r(6, 2, 12, 20, 3) + p("M10 5h4m-3 14h2"), "mobile smartphone"],
    ["tablet", r(3, 2, 18, 20, 2) + c(12, 19, 0.6), "mobile slate"],
    [
      "watch",
      r(6, 6, 12, 12, 3) + p("M8 6V2h8v4M8 18v4h8v-4M12 9v3l2 2"),
      "wearable smartwatch",
    ],
    [
      "keyboard",
      r(2, 6, 20, 14) +
        p(
          "M5 10h.01m4 0h.01m4 0h.01m4 0h.01M5 14h.01m4 0h.01m4 0h.01m4 0h.01M7 17h10",
        ),
      "typing input",
    ],
    ["mouse", r(6, 2, 12, 20, 6) + p("M6 10h12m-6-8v8"), "pointer input"],
    [
      "printer",
      p("M6 8V2h12v6M6 18H2V8h20v10h-4M6 14h12v8H6Zm11-3h2"),
      "paper output",
    ],
    [
      "scanner",
      p("m3 11 4-8 14 7M3 13h18v8H3Zm4 4h10m-10 2h7"),
      "document digitizer",
    ],
    [
      "usb-drive",
      r(7, 9, 10, 13) + p("M9 9V2h6v7M11 5h.01m2 0h.01"),
      "flash removable storage",
    ],
    [
      "sd-card",
      p("M5 2h12l3 3v17H4V3Zm3 0v6m4-6v6m4-6v6M8 13h8v5H8Z"),
      "memory card storage",
    ],
    [
      "battery-full",
      r(2, 6, 18, 12) + p("M20 10h2v4h-2M5 9v6m4-6v6m4-6v6m4-6v6"),
      "power charged",
    ],
    [
      "battery-low",
      r(2, 6, 18, 12) + p("M20 10h2v4h-2M5 9v6"),
      "power remaining",
    ],
    [
      "battery-charging",
      p("M8 6H2v12h6m8-12h4v12h-4m4-8h2v4h-2M13 3l-5 10h5l-2 8 7-12h-5Z"),
      "charge power",
    ],
    [
      "plug",
      p("M8 2v6m8-6v6M5 8h14v3a7 7 0 0 1-14 0Zm7 10v4"),
      "electric connect",
    ],
    ["power-button", p("M12 2v10M7 5a9 9 0 1 0 10 0"), "start shutdown"],
    [
      "processor",
      r(6, 6, 12, 12) +
        r(9, 9, 6, 6, 0) +
        p("M9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4"),
      "cpu chip",
    ],
    [
      "memory-module",
      r(2, 5, 20, 14) +
        r(5, 8, 5, 7, 0) +
        r(14, 8, 5, 7, 0) +
        p("M5 19v3m4-3v3m6-3v3m4-3v3"),
      "ram dimm",
    ],
    [
      "game-controller",
      p(
        "M8 6h8q5 0 6 12c0 4-5 3-7-1H9c-2 4-7 5-7 1Q3 6 8 6ZM7 9v6m-3-3h6m6-2h.01m3 3h.01",
      ),
      "gamepad play",
    ],
    [
      "projector",
      r(2, 8, 20, 11) +
        c(16, 13, 3) +
        p("M5 11h4m-4 3h3M6 19v3m12-3v3M8 2l8 6"),
      "presentation display",
    ],
  ],
  developer: [
    [
      "terminal",
      r(2, 3, 20, 18) + p("m6 8 4 4-4 4m7 0h5"),
      "shell console cli",
    ],
    [
      "code-brackets",
      p("m8 5-6 7 6 7m8-14 6 7-6 7M14 2l-4 20"),
      "source programming",
    ],
    ["braces", p("M9 2H7v7l-3 3 3 3v7h2m6-20h2v7l3 3-3 3v7h-2"), "json object"],
    [
      "git-branch",
      c(6, 4, 2) + c(6, 20, 2) + c(18, 4, 2) + p("M6 6v12m0-5h5a7 7 0 0 0 7-7"),
      "version source control",
    ],
    [
      "git-merge",
      c(6, 4, 2) +
        c(6, 20, 2) +
        c(18, 20, 2) +
        p("M6 6v12m0-9h5a7 7 0 0 1 7 7v2"),
      "combine branch",
    ],
    ["git-commit", c(12, 12, 4) + p("M2 12h6m8 0h6"), "revision snapshot"],
    [
      "pull-request",
      c(6, 4, 2) +
        c(6, 20, 2) +
        c(18, 20, 2) +
        p("M6 6v12m12 0V9a4 4 0 0 0-4-4h-2m3-3-3 3 3 3"),
      "review change",
    ],
    [
      "bug",
      r(7, 7, 10, 14, 5) +
        p(
          "M9 7 6 3m9 4 3-4M3 9h4m10 0h4M2 15h5m10 0h5M4 21l4-3m8 0 4 3M12 7v14",
        ),
      "defect debug",
    ],
    [
      "wrench",
      p("M14 3a6 6 0 0 0-7 8L2 16a3 3 0 0 0 4 4l6-6a6 6 0 0 0 8-7l-4 4-4-4Z"),
      "repair tools",
    ],
    [
      "hammer",
      p("m13 3 8 8-4 4-3-3L5 22l-3-3 10-10-3-3ZM9 6l4-3"),
      "build construct",
    ],
    [
      "test-tube",
      p("M9 2h10m-8 0v10L4 19a2 2 0 0 0 1 3h9a2 2 0 0 0 2-3l-1-7V2M8 15h8"),
      "experiment laboratory",
    ],
    [
      "binary",
      p("M3 3h5v7H3ZM16 3h2v7m-3 0h6M3 14h2v7m-3 0h6m7-7h5v7h-5Z"),
      "bits machine data",
    ],
    [
      "api",
      r(2, 7, 6, 10, 1) +
        r(16, 7, 6, 10, 1) +
        p("M8 12h8m-5-3 3 3-3 3M5 3v4m14 10v4"),
      "integration endpoint",
    ],
    [
      "webhook",
      c(5, 5, 3) + c(19, 5, 3) + c(12, 19, 3) + p("m7 8 4 8m6-8-4 8M8 5h8"),
      "callback event",
    ],
    [
      "package-box",
      p("m2 7 10-5 10 5v11l-10 5-10-5Zm0 0 10 5 10-5M12 12v11M7 4l10 5v5"),
      "dependency module",
    ],
    [
      "puzzle",
      p(
        "M4 4h6a2 2 0 1 1 4 0h6v6a2 2 0 1 0 0 4v6h-6a2 2 0 1 0-4 0H4v-6a2 2 0 1 1 0-4Z",
      ),
      "extension plugin",
    ],
    [
      "regex",
      p("M5 4v8m-4-6 8 4m-8 0 8-4M14 3h7v7m-7 4 7 7m-7 0 7-7") + c(5, 19, 1),
      "pattern match expression",
    ],
    [
      "diff",
      r(3, 2, 18, 20) + p("M7 7h10m-5 6v6m-3-3h6"),
      "change patch compare",
    ],
    [
      "pipeline",
      r(1, 9, 6, 6, 1) +
        r(9, 2, 6, 6, 1) +
        r(17, 9, 6, 6, 1) +
        p("M7 12h5V8m0 0v4h5M12 12v9"),
      "workflow automation ci",
    ],
    [
      "breakpoint",
      p("M3 3h11l7 9-7 9H3Z") + c(10, 12, 3),
      "debug pause execution",
    ],
  ],
  calendar: [
    [
      "calendar-grid",
      calendar + p("M7 14h.01m5 0h.01m5 0h.01M7 18h.01m5 0h.01m5 0h.01"),
      "date month",
    ],
    [
      "calendar-add",
      p("M12 21H3V5h18v7M7 3v4m10-4v4M3 10h18") + badge.plus,
      "new event",
    ],
    [
      "calendar-check",
      p("M12 21H3V5h18v7M7 3v4m10-4v4M3 10h18") + badge.check,
      "confirmed scheduled",
    ],
    [
      "calendar-clock",
      p("M12 21H3V5h18v7M7 3v4m10-4v4M3 10h18") + badge.clock,
      "appointment time",
    ],
    [
      "calendar-remove",
      p("M12 21H3V5h18v7M7 3v4m10-4v4M3 10h18") + badge.minus,
      "cancel event",
    ],
    [
      "calendar-range",
      calendar + p("M6 14h12M6 18h6"),
      "duration interval dates",
    ],
    ["calendar-day", calendar + r(8, 12, 8, 7, 0), "today single date"],
    [
      "calendar-week",
      calendar + p("M7 10v11m5-11v11m5-11v11"),
      "weekly schedule",
    ],
    ["clock-face", c(12, 12, 10) + p("M12 6v6l4 3"), "time watch"],
    [
      "alarm-clock",
      c(12, 13, 8) + p("M12 8v5l3 2M3 4l3-3m12 0 3 3M5 20l-2 3m16-3 2 3"),
      "reminder wake",
    ],
    [
      "stopwatch",
      c(12, 14, 8) + p("M9 2h6m-3 0v4m6 2 3-3M12 10v4l3 2"),
      "timer elapsed",
    ],
    [
      "hourglass",
      p("M5 2h14M5 22h14M7 2v5l5 5-5 5v5m10-20v5l-5 5 5 5v5M9 6h6m-5 12h4"),
      "waiting duration",
    ],
    [
      "history",
      p("M3 10a9 9 0 1 1 1 8M3 3v7h7M12 7v6l4 2"),
      "past activity recent",
    ],
    [
      "sunrise",
      p(
        "M2 18h20M6 18a6 6 0 0 1 12 0M12 2v7m-3-3 3-3 3 3M3 10l3 3m12 0 3-3M2 22h20",
      ),
      "morning start day",
    ],
    [
      "sunset",
      p(
        "M2 18h20M6 18a6 6 0 0 1 12 0M12 2v7m-3-3 3 3 3-3M3 10l3 3m12 0 3-3M2 22h20",
      ),
      "evening end day",
    ],
    [
      "night",
      p("M17 3A9 9 0 1 0 21 16 9 9 0 0 1 17 3ZM6 5h3M7.5 3.5v3"),
      "moon overnight",
    ],
    [
      "deadline",
      p("M5 22V2m0 1h15l-4 5 4 5H5") + c(16, 18, 4) + p("M16 16v2l2 1"),
      "due target time",
    ],
    [
      "calendar-repeat",
      p("M10 21H3V5h18v7M7 3v4m10-4v4M3 10h18M21 16a4 4 0 1 0 0 5m0 2v-3h-3"),
      "recurring event",
    ],
    [
      "time-zone",
      c(10, 10, 8) +
        p("M2 10h16M10 2q-6 8 0 16 6-8 0-16") +
        c(18, 18, 4) +
        p("M18 16v2l2 1"),
      "world local time",
    ],
    [
      "booking",
      r(3, 3, 18, 18) +
        p("M3 8h18M8 3v5m8-5v5M7 13h10m-10 4h6") +
        p("m17 17 2 2 3-4"),
      "reservation schedule",
    ],
  ],
  status: [
    [
      "success-circle",
      c(12, 12, 10) + p("m6 12 4 4 8-8"),
      "done valid complete",
    ],
    ["error-circle", c(12, 12, 10) + p("m8 8 8 8m-8 0 8-8"), "failed invalid"],
    ["warning-triangle", p("m12 2 11 20H1ZM12 9v5m0 4h.01"), "caution alert"],
    ["information", c(12, 12, 10) + p("M12 11v7m0-12h.01"), "details about"],
    [
      "question",
      c(12, 12, 10) + p("M8 8a4 4 0 1 1 6 4c-2 1-2 2-2 3m0 3h.01"),
      "help unknown",
    ],
    ["pending", c(12, 12, 10) + p("M7 12h10"), "waiting unresolved"],
    ["loading", p("M12 2a10 10 0 1 1-10 10"), "spinner busy"],
    ["progress", c(12, 12, 10) + p("M12 2v10l7 7"), "completion portion"],
    [
      "notification",
      p("M5 9a7 7 0 0 1 14 0v8l3 2H2l3-2Zm4 13h6"),
      "bell alerts",
    ],
    [
      "notification-off",
      p("m2 2 20 20M5 9v8l-3 2h16M9 3a7 7 0 0 1 10 6v6M9 22h6"),
      "silent muted bell",
    ],
    ["flag", p("M4 22V2m0 1h15l-3 5 3 5H4"), "report milestone"],
    ["bookmark", p("M5 2h14v20l-7-5-7 5Z"), "saved read later"],
    [
      "heart-outline",
      p("M12 22 3 13C-3 5 7-1 12 6c5-7 15-1 9 7Z"),
      "favorite love",
    ],
    [
      "star-outline",
      p("m12 2 3 6 7 1-5 5 1 8-6-4-6 4 1-8-5-5 7-1Z"),
      "rating favorite",
    ],
    ["thumb-up", p("M3 10h5v12H3Zm5 0 6-8 2 1v6h6l-3 13H8Z"), "approve like"],
    [
      "thumb-down",
      p("M3 2h5v12H3Zm5 12 6 8 2-1v-6h6L19 2H8Z"),
      "disapprove dislike",
    ],
    ["ban", c(12, 12, 10) + p("M5 5l14 14"), "forbidden prohibited"],
    [
      "offline-dot",
      c(9, 9, 7) + c(19, 19, 3) + p("M17 19h4"),
      "unavailable disconnected",
    ],
    [
      "verified-seal",
      p("m12 2 3 2 4 1 1 4 2 3-2 3-1 4-4 1-3 2-3-2-4-1-1-4-2-3 2-3 1-4 4-1Z") +
        p("m7 12 3 3 7-7"),
      "certified trusted",
    ],
    [
      "announcement",
      p("M3 8h5l13-5v18L8 16H3Zm5 8 3 6H7l-2-6m3-8v8"),
      "megaphone news",
    ],
  ],
  accessibility: [
    [
      "accessibility-person",
      c(12, 4, 2) + p("M3 9h18m-9 0v6m0-3-6 10m6-10 6 10"),
      "universal access",
    ],
    [
      "wheelchair",
      c(10, 3, 2) + p("M10 5v8h8l3 7M10 9h6M6 11a6 6 0 1 0 9 8"),
      "mobility accessible",
    ],
    [
      "hearing",
      p(
        "M5 10a7 7 0 0 1 14 0c0 5-6 5-6 9a3 3 0 0 1-6 0M9 10a3 3 0 0 1 6 0c0 3-4 2-4 6",
      ),
      "ear audio support",
    ],
    [
      "hearing-off",
      p(
        "m2 2 20 20M5 10a7 7 0 0 1 1-4m4-3a7 7 0 0 1 9 7c0 5-6 5-6 9a3 3 0 0 1-6 0M9 10q0-1 1-2",
      ),
      "deaf muted",
    ],
    [
      "captions",
      r(2, 5, 20, 14) + p("M10 9H6v6h4m8-6h-4v6h4"),
      "closed caption cc subtitles",
    ],
    [
      "text-size",
      p("M2 5h13M8.5 5v16M5 21h7m3-10h7m-3.5 0v10m-2.5 0h5"),
      "font scale type",
    ],
    [
      "contrast",
      c(12, 12, 10) + p("M12 2v20M12 6h6m-6 4h9m-9 4h9m-9 4h6"),
      "high contrast brightness",
    ],
    [
      "focus",
      p("M3 8V3h5m8 0h5v5M3 16v5h5m8 0h5v-5") + c(12, 12, 3),
      "keyboard target",
    ],
    [
      "keyboard-key",
      r(3, 3, 18, 18, 3) + p("M8 8h8v6H8Zm4 0v6M6 17h12"),
      "shortcut input",
    ],
    [
      "hand",
      p(
        "M8 12V5a2 2 0 0 1 4 0v7m0-8a2 2 0 0 1 4 0v8m0-5a2 2 0 0 1 4 0v9c0 4-3 6-7 6H9L2 13a2 2 0 0 1 3-2l3 4",
      ),
      "touch gesture pan",
    ],
    [
      "touch-tap",
      p(
        "M10 14V8a2 2 0 0 1 4 0v6l5 1v4l-3 3h-6l-5-6a2 2 0 0 1 3-2l2 2M6 8a6 6 0 0 1 12 0",
      ),
      "pointer press",
    ],
    [
      "voice",
      p("M2 10v4m4-8v12m4-16v20m4-17v14m4-11v8m4-6v4"),
      "speech waveform",
    ],
    [
      "read-aloud",
      p("M2 4h8v16H2Zm8 0h5v16h-5M18 8q4 4 0 8m3-11q3 7 0 14"),
      "screen reader narration",
    ],
    [
      "braille",
      c(5, 5, 1) +
        c(5, 12, 1) +
        c(5, 19, 1) +
        c(11, 5, 1) +
        c(11, 19, 1) +
        c(18, 5, 1) +
        c(18, 12, 1),
      "tactile reading",
    ],
    [
      "reduced-motion",
      p("M2 6h6m-6 6h4m-4 6h6M14 5a7 7 0 1 1-3 13M14 5v7l4 2M3 22 22 3"),
      "animation preference",
    ],
    [
      "zoom-in",
      c(10, 10, 7) + p("m15 15 7 7M6 10h8m-4-4v8"),
      "magnify increase",
    ],
    ["zoom-out", c(10, 10, 7) + p("m15 15 7 7M6 10h8"), "magnify decrease"],
    [
      "reading-mode",
      p("M2 3h8l2 2 2-2h8v18h-8l-2 1-2-1H2ZM12 5v17M5 8h4m-4 4h4m6-4h4m-4 4h4"),
      "book legibility",
    ],
    [
      "language",
      p("M2 5h12M8 2v3m-4 3 8 10M12 5q0 9-10 14M13 22l5-13 5 13m-8-4h6"),
      "translate locale",
    ],
    [
      "text-cursor",
      p("M8 2h8m-4 0v20m-4 0h8M3 7v10m18-10v10"),
      "caret selection input",
    ],
  ],
  layout: [
    [
      "grid",
      r(3, 3, 7, 7, 1) +
        r(14, 3, 7, 7, 1) +
        r(3, 14, 7, 7, 1) +
        r(14, 14, 7, 7, 1),
      "tiles apps",
    ],
    [
      "list",
      p("M8 5h14M8 12h14M8 19h14") +
        c(3, 5, 0.8) +
        c(3, 12, 0.8) +
        c(3, 19, 0.8),
      "rows items",
    ],
    [
      "table",
      r(2, 3, 20, 18) + p("M2 9h20M2 15h20M9 3v18m7-18v18"),
      "spreadsheet data",
    ],
    [
      "sidebar-left",
      r(2, 3, 20, 18) + p("M8 3v18M4 7h2m-2 4h2m-2 4h2"),
      "panel navigation",
    ],
    [
      "sidebar-right",
      r(2, 3, 20, 18) + p("M16 3v18M18 7h2m-2 4h2m-2 4h2"),
      "inspector panel",
    ],
    ["split-horizontal", r(2, 3, 20, 18) + p("M12 3v18"), "columns panes"],
    ["split-vertical", r(2, 3, 20, 18) + p("M2 12h20"), "rows panes"],
    [
      "dashboard",
      r(2, 2, 9, 7, 1) +
        r(14, 2, 8, 12, 1) +
        r(2, 12, 9, 10, 1) +
        r(14, 17, 8, 5, 1),
      "overview widgets",
    ],
    ["align-left", p("M3 2v20M7 5h14M7 10h9M7 15h14M7 20h9"), "text start"],
    ["align-center", p("M3 4h18M7 9h10M3 14h18M7 19h10"), "text middle"],
    ["align-right", p("M21 2v20M3 5h14M8 10h9M3 15h14M8 20h9"), "text end"],
    ["justify", p("M3 4h18M3 9h18M3 14h18M3 19h18"), "text full width"],
    ["columns", r(2, 3, 20, 18) + p("M8 3v18m8-18v18"), "three layout"],
    ["rows", r(2, 3, 20, 18) + p("M2 9h20M2 15h20"), "three layout"],
    [
      "layers",
      p("m2 7 10-5 10 5-10 5Zm0 5 10 5 10-5M2 17l10 5 10-5"),
      "stack depth",
    ],
    [
      "ruler",
      p("m2 16 14-14 6 6L8 22Zm3-3 3 3m0-6 3 3m0-6 3 3m0-6 3 3"),
      "measure dimensions",
    ],
    [
      "palette",
      p(
        "M12 2a10 10 0 1 0 0 20h2a3 3 0 0 0 0-6h-1a2 2 0 0 1 0-4h4a5 5 0 0 0 5-5c0-3-5-5-10-5Z",
      ) +
        c(6, 11, 0.8) +
        c(8, 6, 0.8) +
        c(14, 6, 0.8),
      "colors theme",
    ],
    [
      "sliders",
      p(
        "M5 2v6m0 4v10M12 2v12m0 4v4M19 2v3m0 4v13M2 8h6v4H2Zm7 6h6v4H9Zm7-9h6v4h-6Z",
      ),
      "adjust preferences controls",
    ],
    [
      "window",
      r(2, 3, 20, 18) + p("M2 8h20M5 5.5h.01m3 0h.01m3 0h.01"),
      "browser application",
    ],
    [
      "picture-in-picture",
      r(2, 3, 20, 18) + r(12, 12, 8, 7, 0),
      "floating mini player",
    ],
  ],
  commerce: [
    [
      "cart",
      p("M2 3h3l3 13h11l3-9H6") + c(9, 21, 1) + c(18, 21, 1),
      "shopping basket checkout",
    ],
    [
      "basket",
      p("M2 9h20l-3 12H5ZM7 9l5-7 5 7M8 13v4m4-4v4m4-4v4"),
      "shop purchase",
    ],
    [
      "credit-card",
      r(2, 4, 20, 16) + p("M2 9h20M6 15h4m4 0h4"),
      "payment billing",
    ],
    [
      "wallet",
      p(
        "M21 7V3H5a3 3 0 0 0-3 3v13a3 3 0 0 0 3 3h16V7H5a2 2 0 0 1 0-4M21 12h-6v5h6",
      ) + c(17, 14.5, 0.5),
      "funds balance",
    ],
    [
      "receipt",
      p("M4 2 8 4l4-2 4 2 4-2v20l-4-2-4 2-4-2-4 2ZM8 8h8m-8 4h8m-8 4h5"),
      "invoice order",
    ],
    ["tag", p("M2 2h10l10 10-10 10L2 12Z") + c(7, 7, 1.5), "label price"],
    [
      "gift",
      r(2, 8, 20, 5, 0) +
        p("M4 13v9h16v-9M12 8v14M12 8C0 8 6-4 12 8c6-12 12 0 0 0"),
      "present reward",
    ],
    [
      "storefront",
      p("M3 9V3h18v6M2 9h20l-2 5-4-1-4 1-4-1-4 1ZM4 14v8h16v-8M8 22v-6h6v6"),
      "shop market",
    ],
    [
      "truck",
      p("M2 4h12v13H2Zm12 5h5l3 5v3h-8M18 9v5h4") + c(6, 19, 3) + c(18, 19, 3),
      "shipping delivery",
    ],
    [
      "box-open",
      p("m12 7 6-4 5 6-6 4-5-6-5 6-6-4 5-6ZM3 12v7l9 4 9-4v-7M12 14v9"),
      "unpack order",
    ],
    ["percent", p("M4 21 20 3") + c(6, 6, 3) + c(18, 18, 3), "discount rate"],
    [
      "coins",
      e(9, 5, 7, 3) +
        p("M2 5v6c0 3 8 4 12 2M2 10v6c0 3 5 4 9 3") +
        e(17, 15, 5, 2) +
        p("M12 15v5c0 3 10 3 10 0v-5"),
      "currency savings",
    ],
    [
      "bank",
      p("m2 8 10-6 10 6ZM3 22h18M5 10v9m5-9v9m4-9v9m5-9v9M3 19h18"),
      "institution finance",
    ],
    ["chart-line", p("M3 2v20h19M6 16l5-6 4 3 7-9"), "analytics growth"],
    [
      "chart-bars",
      p("M2 22h20M4 22V12h4v10m2 0V4h4v18m2 0V8h4v14"),
      "metrics statistics",
    ],
    [
      "chart-pie",
      p(
        "M10 2a10 10 0 0 0-8 10 10 10 0 0 0 10 10 10 10 0 0 0 10-8H10ZM14 2v8h8a10 10 0 0 0-8-8Z",
      ),
      "breakdown distribution",
    ],
    ["target", c(12, 12, 10) + c(12, 12, 6) + c(12, 12, 2), "goal objective"],
    [
      "briefcase",
      r(2, 7, 20, 15) + p("M8 7V2h8v5M2 13h20M10 11h4v5h-4Z"),
      "business work",
    ],
    [
      "building",
      r(5, 2, 14, 20, 0) +
        p("M9 6h.01m6 0h.01M9 10h.01m6 0h.01M9 14h.01m6 0h.01M9 22v-4h6v4"),
      "office company",
    ],
    [
      "scale-balance",
      p(
        "M12 2v20M3 7l18-3M6 6l-4 9h8Zm12-2-4 9h8ZM7 22h10M2 15q4 5 8 0m4-2q4 5 8 0",
      ),
      "fairness legal compare",
    ],
  ],
};
export const iconCatalog = Object.entries(groups).flatMap(
  ([category, entries]) =>
    entries.map(([id, body, keywords]) => ({
      id,
      title: id
        .split("-")
        .map((w) => w[0].toUpperCase() + w.slice(1))
        .join(" "),
      category,
      tags: keywords.split(" "),
      body,
    })),
);
