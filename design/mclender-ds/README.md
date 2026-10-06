McLender is the loan management system built for Breez Lending, a small lender in Papua New Guinea: a staff app for loan officers, credit managers and accountants, and a mobile-first portal for borrowers. It sits on Apache Fineract. People use it to make decisions about other people's money, so it should read as calm, exact and plain.

## Content fundamentals

- **Write the way a good loan officer talks.** Short sentences, everyday words, sentence case. "Record repayment", not "Submit Transaction".
- **Use "you" for the borrower and plain role names for staff:** "Your next payment is due 14/10/2026", "Waiting for a credit manager".
- **Money is always written in kina with the currency first:** `K 1,318.74`. Use two decimals everywhere money appears, including in tables. Negative amounts take a minus sign, never brackets.
- **Dates are `dd/MM/yyyy`** (14/10/2026). Use relative dates only next to them ("in 3 days").
- **Say what happens and what to do next.** Errors name the field and the fix: "Monthly income is required to run the affordability check."
- **No emoji, no exclamation marks, no "Oops".** Avoid jargon in the borrower portal: say "amount you borrowed" instead of "principal", and "interest" stays "interest".
- **Loan states use the same words everywhere:** Draft, Pending approval, Approved, Rejected, Active, In arrears, Closed, Written off.

## Visual foundations

**Colour.** The UI is neutral first. `surface` is the page and `surface-raised` holds the content. `brand` (a deep sea teal) is the one brand colour: primary buttons, links, active navigation and the focus ring. Use at most one primary (`brand`) button per view. `kina-gold` marks money that needs attention now, like the amount due today or the borrower's next payment, and is never used for decoration.

**Status colours.** `success`, `warning`, `danger` and `info` mark loan and payment states. Each always comes with a word (a `StatusPill`, or a labelled value), so colour is never the only signal. Text in a status colour goes on its `-soft` ground or on a surface.

**Type.** Set body text, inputs and tables in `body` (IBM Plex Sans 15px). Use `label` for form labels and table headers, and `caption` (uppercase, tracked) only for short eyebrows such as "DUE TODAY". Use `display` (Fraunces) for one hero figure per screen, such as total portfolio or the borrower's balance, and `title` for screen titles. Write loan, client and receipt numbers in `reference` (Plex Mono). Give every column of money `font-variant-numeric: tabular-nums` and right-align it.

**Spacing and layout.** Space in 4px steps (`space-1` … `space-8`). Staff screens use a sidebar plus a content column with a maximum width of 1200px; cards are padded `space-6` on desktop and `space-4` on phones. The borrower portal is a single column 480px wide with a bottom tab bar.

**Shape.** Use `radius-md` for buttons and inputs, `radius-lg` for cards, and `radius-sm` for pills. Separate cards with a `line` hairline plus `shadow-raised`, nothing heavier. Inputs and controls use `line-strong` borders so they meet 3:1 contrast.

**States.** Hover darkens a fill slightly or adds a `surface-sunken` ground. Selected rows and the active nav item use `brand-soft`. Disabled controls show at 50% opacity and cannot be focused. Keyboard focus is a 2px `focus-ring` outline offset by 2px on every interactive element.

**Motion.** Keep it to 120–160ms ease-out for hovers and dialogs. There are no animations on figures; money never counts up.

**Low bandwidth.** The fonts come from Google Fonts with system fallbacks (`Segoe UI`, `Georgia`, `Consolas`), so the app still works if they fail to load. There are no background images or illustrations, and icons are inline SVG.

## Iconography

Use outline icons 20px on a 24px grid with a 1.75 stroke, drawn in `currentColor` (Lucide is the reference set in code). Icons sit beside a text label and never stand alone, except in the borrower tab bar, which also carries labels. There is no logo yet. Write the product name "McLender" in `title` weight in `brand-deep`; where the lender must be named (borrower portal, receipts, SMS), write "Breez Lending" in plain `body` text. McLender is the system; Breez Lending is the company borrowers deal with.

## Components

React 18 components are exposed as `window.McLender` (see `components/index.d.ts`): `Button`, `StatusPill`, `Money`, `StatTile`, `Field`, `DataTable`, `LoanStepper` and `AssessmentCard`. Class names use the `ml-` prefix and read only from these tokens.
