# HW4 AI Prompts

All prompts entered for homework 4. Labeled as Problem N, Prompt M for each problem.

## Problem 1, Prompt 1

Problem 1 - let's work in the hw4 folder. We are building a website for Campus Customs (current website at yalebulldogblue.com). We are going to build a React + Vite + Typescript front end and a Python FastAPI backend hooked up to a PydanticAI agent. We want shoppers to be able to browse products, create an account, chat about merch, see matching items, and get honest answers from a local database. In the data folder you will find campus_customs.db, with tables for the product catalogue, inventory, and users (with hashed passwords). Let's start by creating an AI_prompts.md file in the hw4 repo. This will work like other assignments. Log each prompt after I type it. This is for example Problem 1, Prompt 1

## Problem 1, Prompt 2

Test prompt to make sure we are writing to the file OK

## Problem 2, Prompt 1

Problem 2 - Look at data/campus_customs.db and understand fields. We really need you to get a good read on what is in "catalogue" "inventory" and "users". Create a file called "output/harness.md" Write down each table and its field and tell us why each matters either for the store or the chatbot we will build

## Problem 3, Prompt 1

Problem 3 - let's scaffold a React/Vite/Typescript front end for Campus Customs. There should be a nav up top with links to the following pages:
- Home
- Products
- About Us
- Log in 
- Create account 

For Home and About Us, reference yalebulldogblue.com, but do not copy what is on the site word for word. 

On the Products page, show product images from the catalogue (use the image paths in the database) with basic product info (name, price, short description). Make each product open a single-item page (large image on one side, full product text on the other, inclusive of description, price, sizes/stock when you have them). Clicking a product card on Products should take a user there. Add a chat interface to the bottom right of the site (floating is fine) - just stub this out for the moment.

Also stub out "backend/main.py" which is our FastAPI backend. We will build this out in a later problem

## Problem 4, Prompt 1

Problem 4 -  Now let's build a normal create-account/ log in flow:
Create account: first name, last name, email, password, confirm password
Log-in: email and password

All new accounts should be in the 'users' table. The seed database has a test user to use as an example that hashes passwords with PBKDF2-HMAC-SHA256, 120k iterations. 

How I want you to check passwords:
- Never un-hash the stored value. Instead re-hash what user typed and compare. 
- Read the salt out of the stored strong, do not make a new one
- Hash the typed password with the same salt and compare to the stored hash with constant-type compare
- Signup and login must use the same hash settings. 

To test - log-in as the seeded user and a test user you create. 

Update "output/harness.md" with info on how auth flow works and what protections are in place

## Problem 5, Prompt 1

Problem 5 - Now let's build the chat feature as a Pydantic AI agent behind FastAPI. Put the API app in "backend/main.py" which we will run with Uvicorn. "backend" should also contain the following files:
- prompts/prompt.md - system promp (we will expand this later) 
- agent.py - agent entry/writing 
- tools.py - the tools the agent canc all 
- models.py - Pydantic/PydanticAI structured types. 

In main.py explose a chat route so a message from the website returns a reply from the agent (in addition to whatever else we need for product info and auth). Use the same portkey API key we have used for other projects. 

Put Campus Customs voice and safety basics into 'prompts/prompt.md'. Start or update types in 'models.py' for chat replies/product cards as needed. 

In 'output/harness.md' note how the front end talks to FastAPI and how the agent is loaded (prompt file + model)

Backend needs to run from the command:
uvicorn main:app --reload --port 8000\

## Problem 6, Prompt 1

Problem 6 - Now let's give the agent tools to look up real information from "campus_customs.db" It looks like you already did some of this, but here is what we need to be able to report: 
- Product Description
- Price 
- How many are in stock (by size when customer asks. If a size is out of stock say so clearly) 
Make sure the agent only references our database. Do not invent information. 

Expand 'prompts/prompt.md' so the agent knows to call these tools for price and stock questions. Add or update return types in 'models.py' In 'output/harness.md' please list each tool and explain which model fields you chose for lookup results and why

## Problem 7, Prompt 1

Problem 7 - Now for an interesting feature. When a customer asks about a type of item - for example "what hoodies do you have?" - the agent should search the catalogue and the website should dynamically show those matching items as product cards. It looks like you already built this, but let's make sure the single-item page behavior we already built previosuly still works. The returned cards should open the detailed view when clicked. Updated 'prompts/prompt.md' and 'output.harness.md' so it is clear hwo search results reach the page

## Problem 8, Prompt 1

Problem 8 - we also have a version of this, but let's make sure its good to go. When a shopper is logged in, save their chat history in the database in an appropriate table and reload it when they return. The agent should know who is chatting (name, email) - put that in agent deps (or an equivilant pattern) and/or tools the agent can call. Also make sure the agent has enough current page context that if someone is on a page and asks "do you have this in pink?" the agent knows what item they mean (perhaps by passing code from page into agent context). Guests should still be able to chat, but history only needs to be persisted for logged-in users. Document this in 'output/harness.md" - how user chat history is stored, what customer agent fields the agent sees, and how page context is passed

## Problem 9, Prompt 1

Problem 9 - OK now let's come up with some quality of life/usability improvements. Use your best judgement and come up with:
- 2 front-end usability improvements ... i.e. things that make the site look better and easier to use 
- 2 agent/backend usability improvements ... i.e. things that make the agent output better, more accurate, or sager. These can also be optimizations to make the agent cheaper or faster 

As you build - create and update "output/usability.md" with each improvement, describing what you added and why it helps a Campus Customs shopper or business. 

Graders will read this file and look for features. If this was a non-technical update (say better performance) include a before and after performance benchmark for the grader

## Problem 10, Prompt 1

Problem 10 - now we really want to re-style this website to pop. Look at other trendy fashion sites - the original Campus Customs site, Lululemon, Alo, Vuori, and redesign what we built. Feel free to grab stock images from Campus Customs. DO NOT change any design decisions we made, this is just a reskin. Write a terse update to "output/design.md" on what you changed and why 

## Problem 10, Prompt 2

This is great. Now review all copy on the site that we wrote (not copy from our database) and make sure it is punchy. We do not want it to sound AI written 

## Problem 10, Prompt 3

Remove this "The store also stocks hats, mugs, and souvenirs. Online, we stick to apparel." Also can we make this nav more elegant - maybe get their real logo? 

## Problem 10, Prompt 4

Ok last edit - love the logos you brought in, please move the logo back to the left as we had it. On the "Products page" change "The Full Rack" to "Product Catalogue" change  "Pieces" to "Items" and then change the search prefill to something better

## Problem 11, Prompt 1

Problem 11 - now test the live site and document it in "output/app_check.html" which should be a page we can open. Include clear screenshots and captions for: 
1. Chat checking the inventory level of an item (honest stock/price from the DB)
2. The dynamic search-result cards appearing after a category question (e.g. hoodies) 
3. One of the usability features we added in Problem 9 

Make the HTML easy to grade: heading for each check, screenshot, one or two sentences on what the screenshot proves. 

Put the screenshots in "output/app_check_images/" and link them from "app_check.html" with relative paths (for example "app_check_images/inventory.png")

## Problem 12, Prompt 1

Problem 12 - Now develop an append-only "output/audit_trail.json" file of agent-loop activity (time, tool name, short args/results, stop reason). Do not wipe it between runs. Also - think of safety rules to give to the agent and add them to "prompts/prompt.md". Run the agent a few times to populate the audit_trail. 

Fnally, finish output/harness.md so it is clear how the system works. This is inclusive of: 
- Model fields in models.py and why you chose them. 
- Tools and abilites 
- Safety rules
- Specs (loop limits, result caps, models, how to run front/back) 

## Problem 13, Prompt 1

Problem 13 - please make sure our repo is published like this. If you have to move anything around, re-test the app please

## Problem 13, Prompt 2

gitignore should include the whole data folder

## Problem 13, Prompt 3

do we need to update the README to instruct the grader how to connect the data folder when they pull this down?
