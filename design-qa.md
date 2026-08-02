# Avatar and identity-card visual QA

## Source visual truth

- `/var/folders/w2/qdlnjkx173ddwcb1bc34pd6w0000gn/T/codex-clipboard-311c3800-96d5-4cc6-b540-1b1a01faa039.png` — identity-card edit state, 700 x 500 px.
- `/var/folders/w2/qdlnjkx173ddwcb1bc34pd6w0000gn/T/codex-clipboard-bff26ea9-d7cb-42ad-bf08-ee469c0b11cf.png` — Chinese birth-date label wrapping reference, 700 x 500 px.
- `/var/folders/w2/qdlnjkx173ddwcb1bc34pd6w0000gn/T/codex-clipboard-5060bb78-f876-42dd-8675-e671e35db409.png` — management user card and fallback-avatar reference, 1960 x 1200 px.

## Implementation evidence

- `/private/tmp/elfie-qa-avatar-zGhkBE/account-menu-edit-zh.png` — `/manage` account-menu edit state, 1280 x 720 px.
- `/private/tmp/elfie-qa-avatar-zGhkBE/manage-users-avatar-1960.png` — `/manage?section=users`, 1960 x 1200 px.
- `/private/tmp/elfie-qa-avatar-zGhkBE/elfie-management-avatar.png` — `/manage?section=elfies`, 1280 x 720 px.
- `/private/tmp/elfie-qa-avatar-zGhkBE/chat-avatar.png` — `/chat?view=elfies`, 1280 x 720 px.

The browser-rendered screenshots were captured at CSS viewport sizes matching their pixel dimensions with device scale factor 1. The source screenshots were compared as focused component regions where the surrounding page viewport differed; no density conversion was required.

## States and interactions tested

- Identity card display state and edit state in Chinese and English.
- Edit-state name/account/gender/birth-date controls, including the read-only role field.
- Confirmed that the edit pencil is absent while editing and that `出生日期：` / `Birth date:` stay on one line.
- Management user card, Elfie management card, chat Elfie list, and shared account-menu avatars with no uploaded image.
- Focused tests exercised account-menu editing and the shared `Avatar` fallback; browser navigation exercised `/manage` and `/chat` routes.

## Comparison

### Full-view evidence

At 1960 x 1200, the management user card keeps the same desktop composition as the reference while the fallback initial is substantially larger and centered in the avatar frame. At 1280 x 720, the management Elfie card and chat Elfie list show the same centered, enlarged fallback treatment. The account menu preserves its existing warm-paper layout and hierarchy.

### Focused-region evidence

The edit-panel region was compared against the two 700 x 500 identity-card references. The right-side pencil disappears in edit state, the gender select remains in the top row, and the label column uses a content-sized, non-wrapping track. The Chinese and English birth-date labels remain single-line without disturbing the input column. Avatar-focused regions were compared against the 1960 x 1200 management reference and the corresponding Elfie/chat captures.

## Findings

- No actionable P0, P1, or P2 visual findings remain.
- [P3] At a narrower 1280-wide management viewport, long account values can still make the existing two-column user card feel dense; the target desktop reference is 1960-wide and the requested birth-date label remains stable. This is follow-up polish, not a regression from the avatar/edit-state change.

## Comparison history

- Initial edit-state review found the pencil still visible and the Chinese birth-date label wrapping. Fixed by conditionally hiding the edit button and giving the label column a content-sized, non-wrapping track. The revised evidence is `account-menu-edit-zh.png`.
- Initial avatar review found fallback initials too small in shared and custom avatar surfaces. Fixed the shared `Avatar` fallback and the manage/chat custom portrait tokens. Revised evidence is `manage-users-avatar-1960.png`, `elfie-management-avatar.png`, and `chat-avatar.png`.

## Implementation checklist

- [x] Hide the edit icon while identity-card editing is active.
- [x] Keep Chinese and English identity labels on one line with a stable label column.
- [x] Enlarge and center fallback initials across shared, management, Elfie, and chat avatar surfaces.
- [x] Add focused regression coverage for the edit state and shared avatar fallback.
- [x] Run TypeScript checks, Vite build, focused tests, and browser visual verification.

final result: passed
