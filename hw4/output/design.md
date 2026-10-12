# Design update: reskin

A visual-only pass. Routes, pages, nav items, copy, chat behavior, filters, the data flow, and the Yale navy (`#00356b`) brand are unchanged.

References: yalebulldogblue.com (photography, navy and white), Lululemon, Alo, and Vuori (full-bleed lifestyle heroes, uppercase micro-labels, flat photo tiles, lots of whitespace).

## What changed and why

- **Palette.** The page background moved from cool gray to warm off-white (`#f7f6f2`), with near-black ink (`#0e1726`) and a light-gold accent. The navy stays the brand color. Warm neutrals make the navy garments stand out, the way Vuori and Alo backgrounds do.
- **Type.** Still Inter. Headlines are heavier (800) and tighter. Nav, buttons, chips, and labels use small uppercase text with wide letter spacing. That gives the premium-athleisure feel without adding a font.
- **Announcement strip.** A thin navy bar above the nav reads "Official Yale gear · 57 Broadway since 1975." All three reference sites use this pattern, and it carries the store's main trust signal.
- **Nav.** The real Yale Bulldog Blue wordmark (the logo on yalebulldogblue.com) replaces the "CC" circle. It sits on the left with all links on the right, the same layout as before. Translucent off-white with a blur. The active link is underlined and the call to action is a solid dark pill.
- **Footer logo.** The Campus Customs mark (with the "webstore powered by" label cropped off and recolored white) sits above the address in the navy footer.
- **Home hero.** A full-bleed Campus Customs lifestyle photo with a navy gradient behind the existing headline, copy, and Browse button. The featured-product link is still there, now as a floating card with photo, name, and price.
- **Highlights.** The same three blocks (College crests, Sport marks, Family pieces) are now photo tiles with the text over a navy fade, so the home page is image-led rather than text boxes.
- **Product cards.** Borderless square photo tiles, since 94 of the 102 catalogue photos are square. The image zooms slightly on hover and a "View" pill appears. The text below is smaller and quieter, and the price is in navy. The card still opens the same product page.
- **Product page.** Same two-column layout with a larger square photo. On desktop the detail column stays in view while you scroll. Sizes sit in a two-column grid, and out-of-stock sizes are struck through and muted, so they read at a glance.
- **Filters.** Chips are uppercase. The active chip is solid dark, with clearer focus rings and a divider below the filter row.
- **About page.** Opens with the real Broadway storefront photo from the Campus Customs site.
- **Log in and Create account.** Split layout with a lifestyle photo beside the unchanged form, which stacks on mobile. Inputs are larger, and the submit button is full width.
- **Chat.** Same widget and behavior. The header is now navy, bubbles have rounder "tail" corners, chat cards get a navy hover border, and the launcher is a pill with an uppercase label and a navy shadow.
- **Footer.** A navy band in place of gray text, so each page has a clear end.
- **Motion.** Short eased transitions on hover and focus. All of them are turned off under `prefers-reduced-motion`.
- **Mobile.** The product grid shows two columns on phones instead of one, the usual density on fashion sites. Hero, highlights, product detail, and account pages stack. There is no horizontal overflow at 390 px.

## Copy

All the copy we wrote was rewritten in a shop voice: short sentences, contractions, and concrete Yale details (colleges, sports, "Yale Dad"). Text that explained how the system works ("the password is stored as a hash," "I'll only name pieces in the catalogue") is gone. Error messages now say what happened in plain words. The chat is labeled "Ask the shop," and stock rows read "8 left" or "Sold out." "Since 1975" and "oldest official Yale shop in New Haven" come from Campus Customs' own storefront sign. Product names and descriptions come from the database and were not touched.

## Images

All five are from yalebulldogblue.com, saved locally as compressed JPEGs in `frontend/public/lifestyle/` rather than hotlinked:

- `campus-walk.jpg`: home hero
- `campus-steps.jpg`: College crests tile and Log in
- `navy-zip.jpg`: Sport marks tile and Create account
- `friends.jpg`: Family pieces tile (cropped from the site banner, with the baked-in logo removed)
- `broadway-storefront.jpg`: About page

Logos, also from yalebulldogblue.com, are in `frontend/public/brand/`: `yale-bulldog-blue.png` (nav) and `campus-customs-white.png` (footer).

Product photos are unchanged and still come from `data/products/`.

## Files touched

`frontend/src/index.css` (rewritten; every existing class name kept), `HomePage.tsx`, `AboutPage.tsx`, `LoginPage.tsx`, `CreateAccountPage.tsx`, `Layout.tsx` (announcement strip), and `frontend/public/lifestyle/`.
