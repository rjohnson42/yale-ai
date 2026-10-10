# Campus Customs agent

This document describes what the agent does, which tools it may use, what those tools are allowed to do, how results are stored, and the limits that control cost and quality.

Campus Customs sells Yale merchandise. The agent does two jobs:

1. Look at a customer or influencer photo and decide whether someone is wearing a Campus Customs product, and which product if we can tell.
2. Look at one of our ad videos together with a customer profile and judge whether that ad would bring that customer into the store.

Both jobs depend on a catalogue of 102 studio product photos. The catalogue is built once, locally, and then reused. The paid model is GPT-5.6 Luna, called through Portkey. The model name can be overridden with the `LLM_MODEL` setting. The API key stays in `hw3/.env` and is never written into a result file.

A "Pydantic model" here is a form with required fields. PydanticAI is the library that runs the agent and checks those forms. If a result does not match the form, it is not saved as a finished answer.

The system prompt is `prompts/prompt.md`. The agent will not start if that file is missing its Safety section.

## What the agent is allowed to call

The language model itself may call two tools, and only one tool per run. It cannot pick a different photo, video, or profile than the one on the command line. It cannot browse the catalogue, send email, or ask for more images.

**Identify a product** (`identify_campus_product`)

- Can decide whether the clothing in the given photo is a specific Campus Customs item.
- Can return "not one of ours" when the wording and the visual search do not support a match.
- Cannot open catalogue photos one at a time, and cannot send more than 10 images in any single model request.
- Cannot name the person in the photo or describe their face. The tool reads the garment.

**Judge an ad** (`judge_ad_effectiveness`)

- Can score one ad video against one customer profile: would this person come shop.
- Can name what in the sampled frames fits that profile and what misses.
- Cannot upload the whole video, and cannot call the model once per frame.
- Cannot invent a customer. The profile file has to match the customer form, or the run stops.

A photo run and an ad run are separate commands. One command does not do both.

The two tools above are the only ones the model can choose. Each of them runs a few fixed steps in code. Those steps are not extra choices for the model. They exist so the expensive model sees a small, already-filtered packet of evidence.

## Catalogue, and why it is fast

We do not send each product photo to the paid vision model.

There are 102 studio shots. A vision call per shirt would be slow and billed, and we would still need a way to compare a person in a snapshot with the catalogue. The filenames already say the cut, the school, the sport, the family role, or the licensed brand. Reading those strings is instant and does not invent a caption.

What a filename cannot do is match a shirt on a person. For that, every studio photo is turned into a list of 512 numbers by a local picture model called CLIP (`clip-ViT-B-32`), through the `sentence-transformers` library. CLIP runs on this machine. It does not use Portkey and does not use the API key.

- The picture model loads once.
- Photos are encoded in batches of 32.
- Each list of numbers is scaled to length 1, so a later comparison is one multiplication, not another model call.
- The model name is printed when the catalogue is built and stored on every product, so a rebuild can be repeated.
- The build uses the Apple GPU when it is available, otherwise a NVIDIA GPU, otherwise the CPU.

Color is a separate cheap pass. Each photo is shrunk to 72 by 72 pixels, the near-white and near-black studio backdrop is ignored, and the middle color of the largest remaining cluster is named. Near-gray pixels stay gray, ivory, or black. Pixels with a real hue snap to a small palette such as navy or pink. That name is a filter, not a precise dye name.

The dataset arrived as flat files whose names still contained Windows backslashes (`data\products\yale-mom-hoodie.jpg`). The catalogue builder moves those into real `data/products/`, `data/test_images/`, and `data/videos/` folders before it reads anything. A folder that is already unpacked is left alone.

The only filename that does not name a garment is `squash-left-chest-tennis`. The photo is a crewneck that says Yale Squash, so that one cut is set to crewneck, and the sport is Squash.

## How a photo is identified

Command: `python agent.py --image "data/test_images/example.jpg"`

A customer photo is a person in a room, not a shirt on a white background. Comparing that whole frame with all 102 studio shots, one image at a time, would miss the shirt (the background dominates the comparison) and would send far too many images to the paid model.

The identify tool does this instead:

1. **Local crops, one batch.** The photo is split into the full frame plus overlapping windows at about 45% and 70% of the frame. Those windows are embedded together with the same local CLIP model as the catalogue. This step is not an API call.
2. **One comparison against the whole catalogue.** The stored product vectors score all 102 products at once. We keep the top 9. We do not open catalogue files in a loop, and we do not ask the paid model to look at each one.
3. **One look at the customer photo.** A single vision call, with that one image, reads text on the clothing and the cut. A Yale building in the background does not count. Words such as "Dad" or "Bulldogs" are matched against the catalogue theme and garment type in plain text.
4. **Agree, or show a handful of photos.** If that wording points at exactly one product, and CLIP already ranks it in the top 3 with a similarity of at least 0.70, we stop. No catalogue photo is sent. If the wording is ambiguous, or CLIP does not agree, one more vision call receives the customer photo plus at most 9 catalogue shots. That is 10 images. The code refuses to build a request with more.

`images_sent` on the saved result is the number of images in the largest of those calls. The outer agent is given only the file path, so it cannot attach the catalogue on its own.

GPT-5.6 Luna reasons at a medium setting unless we say otherwise. Reading a garment is a small structured question, so every model call in this step turns reasoning off. Leaving the default on made each photo take minutes, and a second confirm call doubled that. The 10-image cap is unchanged. The local CLIP ranking is still the step that covers the whole catalogue.

## How an ad video is judged

Command: `python agent.py --video "data/videos/ad_humble.mp4" --profile "profiles/profile_student.json"`

The saved result is `output/ad_effectiveness.json`, a list with one row per profile. Running the command again for the same profile replaces that row and leaves the other.

The agent calls the ad tool once. That tool uses three helpers. None of them walks the catalogue image by image. The only paid request in this job sends 8 frames. The hard cap is still 10. Reasoning stays off.

**Load the customer profile** (`load_customer_profile`)

- Can read the profile JSON on this machine and check it against the customer form, so the score is about this person.
- Can pass a short text copy of that profile into the one judgment call. Longer than 6,000 characters, the text is cut.
- Cannot invent missing fields. A file that does not match the form stops the run.
- Cannot treat the profile as a named individual. The two profiles we ship are typical people.

**Sample the ad** (`sample_ad_frames`)

- Can pull 8 frames, evenly spaced from the start of the video to just before the end, and shrink each so the long side is at most 640 pixels.
- Cannot upload the video file. Frame grabbing happens locally.
- Cannot call the paid model once per frame.

**Match frames to the catalogue** (`match_ad_to_catalogue`)

- Can embed those 8 frames in one local CLIP batch and score all 102 products with one multiplication.
- Can keep up to 5 neighbors, and only neighbors whose similarity is at least 0.22.
- Cannot open each studio photo for the model. The judgment sees a short text list of neighbors, not the studio shots.

**Judge the ad** (`judge_ad_effectiveness`)

- Can make one vision call with those frames, the profile text, and the neighbor list, and return whether this customer would come shop.
- Cannot watch the video itself, and cannot request extra images.

We picked these steps because the profile is text, the catalogue is already turned into numbers, and the ad only needs a handful of frames to judge tone and merchandise. A second pass over every product photo, or a paid call per frame, would repeat the cost problem we already hit on photos.

## Customer profiles

The customer form is `CustomerProfile`. The two files are `profiles/profile_student.json` and `profiles/profile_parent.json`. They describe typical people, not named individuals.

The catalogue is already split into college, campus, sport, family, and brand. An ad fits when its merchandise and mood land in the collections this person wants, and misses when it lands in the themes they avoid. Price and tone are separate from the shirt graphic: a student can like a Yale versus Harvard tee and still bounce off a luxury pitch, and a parent can like a Yale Dad hoodie and bounce off a college in-joke.

**Student.** A Yale College undergrad lives in a residential college and wears gear as clothes. College marks, campus marks (Boola Boola, big Yale, The Game), and their sport fit. The family line (Mom, Dad, Grandma) and professional-school crests are for someone else. Budget is tight, so price sensitivity is high. The tone should feel like campus. The profile does not name one college, because a typical student is in some college, not a particular one.

**Parent.** They buy for themselves and for their student, mostly around visits, holidays, and graduation. The family collection is the obvious fit, plus a plain Yale mark they can wear in public and a slightly nicer gift. Another college's crest, or an ad that only makes sense if you live in the entryway, does not fit. They will spend more than a student, so sensitivity is medium. The tone should be warm and proud. A party ad or a student-only joke leaves them out.

## Forms in models.py, and why the fields are there

Every saved file is checked against one of these forms before it is written.

### CatalogueEntry and Catalogue

`CatalogueEntry` is one product. `Catalogue` is the file wrapper written to `output/catalogue.json`.

| Field | Why it is here |
| --- | --- |
| product id | Stable id from the filename, so a later match can point at one product. |
| name | A readable label for a person reviewing a match. |
| image path | Where to reload the studio photo without scanning the folder again. |
| garment type | Lets us tell a hoodie from a t-shirt before comparing pictures. |
| collection | College, school, sport, family, brand, or campus. This is the bridge to a customer profile. |
| theme | The specific subject inside that collection, such as Mom, Morse College, or Hockey. |
| brand | The licensed name when the filename has one (Champion, District, Brooks Brothers, Hype and Vice, Under Armour). House goods are blank, because the filename never claims a brand. |
| primary color | A coarse color so an obvious mismatch can be dropped before picture search. |
| description | One sentence assembled only from the fields above. Nothing in it was guessed by a model. |
| embedding | The CLIP numbers. This is what answers whether a person looks like they are wearing this product. |
| embedding model | Which model built those numbers, stored on each product so a mixed catalogue is obvious. |
| embedding dimension | Length of that list. For this model it is 512. |

`Catalogue` also stores the embedding model, the dimension, whether every vector has length 1 (it does), and the product count (102). The script checks the whole object before it writes the file.

### RankedProduct

One neighbor from the local picture search. Used inside a photo result and inside an ad result. The embedding itself is left in the catalogue, so these result files stay small.

| Field | Why it is here |
| --- | --- |
| product id, name, garment type, theme, primary color | Enough to review the neighbor without opening the catalogue. |
| similarity | How close this product was to the best local crop of the photo, or to the best sampled ad frame. |

### ProductIdentification

The saved photo decision, in `output/identify_product.json`. One photo is one object. Several photos are a list. A rerun replaces the row for that same photo and leaves the others.

| Field | Why it is here |
| --- | --- |
| query image | Which photo was judged. |
| product found | Whether we are willing to name a specific catalogue item. |
| product id, product name | The item, when we can tell. Blank when the clothing is not ours or the shortlist does not match. |
| garment type, theme, primary color | Copied from the catalogue row so a reviewer does not have to open the catalogue. |
| confidence | 0 to 1. From CLIP when wording and pictures agree, otherwise from the confirmation call. |
| clip similarity | How close the chosen product was, or the nearest neighbor when nothing is chosen. |
| matched by | `text` when wording picked the row, `clip` when we had to show shortlist photos, `none` when we decline. |
| readable text | What the vision model actually read on the garment. This keeps the decision auditable. |
| reason | A short explanation of why this id, or why none. |
| images sent | The largest single request. This is the check that we stayed at or under 10. |
| vision model | Which Portkey model made the vision calls. CLIP's name stays on the catalogue. |
| shortlist | The top visual neighbors. The model is not shown the rest of the catalogue. |

Two smaller forms live in `tools.py`, not in `models.py`: one for the garment read, and one for the confirmation pick. They shape the vision calls. They are not the saved result.

### CustomerProfile

Who an ad is for. Fields line up with the catalogue so a video can be scored against them.

| Field | Why it is here |
| --- | --- |
| name | A short label, used as the customer summary. |
| segment | `student` or `parent`. Keeps the two audiences distinct. |
| summary | A few sentences on this typical person. |
| relationship to Yale | How they are tied to Yale, not a specific biography. |
| who they buy for | Self, their student, gifts, and so on. |
| occasions | Moments when they actually shop for Yale gear. |
| preferred collections | Which catalogue lines should resonate: college, school, sport, family, brand, campus. |
| preferred themes | Subjects inside those lines that should land. |
| avoid themes | Subjects that would make the ad feel aimed at someone else. |
| preferred garments | Cuts they would actually wear or give. |
| price sensitivity | High means a tight budget. Low means price is not the main objection. |
| tone that resonates, tone that misses | The mood the ad should have, and the mood that would push them away. Separate from the shirt graphic. |

### AdEffectiveness

How well one ad would move one customer to shop. Stored in `output/ad_effectiveness.json`.

| Field | Why it is here |
| --- | --- |
| video path, profile path | Which ad and which customer file were judged. |
| customer summary | The short label from the profile, so a reader can see the audience without opening the profile. |
| effective | Whether the ad is a good reason for this customer to visit. |
| score | 0 to 1. Higher means more likely to bring this customer in. This is the number a manager can compare across profiles. |
| would visit | Whether we would expect this person to come shop after seeing the ad. |
| reason | The explanation, tied to what is visible. |
| strengths, mismatches | What in the ad fits this customer, and what misses. |
| catalogue matches | The closest catalogue items across the sampled frames. This is a neighbor list, not a frame-by-frame scan. |
| frame timestamps | Where the sampled frames sit in the video, so the judgment can be checked. |
| frames sent | How many frames were in the single judgment request. Never above 10. On the current setting it is 8. |
| vision model | Which Portkey model made the call. |

The vision call itself returns a smaller form (`AdJudgment` in `tools.py`) with the score, the visit decision, the reason, and the strengths and mismatches. The saved form adds the paths, the frame times, the neighbor list, and the model name.

### AuditEntry and AuditedToolCall

`AuditEntry` is one row of `output/audit_trail.json`. `AuditedToolCall` is the tool record inside that row. Each run appends a row. The writer reads the existing list, checks it, and writes the old rows plus the new one. It does not clear the file first. If the file is not valid JSON, the run stops instead of replacing it.

| Field | Why it is here |
| --- | --- |
| time | When the run was recorded, so later runs stay in order. |
| thoughts | What the model said it was doing before the tool, which is where it has to name the photo rule it is following. Reasoning stays off, so this is not a hidden chain of thought. If the model returns none, the row says so. |
| tool calls | For each call: the tool name, the file paths it actually used, and a short result (product found and id, or effective and score). Arguments stay paths. The short result is a few fields, not the full JSON and not the image. |
| stop reason | Why the run ended: the model's finish reason, or the error if a limit or failure stopped it. |

## Safety rules

These rules cover every customer photo, every influencer photo, and every frame taken from an ad. A person in the frame is not a catalogue item. The rules live in `prompts/prompt.md` under Safety. The agent refuses to start if that section is missing. The vision calls that actually see pixels load the same section. The outer agent only receives a file path.

The agent must:

- Use the photo only for the job that was asked: decide whether a Campus Customs product is being worn, or judge an ad the store already has.
- Talk about the garment, the words printed on it, and the catalogue match. That is the whole output.
- Keep the photo on this machine. The only copy that leaves is the one vision request for that job, and that request stays at or under 10 images.
- Say it cannot tell when the product is unclear.

The agent must not:

- Name the person, guess who they are, or try to find them in other photos or online.
- Estimate age, gender, race, body, health, religion, or anything else about the person. It must not describe a face. If someone appears to be a child, it must not describe them at all. Only the garment question is in scope.
- Treat a face as an identifier. It must not store a face crop, a face embedding, or the image bytes in the audit trail or any output file.
- Build a customer or influencer profile from a photo. It must not score how marketable a person is, and it must not recommend paying, posting, or contacting them.
- Email, post, or otherwise share the photo. It must not add the photo to the catalogue or use it as training data.
- Run a photo the user did not pass in on this command.
- Continue if the request is to identify, track, or contact someone. It stops and says that is out of scope.

An influencer photo answers which of our products is shown. A customer photo answers the same question. It does not answer who the person is.

## Limits that affect cost and quality

These are the caps in the code. They are there so a run stays short, cheap, and checkable.

| Limit | Value | Why it matters |
| --- | --- | --- |
| Tool calls per run | 1 | The model calls one tool and stops. It cannot loop through the catalogue or retry the tool on its own. |
| Model round trips per run | 4 | A ceiling on the outer conversation, including the tool call and the final answer. |
| Retries | 1 | If a structured answer fails validation, the agent may try once more. It does not keep looping. |
| Images in one paid request | 10 | Hard stop. A photo confirm sends the customer photo plus at most 9 catalogue shots. |
| Catalogue neighbors kept for a photo | 9 | The rest of the 102 products stay local. |
| Text and CLIP must agree | Top 3, similarity at least 0.70 | When both agree on one product, we skip sending catalogue photos. That is the cheap path. |
| Ad frames sampled | 8, evenly spaced | Enough to see the spot. The whole video is never uploaded. The long side of each frame is at most 640 pixels. |
| Ad catalogue neighbors | Up to 5, similarity at least 0.22 | A short list for the judgment, not a second pass over every shirt. |
| Profile text in the judgment | 6,000 characters | A runaway profile cannot inflate the paid call. |
| Reasoning | Off | Medium reasoning made each photo take minutes. Garment reads and ad scores do not need it. |
| Paid-call timeout | 90 seconds | A stuck call fails instead of billing for many minutes. |
| Catalogue build | Local only, batches of 32 | Building or rebuilding the 102-product catalogue does not call Portkey. |

A straightforward photo is one paid vision call (the customer image only), plus the outer agent call that invokes the tool. A photo that needs confirmation is a second vision call, still capped at 10 images. An ad is one paid vision call with 8 frames. Local CLIP work is free of API charges.

## What this agent does not do

- It does not email, post, or contact anyone.
- It does not store image bytes, face crops, or face templates in any output file.
- Keys stay in `hw3/.env` and are not written into the JSON.
