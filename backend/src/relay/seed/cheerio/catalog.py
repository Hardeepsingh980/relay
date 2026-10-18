"""Text banks for Cheerio's (fictional) customer portfolio.

The product areas are Cheerio's real modules; the customers, contacts, tickets
and conversations are invented. Customer phrasing is modelled on the kinds of
issues a WhatsApp marketing platform sees ("messages stopped going", "same
number showing twice"), never copied from real tickets.
"""

from __future__ import annotations

# (id, name, owning engineer, systems that serve it, weekly events per active user)
FEATURES = [
    ("F-CAMPAIGNS", "Broadcast campaigns", "p-neha", ["messaging-api", "send-guard"], 6.0),
    ("F-TEMPLATES", "Templates", "p-kavya", ["messaging-api"], 3.2),
    ("F-INBOX", "Shared inbox", "p-gautam", [], 14.0),
    ("F-WORKFLOWS", "Workflows & chatbots", "p-nikhil", ["workflow-engine"], 5.5),
    ("F-SHOPIFY", "Shopify automations", "p-zoya", ["workflow-engine"], 4.8),
    ("F-REPORTS", "Campaign reports", "p-dev", ["data-warehouse"], 8.4),
    ("F-AI", "AI assistant", "p-rohan", ["workflow-engine"], 3.5),
    ("F-VOICE", "Voice AI", "p-ritu", ["voice-gateway"], 1.8),
    ("F-ADS", "Click-to-WhatsApp ads", "p-tom", [], 2.2),
    ("F-API", "Messaging API & webhooks", "p-arjun", ["messaging-api", "api-gateway"], 9.0),
    ("F-ACCESS", "Team, login & roles", "p-omar", ["api-gateway"], 0.8),
]
FEATURE_NAME = {f[0]: f[1] for f in FEATURES}
FEATURE_OWNER = {f[0]: f[2] for f in FEATURES}
FEATURE_RATE = {f[0]: f[4] for f in FEATURES}
CORE_FEATURES = ["F-CAMPAIGNS", "F-TEMPLATES", "F-INBOX"]

# Background bug templates: feature -> [(title, keyword, [ticket subject variants])]
BUG_TEMPLATES = {
    "F-CAMPAIGNS": [
        ("Scheduled broadcast sent twice after a retry", "duplicate broadcast", ["Our customers got the campaign twice", "Same broadcast went out two times", "Why did the 6 pm campaign send twice?"]),
        ("Campaign stuck in Processing for audiences above 1 lakh", "stuck campaign", ["Campaign stuck in processing since morning", "Broadcast not moving from Processing", "Big campaign never started"]),
        ("Personalisation variable sent blank when a contact attribute is missing", "blank variable", ["Messages going out with blank name", "Customer name missing in campaign", "Variables not filling in broadcast"]),
        ("Image header fails for PNGs above 5 MB", "media header", ["Campaign image not showing", "Header image failed for some customers", "Media not delivered in broadcast"]),
    ],
    "F-TEMPLATES": [
        ("Template status not syncing after Meta approval", "template sync", ["Template approved on Meta but shows pending", "Can't use template, still says in review", "Template status stuck"]),
        ("Carousel template preview misaligned on mobile", "carousel preview", ["Carousel preview looks broken", "Carousel cards cut off in preview", "Preview not matching WhatsApp"]),
        ("Template variables reorder after editing", "variable order", ["Variables changed order after edit", "Template sends wrong values after edit", "Edited template mixes up fields"]),
    ],
    "F-INBOX": [
        ("Inbox doesn't show new messages until refresh", "inbox refresh", ["New chats not showing in inbox", "Have to refresh to see messages", "Inbox not updating live"]),
        ("Round-robin assignment skips agents marked online", "assignment rules", ["Chats not getting assigned to my team", "Assignment skipping some agents", "Round robin not working"]),
        ("Media attachments fail to download in inbox", "inbox media", ["Can't open customer images", "Attachments not downloading", "Voice notes not playing in inbox"]),
        ("24-hour window timer wrong after a template reply", "session timer", ["Inbox says session expired but customer just replied", "24 hour window showing wrong", "Can't reply, says window closed"]),
    ],
    "F-WORKFLOWS": [
        ("Chatbot flow stops at list message node", "flow stops", ["Bot stops after the menu", "Flow not moving after list message", "Chatbot gets stuck"]),
        ("Keyword trigger is case-sensitive", "keyword trigger", ["Bot not responding to HI", "Keyword works only in lowercase", "Trigger missing some messages"]),
        ("Bot skips questions it failed to collect", "skipped questions", ["The bot skips my questions", "Bot didn't ask for pincode", "Flow skipping steps"]),
    ],
    "F-SHOPIFY": [
        ("Abandoned-cart message sent after the order was placed", "cart after order", ["Customer got cart reminder after ordering", "Abandoned cart message after purchase", "Wrong cart reminder sent"]),
        ("Order fulfilled message missing tracking link", "tracking link", ["Tracking link missing in shipping update", "Fulfilment message has no link", "Customers asking for tracking"]),
        ("Shopify contact sync creates duplicates for +91 numbers", "duplicate contacts", ["Same number showing twice", "Duplicate contacts after Shopify sync", "Contacts doubled"]),
    ],
    "F-REPORTS": [
        ("Delivery rate chart counts failed messages as sent", "delivery chart", ["Delivery numbers look too high", "Report says delivered but customers didn't get it", "Delivery rate doesn't match"]),
        ("Click tracking shows zero for shortened links", "click tracking", ["Clicks showing zero", "Link clicks not tracked", "CTR is 0 in report"]),
        ("Revenue attribution double counts repeat orders", "revenue attribution", ["Revenue in dashboard looks double", "Attributed revenue too high", "Revenue numbers don't match Shopify"]),
    ],
    "F-AI": [
        ("AI assistant replies in English to Hindi messages", "reply language", ["Bot replies in English when customer writes Hindi", "AI assistant using wrong language", "Language not detected"]),
        ("Knowledge base PDF upload stuck at processing", "kb upload", ["PDF upload stuck", "Knowledge base not updating", "Retraining never finishes"]),
        ("AI assistant answers off-script after hand-off", "off-script", ["Bot answering things it shouldn't", "AI going off script", "Assistant ignores instructions"]),
    ],
    "F-VOICE": [
        ("Voice campaign triggers only part of the audience", "partial calls", ["Only some calls went out", "Voice campaign not calling everyone", "Calls aren't connecting"]),
        ("Call recordings missing for transferred calls", "call recordings", ["No recording for transferred calls", "Recording missing in call logs", "Can't find call recording"]),
        ("Voice agent sounds different from the demo voice", "voice quality", ["Voice sounds different from the demo", "Call audio sounds robotic", "Voice quality bad on calls"]),
    ],
    "F-ADS": [
        ("CTWA referral data missing for Instagram placements", "ad referral", ["Ad source missing for Instagram leads", "Can't see which ad the chat came from", "Referral info blank"]),
        ("Conversion events not deduplicated with the Pixel", "conversion dedupe", ["Conversions counted twice in Ads Manager", "Duplicate purchase events", "Pixel and CAPI double counting"]),
    ],
    "F-API": [
        ("Webhook retries flood the endpoint after an outage", "webhook retries", ["Webhook storm after downtime", "Too many webhook retries", "Webhooks hammering our server"]),
        ("Status webhook arrives before the sent event", "webhook order", ["Delivered webhook before sent", "Webhook events out of order", "Status updates in wrong order"]),
        ("Rate limit headers missing on 429 responses", "rate limit", ["No retry-after header", "429 without rate limit info", "API throttling unclear"]),
    ],
    "F-ACCESS": [
        ("Invite emails expire before 24 hours", "invite expiry", ["Invite link expired", "New agent can't accept invite", "Invite says expired already"]),
        ("Removed agent keeps inbox access until logout", "deprovisioning", ["Ex-employee could still see chats", "Removed agent still has access", "Agent removal not working"]),
    ],
}

HOWTO_TICKETS = {
    "F-CAMPAIGNS": ["How do I schedule a campaign for 9 pm?", "Can I send a campaign to only COD customers?", "How do I stop a running campaign?"],
    "F-TEMPLATES": ["How do I get a template approved faster?", "Can we add buttons to an existing template?", "Why was my template rejected?"],
    "F-INBOX": ["How do I add a new agent to the inbox?", "Can we auto-close chats after 24 hours?", "How do I transfer a chat to another agent?"],
    "F-WORKFLOWS": ["How do I trigger a flow from an Instagram ad?", "Can a workflow wait for a reply?", "How do I test a workflow on one contact?"],
    "F-SHOPIFY": ["How do I connect a second Shopify store?", "Can COD confirmation go in Hindi?", "How do I change the cart reminder timing?"],
    "F-REPORTS": ["How do I export a campaign report?", "Where can I see revenue per campaign?", "Can I get delivery rates by template?"],
    "F-AI": ["How do I add our FAQ to the AI assistant?", "Can the assistant hand off to a human?", "Which AI model is the assistant using?"],
    "F-VOICE": ["How many calls can run at the same time?", "Can the voice agent transfer to two numbers?", "How do I clone our brand voice?"],
    "F-ADS": ["How do I connect Click-to-WhatsApp ads?", "Where do I see ad conversions?", "Can we send Purchase events to Meta?"],
    "F-API": ["Where are the API docs?", "How do I create an API key?", "Is there a sandbox number for testing?"],
    "F-ACCESS": ["How do I set up SSO?", "Can we enforce 2FA for all agents?", "How do I transfer admin rights?"],
}

TICKET_BODY_OPENERS = ["Hi team,", "Hello,", "Hi Cheerio support,", "Hey there,", "Good morning,", "Hi,"]
TICKET_BODY_CLOSERS = [
    "Can you take a look?", "Is this a known issue?", "Pls advise.", "Any update would help.",
    "This is blocking our weekly review.", "Thanks in advance.",
]

# Conversation snippets for background accounts, by intended tone.
CONVERSATION_SNIPPETS = {
    "positive": [
        "The abandoned-cart flow paid for itself in the first week, thanks for setting it up.",
        "We're planning to roll Cheerio out to two more brands next quarter.",
        "Can you send a quote for five more agent seats? The team lives in the inbox now.",
        "The Diwali broadcast did really well, really happy with it.",
        "Thanks for the quick fix, everything is running smoothly again.",
        "Our growth team loves the revenue dashboard, it replaced two spreadsheets.",
    ],
    "neutral": [
        "Quick question about the renewal paperwork, who should we send the PO to?",
        "Can we move our monthly review to next Thursday?",
        "We'd like a refresher training for the new agents.",
        "Could you share the release notes for the latest update?",
        "We're adding a second WhatsApp number for our new brand, can you help with the setup?",
        "Team, kal ka broadcast schedule kar diya hai, pls confirm the template is approved.",
    ],
    "frustrated": [
        "This is the third time this month a campaign got stuck, it's really frustrating.",
        "Honestly the team is losing patience with the constant workarounds.",
        "We keep reporting the same issue and nothing changes, this is unacceptable.",
    ],
    "competitor": [
        "Leadership asked us to look at alternatives before we renew.",
        "We've had a demo from another platform and are comparing options.",
    ],
    "budget": [
        "We're under pressure to cut software costs this year, so the renewal will get scrutinised.",
        "Budgets are tight after the festive season, we may need to reduce seats.",
    ],
}

# Fictional brand names. Prefix + suffix; the suffix fixes the industry.
IN_PREFIXES = [
    "Aranya", "Banyan", "Basil", "Bodhi", "Chandan", "Coral", "Elaichi", "Gulmohar", "Haldi", "Jamun",
    "Kokum", "Marigold", "Mitti", "Monsoon", "Neelam", "Peacock", "Pista", "Rangoli", "Sitara", "Tamarind",
    "Teak", "Tulsi", "Vayu", "Zeera", "Aarohi", "Nila", "Prakriti", "Rasa", "Urvi", "Vana", "Pagdandi", "Zaika",
    "Ojas", "Amber", "Jharokha", "Kumkum", "Laung", "Mehndi", "Noorani", "Panchi", "Sundari", "Taaza",
]
IN_SUFFIXES = [
    ("Naturals", "Beauty & personal care"), ("Skincare", "Beauty & personal care"), ("Threads", "Fashion & apparel"),
    ("Studio", "Fashion & apparel"), ("Footwear", "Fashion & apparel"), ("Jewels", "Jewellery & accessories"),
    ("Silver", "Jewellery & accessories"), ("Organics", "Food & beverage"), ("Kitchen", "Food & beverage"),
    ("Tea Co.", "Food & beverage"), ("Snacks", "Food & beverage"), ("Living", "Home & decor"), ("Home", "Home & decor"),
    ("Wellness", "Health & wellness"), ("Ayurveda", "Health & wellness"), ("Pets", "Pet care"), ("Baby", "Baby & kids"),
    ("Electronics", "Consumer electronics"), ("Finserv", "Lending & BFSI"), ("Realty", "Real estate"),
    ("Academy", "Education"), ("Holidays", "Travel"), ("Clinics", "Healthcare"),
]
US_PREFIXES = [
    "Acorn", "Bayside", "Cedar", "Driftwood", "Elmstead", "Foxglove", "Goldfinch", "Hearth", "Ironwood", "Juniper",
    "Kingfisher", "Larkspur", "Meadowbrook", "Northgate", "Oakhaven", "Pebble", "Redwood", "Saltmarsh", "Thistle",
    "Willow", "Yarrow", "Birch", "Clover", "Evergreen", "Glenrock", "Lantern", "Millbrook", "Orchard", "Riverbend",
]
US_SUFFIXES = [
    ("Candles", "Home & decor"), ("Coffee Co.", "Food & beverage"), ("Apparel", "Fashion & apparel"),
    ("Skincare", "Beauty & personal care"), ("Pet Supply", "Pet care"), ("Outfitters", "Fashion & apparel"),
    ("Supplements", "Health & wellness"), ("Bakehouse", "Food & beverage"), ("Goods", "Home & decor"),
]

CONTACT_ROLES = ["Founder", "Head of Growth", "CRM Manager", "Ops Manager", "Marketing Executive", "Finance Manager"]

# Contact names. First names avoid the Cheerio cast so transcripts stay unambiguous.
IN_FIRST = [
    "Aakash", "Aditi", "Akhil", "Alisha", "Amit", "Anika", "Ankur", "Anushka", "Arpit", "Bhavna", "Chirag",
    "Deepa", "Devika", "Gaurav", "Harsh", "Ishita", "Jatin", "Juhi", "Karishma", "Kunal", "Lavanya", "Madhav",
    "Mansi", "Mihir", "Naveen", "Nidhi", "Pallavi", "Parth", "Prachi", "Rachit", "Radhika", "Rajat", "Ritesh",
    "Sakshi", "Samar", "Shreya", "Siddhi", "Tanmay", "Tanvi", "Uday", "Vaani", "Varsha", "Yash", "Yamini", "Zubin",
]
IN_LAST = [
    "Agrawal", "Ahuja", "Bajwa", "Bedi", "Chopra", "Dutta", "Garg", "Goel", "Grover", "Hegde", "Jain", "Kapadia",
    "Khanna", "Lal", "Mahajan", "Mittal", "Nanda", "Oberoi", "Parekh", "Puri", "Rastogi", "Saxena", "Sinha",
    "Talwar", "Thakur", "Trivedi", "Vohra", "Wadhwa", "Zaveri", "Bhargava", "Chauhan", "Dhillon", "Kamath",
    "Luthra", "Mehra", "Narang", "Pandey", "Rawat", "Sachdeva", "Tandon", "Venkatesh", "Wagle",
]
US_FIRST = [
    "Ben", "Carmen", "Daniel", "Farid", "Grace", "Hiro", "Isabel", "Jamal", "Keiko", "Liam", "Mina", "Noah",
    "Olivia", "Pablo", "Quinn", "Rosa", "Samir", "Uma", "Victor", "Wen", "Zara", "Bruno", "Chloe", "Esme",
    "Felix", "Gita", "Hannah", "Ivan", "Julia", "Kofi", "Lena", "Marco", "Nadia", "Pia", "Sofia", "Tomas",
]
US_LAST = [
    "Abara", "Bergstrom", "Castillo", "Dubois", "Eriksen", "Gallagher", "Haddad", "Ibarra", "Jansen", "Kowalski",
    "Lindqvist", "Moreau", "Nakamura", "Okonkwo", "Petrov", "Quintero", "Rossi", "Sandoval", "Tanaka", "Varga",
    "Whitfield", "Yilmaz", "Zielinski", "Brennan", "Delgado", "Fischer", "Holm", "Kaplan", "Lombardi", "Novak",
]
