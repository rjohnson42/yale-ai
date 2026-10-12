# Campus Customs usability

Four quality-of-life changes. Two are on the shop site. Two are in the agent. Graders can see the site changes by using the Products page and the chat panel. The agent changes show up in replies and in the benchmark below.

## 1. Catalogue filters on the Products page

The catalogue has 102 pieces. The Products page used to be one long grid, so finding "Pierson" or "hoodies" meant scrolling.

The page now has a search box and five garment chips: Hoodies, Crewnecks, T-shirts, Quarter-zips, and Jackets, plus All. The count next to the title updates as the shopper filters. Search matches the name, garment, description, colors, and tags. A chip with no matches says so and offers Clear filters. Each card still opens the same product page as before.

The chips group the catalogue's uneven labels. "Pullover hoodie" and "hooded sweatshirt" both sit under Hoodies. Quarter-zips are separated from crewnecks even when a name says "crewneck." The chip counts from the current catalogue are Hoodies 27, Crewnecks 28, T-shirts 25, Quarter-zips 11, and Jackets 8. Three performance shirts and a mockneck stay under All only, because they are not one of those five families.

This helps a shopper browse without opening the chat, and it helps the shop because people can reach a garment family in one click.

## 2. Chat panel stays out of the nav, and replies read as sentences

The chat panel was tall enough to cover the top navigation, so Log out and the page links sat under the panel and could not be clicked. The panel is now shorter (`100vh - 168px`, capped at 520px), and the navigation sits above it, so the header stays usable while the chat is open.

Older assistant replies were stored with markdown such as `**$68**` and lines that start with a dash. The panel now shows those as plain sentences. Asterisks and bullet markers are removed when the bubble is drawn. New replies are cleaned the same way on the server before they are saved, so the next visit is plain text too.

This helps a shopper read a price or a list without markup, and it keeps the account links reachable while they chat.

## 3. Shorter chat history sent to the model

A signed-in shopper's thread is still stored in full in `chat_messages`, and the panel still reloads the full thread. What changed is the copy sent back to the model on the next question. Previously that copy was the last 12 turns, uncut. It is now the last 8 turns, and each turn is cut at 320 characters after markdown is removed.

That matters because a long answer about many products was being paid for again on every later question. The shopper still sees the original message in the panel.

Benchmark on the Test User thread in `chat_messages` (18 stored turns), measured by counting characters that would be placed in the model history:

| | Turns sent | Characters |
| --- | --- | --- |
| Before | last 12, full text | 1,323 |
| After | last 8, each cut at 320 characters | 907 |

That is 416 fewer characters, about 31 percent less history on this thread. The longest stored reply is 443 characters and is sent as 320. The current question is never cut. As threads get longer, the cap holds the history at 8 turns instead of growing with every visit.

## 4. The open product is answered from the database, and replies are checked

When a shopper is on a product page, the turn now includes that item's price, colors, size quantities, and description, read from `campus_customs.db` for that request. "This" and "it" mean those fields. The agent is told not to call a tool again for that same product, so a color or stock question does not need a second model request. Questions about a different item or a type of item still use the catalogue tools.

The standing instructions no longer include the shopper's email on every turn. The first name is enough for a greeting. Email is returned only if the agent calls `shopper_context`, which is for when they ask. Another person's email address is removed from a reply. A reply that contains a password hash is replaced with a short refusal.

If the turn is about one product and the reply names a dollar amount that was not in the database block or a price tool, that amount is replaced with the catalogue price. A price the shopper typed themselves, such as "under $40", is left alone. Type searches are not rewritten, because those cards carry the prices.

Benchmark for "Do you have this in pink?" on the Pierson College Crewneck page:

| | Model requests | Tools | Wall clock | Reply |
| --- | --- | --- | --- | --- |
| Before | 2 (description tool, then the answer) | `get_product_description`, `final_result` | 4.8 seconds | Named Pierson and said pink is not offered. Colors were navy, black, and yellow. |
| After | 1 (the answer only) | `final_result` | 4.5 seconds | Same facts, taken from the database block on the turn. No catalogue tool call. |

The wall clock is only a little lower, because one model call is most of the wait. The cost change is the dropped tool request: this kind of question is one model call instead of two, and the colors and price it uses were loaded from the catalogue rather than recalled.
