# HW3 AI Prompts

All prompts entered for homework 3. Labeled as Problem N, Prompt M for each problem.

## Problem 1, Prompt 1

Problem 1 - ok let's look at the hw3 folder. We are going to create a file called AI_prompts.md that we will update after every prompt with the label of "Problem N, Prompt M". This is Problem 1, Prompt 1

## Problem 1, Prompt 2

ok here is a test prompt to make sure it populates properly

## Problem 2, Prompt 1

Problem 2 - here is some context on what we are building. Campus Customs is a store that sells Yale merch. We are going to build an agent that helps us find out who in a photo is wearing a campus customs product and determine whether an ad video might be effective for a certain customer profile. Let's start by creating "build_catalogue.py" that turns every product photo in "data/products" into a structured catalogue entry. Save output in "output/catalogue.json" The catalogue entry type should be saved in "models.py" as a PydanticAI model. We have tons of images and want to parse them as effeciently as possible. I defer to you on best approach, but we likely need a library to vectorize them somehow. Save decisions made to do fast processing in "output.harness.md" with this decision. Also include the fields you pick for "models.py" and why. We will modify this file as we work the assignment

## Problem 3, Prompt 1

Problem 3. We now want to build our Campus Custom agent as four files.
- prompts/promt.md - system prompt to load to agent (we will add this later)
- agent.py - the PydanticAI agent entry point
- tools.py - all of the agents tools/helper files
- models.py - PydanticAI structured types (added to what we already built)

Let's start by adding the ability to take an image and decide if a Campus Customs product appears (and which one if we can tell). Implement this in tools.py, wired to agent.py.

Constraint: we want to do this without checking every catalogue image one at a time. We also never want to send more than 10 images at once to our AI.

Add the structured return type for this ability to models.py

The agent needs to be able to run with this command python agent.py --image "data/test_images/example.jpg"

Save structured output to output/identify_product.json, just populate with a test image for now. Update harness.md to describe how we do product identification and why it is efficient. Also describe what we added for our identify model in models.py

## Problem 4, Prompt 1

Problem 4. Run the agent against the four photos in "data/test_images" - the filename will tell us whether or not it is actual a campus customs product. Save output in "output/identify_product.json" - output for each review should match the identify pydantic model from "models.py." Also create an empty file called "output/agent_evaluation.md"

## Problem 4, Prompt 2

Something is definitely broken if it is taking this long - take a look at the code base and figure out what that might be, keeping in mind our requirements and constraints

## Problem 5, Prompt 1

Problem 5 - ok now we want to be able to take a video and a customer profile JSON file and judge how effective the video might be to get them to come shop at Campus Customs. New code for this should live in tools.py. Update prompts/prompt.md so our agent nows to use this new ability. Put thte structured result type in models.py as a new Pydantic AI model.

The code will be executed in a later problem with the command:
python agent.py --video "data/videos/ad_humble.mp4" --profile "profiles/profile_student.json"

Output from the agent video run should go into output/ad_effectiveness.json. Update output/harness.md to describe the tools the agent has for this job (one line for each tool is fine) and what tools are in ad-effectiveness and we why picked them

## Problem 6, Prompt 1

Problem 6 - Use your best judgment to create two models: profiles/profile_student.json and profiles/profile_parent.json. These should describe the typical Yale student (focus on undergrads at Yale College) and their parents. Include fields that might help us decide whether an ad resonates. Define the profile shape in models.py as a PydanticAI model, then save the profiles you generate. Explain your reasoning in output/harness.md

## Problem 7, Prompt 1

Problem 7 - run the agent on the Campus Customs ad video for both profiles using the following commands:
python agent.py --video "data/videos/ad_humble.mp4" --profile "profiles/profile_student.json"
python agent.py --video "data/videos/ad_humble.mp4" --profile "profiles/profile_parent.json"

Save structured results to output/ad_effectiveness.json

## Problem 7, Prompt 2

Add a few lines to "agent_evaluation.md" summarizing some of my thoughts here (Problem 7, under Problem 4). This output is actually pretty good. I think maybe for future iterations we might want to think about the effect the Kendrick song has on parents as this is definitely for a younger demographic. I like the quantatitive scoring though and it was obviously able to understand what was happening in the video

## Problem 8, Prompt 1

Problem 8 - use your best judgment to come up with safety rules for processing images (i.e. what the agent must do/not do with customer and influencer photos). Add to system prompt in "prompts/prompt.md" and make sure there is an explicit safety section the agent loads in. Create "output/audit_trail.json" and for each run append the following (time, thoughts, tool name + args + short result, stop reason). DO NOT wipe the file after each run. Put an audit-entry type in models.py as a pydanticAI model. In harness.md briefly explain your rationale for what fields you chose. Run against a test image to generate audit data

## Problem 8, Prompt 2

I noticed we have a "prompt.md" and a "promt.md" - audit both and merge into one "prompt.md"

## Problem 9, Prompt 1

Problem 9 - now let's refactor output/harness.md so it reads in plain English for a manager. Include:
- All tools the agent uses
- What they can and can't do 
- The Pydantic/Pydantic AI models in models.py - what each model is for, why fields were chosen
- Safety rules
- Any other specs - max loops sizes, sampled frames from videos, any other limits that matter for cost or quality

Include earlier harness sections as well (catalogue speedup, field choices, identify efficiency, profile videos, video tools)

## Problem 10, Prompt 1

Problem 10. Great now let's bundle this up. Let's make sure the repo is structured to match this example. Only test if there is a dramatic change. Please include the PORTKEY_API_KEY in .env.example only as a placeholder, not the real key. Zip this as hw3.zip, and do not include the data/ directory in the zipped submission
