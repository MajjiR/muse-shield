"""Training data for entity resolution: planned scenarios, written by DeepSeek, checked twice.

1. Code plans each document: who is in it (names, roles, gender for pronouns), which private
   values exist and who owns each one, and how the people relate. Owners and relations are
   ground truth by construction.
2. DeepSeek V4 Flash writes the document from the plan, wrapping every mention in a tag:
   [[PERSON_1|Rohan]] ... [[PERSON_1|his]] salary is [[SALARY_1|₹24 LPA]].
   Tags give exact offsets for every mention, pronouns included.
3. Code checks the writing: every value appears exactly as planned, nothing untagged looks like a
   name, pronoun, phone, email, ID, amount or date, and every planned person and value appears.
4. A second, independent DeepSeek call reads the clean document (no tags, no owners) and says
   who owns each value and who each pronoun refers to. Documents where it disagrees with the plan
   are dropped: if a fresh reader can't recover the plan, the text doesn't really say it.

DeepSeek only ever sees fictional, randomly generated people. Training data only: never real
user data and never at runtime.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from muse_shield import resolution as R
from muse_shield.analysis import ContractError, _loads
from muse_shield.backends import BackendError, DeepSeekBackend
from muse_shield.costs import TOKEN_PRICES

MALE = ["Rohan", "Sandeep", "Arjun", "Kabir", "Rehan", "Sameer", "Joseph", "Arnav", "Yusuf", "Mihir", "Gaurav", "Pranav",
        "Imran", "Vivek", "Kenji", "Tobias", "Oliver", "Diego", "Sven", "Aditya", "Farhan", "Rahul", "Michael", "James",
        "Daniel", "Thomas", "Ethan", "Lucas", "Mateo", "Hiroshi", "Karthik", "Suresh", "Vikram", "Anil", "Ravi", "Omar"]
FEMALE = ["Lakshmi", "Ishita", "Meenakshi", "Tanya", "Lavanya", "Fatima", "Harpreet", "Deepa", "Nandini", "Bhavna", "Clara",
          "Shreya", "Anika", "Amara", "Leila", "Rukmini", "Keerthi", "Jasleen", "Sana", "Priyanka", "Esther", "Wen",
          "Sarah", "Emily", "Olivia", "Sophia", "Grace", "Hannah", "Isabel", "Mei", "Ananya", "Kavya", "Pooja", "Divya",
          "Aisha", "Maria"]
LAST = ["Majji", "Kumar", "Bhattacharya", "Narayanan", "Gill", "Sood", "Pillai", "Chakraborty", "Rao", "Kulkarni",
        "D'Souza", "Ansari", "Mehra", "Venkatesh", "Thakur", "Banerjee", "Fernandes", "Iyengar", "Lobo", "Chopra",
        "Ramaswamy", "Okonkwo", "Lindholm", "Haddad", "Moreno", "Tanaka", "Weber", "Mukherjee", "Saxena", "Dutta",
        "Kapoor", "Menon", "Reddy", "Nair", "Shah", "Patel", "Iyer", "Joshi", "Carter", "Bennett", "Hughes", "Walsh",
        "Novak", "Rossi", "Kim", "Nguyen", "Santos", "Ahmed"]
ORG_A = ["Acme", "Vardhan", "Silverline", "Bluegate", "Konark", "Northstar", "Tarang", "Evergreen", "Sahyadri",
         "Crescent", "Pinnacle", "Arcadia", "Indus", "Lumina", "Maple", "Orion", "Saffron", "Trident", "Zenith", "Coral",
         "Granite", "Halcyon", "Kestrel", "Meridian", "Quantum", "Redwood"]
ORG_B = ["Technologies", "Capital", "Pharma", "Logistics", "Retail", "Healthcare", "Holdings", "Foods", "Ventures",
         "Hospital", "Insurance", "Finserv", "Labs", "Motors", "Bank", "Realty", "School", "Legal LLP"]
IN_CITIES = [("Bengaluru", "560"), ("Mumbai", "400"), ("Chennai", "600"), ("Kolkata", "700"), ("Pune", "411"),
             ("Hyderabad", "500"), ("Delhi", "110"), ("Ahmedabad", "380"), ("Jaipur", "302"), ("Kochi", "682")]
IN_STREETS = ["MG Road", "Residency Road", "Anna Salai", "Park Street", "FC Road", "Linking Road", "Brigade Road",
              "Civil Lines", "Ring Road", "Hill Road", "Sector 18", "Jubilee Hills Road No. 5"]
US_PLACES = [("Austin", "TX", "787"), ("Seattle", "WA", "981"), ("Boston", "MA", "021"), ("Denver", "CO", "802"),
             ("Chicago", "IL", "606"), ("San Jose", "CA", "951")]
US_STREETS = ["Maple Avenue", "Oak Street", "Lakeview Drive", "Cedar Lane", "Elm Street", "Sunset Boulevard"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
# v3 pools: real public places and organisations (public facts; private only because a person is tied to them)
WORLD_CITIES = ["Dubai", "Singapore", "London", "Toronto", "Berlin", "Nairobi", "Lagos", "Sydney", "Hyderabad", "Jaipur",
                "Kochi", "Manila", "Jakarta", "Amman", "Doha", "Lisbon", "Melbourne", "Dublin", "Vancouver", "Riyadh",
                "Kuala Lumpur", "Cape Town", "Istanbul", "Warsaw", "Chicago", "Atlanta", "Phoenix", "Lucknow", "Indore",
                "Coimbatore", "Accra", "Dhaka", "Karachi", "Cairo", "Milan", "Osaka", "Auckland", "Calgary", "Muscat"]
STATES = ["Karnataka", "Maharashtra", "Tamil Nadu", "Kerala", "Gujarat", "Punjab", "Texas", "California", "Ontario",
          "Bavaria", "Queensland", "New South Wales", "Florida", "Telangana", "Rajasthan", "Alberta", "Ohio"]
COUNTRIES = ["India", "United Arab Emirates", "Canada", "Germany", "Kenya", "Nigeria", "Australia", "Jordan", "Ethiopia",
             "Philippines", "Indonesia", "Portugal", "Ireland", "Saudi Arabia", "Malaysia", "South Africa", "Turkey",
             "Poland", "Bangladesh", "Pakistan", "Egypt", "Italy", "Japan", "New Zealand", "Oman", "Ghana", "Qatar"]
PUBLIC_ORGS = {
    "EMPLOYERS": ["Infosys", "Deloitte", "Accenture", "Wipro", "Siemens", "Unilever", "HSBC", "Ericsson", "Cognizant",
                  "Capgemini", "Flipkart", "Swiggy", "Shopify", "Atlassian", "Salesforce", "Nestle", "Philips", "Bosch",
                  "Zoho", "Freshworks", "Mahindra", "Safaricom", "Dangote"],
    "UNIVERSITIES": ["IIT Bombay", "Anna University", "Stanford University", "McGill University", "Makerere University",
                     "Monash University", "Christ University", "BITS Pilani", "Ashoka University", "Columbia University",
                     "Trinity College Dublin", "Jadavpur University", "Manipal University", "Ryerson University"],
    "BANKS": ["HDFC Bank", "ICICI Bank", "Axis Bank", "Barclays", "Chase", "Kotak Mahindra Bank", "Wells Fargo",
              "Standard Chartered", "Citibank", "Equity Bank"],
    "BRANDS": ["Zomato", "Amazon", "Uber", "Netflix", "Spotify", "Myntra", "Starbucks", "IKEA", "Decathlon", "Nykaa",
               "Tanishq", "Zara", "Costco", "Walmart"],
    "PLATFORMS": ["LinkedIn", "Instagram", "Etsy", "Upwork", "Fiverr", "GitHub", "Shopify", "WhatsApp", "Telegram", "Notion"],
    "HOSPITALS": ["Apollo Hospitals", "Fortis Healthcare", "Manipal Hospitals", "Mayo Clinic", "Cleveland Clinic",
                  "Narayana Health", "Aster DM Healthcare"],
    "AIRLINES": ["IndiGo", "Vistara", "Lufthansa", "Etihad", "Ryanair", "KLM", "Akasa Air"],
    "HOTELS": ["Taj Hotels", "Marriott", "Hilton", "Radisson", "Hyatt", "ITC Hotels", "Novotel"],
}
GAZETTEER = sorted(set(WORLD_CITIES + STATES + COUNTRIES + [o for v in PUBLIC_ORGS.values() for o in v]), key=len, reverse=True)
DIAGNOSES = ["type 2 diabetes", "hypertension", "major depressive disorder", "asthma", "hypothyroidism",
             "chronic kidney disease stage 2", "generalised anxiety disorder", "rheumatoid arthritis", "migraine",
             "iron-deficiency anaemia"]

# Each family: document types, people (role, relation to another role), and private values
# (kind, owner role). Owners and relations are what the model must recover.
FAMILIES = {
    "hr_compensation": {
        "doc_types": ["offer letter", "salary revision letter", "annual appraisal email", "promotion letter"],
        "people": [("employee", None), ("manager", ("MANAGES", "employee")), ("hr partner", None)],
        "org": "employer",
        "values": [("SALARY", "employee"), ("SALARY", "manager"), ("ADDRESS:RESIDENTIAL", "employee"),
                   ("DATE:JOINING", "employee"), ("ID:EMPLOYEE_ID", "employee"), ("CONTACT:EMAIL", "employee"),
                   ("ID:PAN", "employee")],
        "optional_people": [("mother", ("PARENT_OF", "employee"), ("EMERGENCY_CONTACT_OF", "employee")),
                            ("spouse", ("SPOUSE_OF", "employee"), ("EMERGENCY_CONTACT_OF", "employee"))],
        "optional_values": [("CONTACT:PHONE", "@optional")],
    },
    "payroll_table": {
        "doc_types": ["monthly payroll summary with a markdown table", "bonus payout sheet with a markdown table",
                      "team compensation review with a markdown table"],
        "people": [("employee", None), ("employee", None), ("employee", None), ("payroll lead", None)],
        "org": "employer",
        "values": [("SALARY", "employee#0"), ("SALARY", "employee#1"), ("SALARY", "employee#2"),
                   ("ID:EMPLOYEE_ID", "employee#0"), ("ID:EMPLOYEE_ID", "employee#1"), ("ID:EMPLOYEE_ID", "employee#2"),
                   ("ID:BANK_ACCOUNT", "employee#0"), ("ID:BANK_ACCOUNT", "employee#1")],
    },
    "hr_investigation": {
        "doc_types": ["workplace grievance investigation memo", "disciplinary hearing notes", "POSH committee report"],
        "people": [("complainant", None), ("respondent", None), ("witness", None), ("investigator", None)],
        "org": "employer",
        "values": [("SENSITIVE_ATTRIBUTE:HEALTH", "complainant"), ("DATE:EVENT", "@none"), ("CONTACT:PHONE", "witness"),
                   ("ID:EMPLOYEE_ID", "respondent")],
    },
    "loan_sanction": {
        "doc_types": ["home loan sanction letter", "personal loan approval email", "loan restructuring notice"],
        "people": [("borrower", None), ("co-applicant", ("SPOUSE_OF", "borrower")),
                   ("guarantor", ("GUARANTOR_FOR", "borrower")), ("relationship manager", None)],
        "org": "lender",
        "values": [("LOAN", "borrower"), ("ID:BANK_ACCOUNT", "borrower"), ("ID:IFSC", "borrower"), ("ID:PAN", "borrower"),
                   ("ID:PAN", "co-applicant"), ("ID:AADHAAR", "guarantor"), ("ADDRESS:RESIDENTIAL", "borrower"),
                   ("CONTACT:PHONE", "relationship manager")],
    },
    "medical_referral": {
        "doc_types": ["hospital referral letter", "discharge summary", "specialist consultation note"],
        "people": [("patient", None), ("doctor", ("TREATS", "patient")),
                   ("daughter", ("PARENT_OF", "<patient"))],
        "org": "hospital",
        "values": [("SENSITIVE_ATTRIBUTE:HEALTH", "patient"), ("SENSITIVE_ATTRIBUTE:AGE", "patient"),
                   ("SENSITIVE_ATTRIBUTE:BODY_MEASUREMENT", "patient"), ("ID:MEDICAL_RECORD", "patient"),
                   ("DATE:DOB", "patient"), ("CONTACT:PHONE", "daughter")],
    },
    "insurance_claim": {
        "doc_types": ["life insurance claim settlement letter", "health insurance claim email", "nominee verification letter"],
        "people": [("policyholder", None), ("nominee", ("NOMINEE_OF", "policyholder")), ("claims officer", None)],
        "org": "insurer",
        "values": [("ID:POLICY", "policyholder"), ("OTHER", "nominee"), ("ID:BANK_ACCOUNT", "nominee"),
                   ("ADDRESS:RESIDENTIAL", "nominee"), ("DATE:EVENT", "@none"), ("CONTACT:EMAIL", "claims officer")],
    },
    "legal_notice": {
        "doc_types": ["legal notice for recovery of dues", "advocate's reply notice", "settlement offer letter"],
        "people": [("client", None), ("advocate", ("REPRESENTS", "client")), ("opposing party", None)],
        "org": "law firm",
        "values": [("OTHER", "client"), ("FEE", "advocate"), ("ADDRESS:RESIDENTIAL", "opposing party"),
                   ("DATE:DEADLINE", "@none"), ("CONTACT:PHONE", "advocate")],
    },
    "ma_memo": {
        "doc_types": ["confidential acquisition memo", "board note on a proposed merger", "deal team update email"],
        "people": [("deal lead", None), ("cfo", None), ("banker", None)],
        "org": "acquirer",
        "orgs": ["target company"],
        "values": [("DEAL_VALUE", "@org"), ("REVENUE", "@org2"), ("PROJECT", "@none"), ("DATE:DEADLINE", "@none"),
                   ("CONTACT:EMAIL", "banker"), ("CONTACT:PHONE", "deal lead")],
    },
    "email_thread": {
        "doc_types": ["email thread between three colleagues with signatures", "vendor onboarding email chain",
                      "client escalation email thread"],
        "people": [("sender", None), ("recipient", None), ("colleague", None)],
        "org": "employer",
        "values": [("CONTACT:PHONE", "sender"), ("CONTACT:EMAIL", "sender"), ("CONTACT:PHONE", "recipient"),
                   ("CONTACT:EMAIL", "colleague"), ("BUDGET", "@org"), ("DATE:DEADLINE", "@none")],
    },
    "kyc_update": {
        "doc_types": ["bank KYC update confirmation", "address change request acknowledgement", "credit card dispute letter"],
        "people": [("customer", None), ("relationship manager", None)],
        "org": "bank",
        "values": [("ID:BANK_ACCOUNT", "customer"), ("ID:CARD", "customer"), ("ID:AADHAAR", "customer"),
                   ("ID:PAN", "customer"), ("ADDRESS:RESIDENTIAL", "customer"), ("ADDRESS:RESIDENTIAL", "customer"),
                   ("DATE:DOB", "customer")],
    },
    "us_onboarding": {
        "doc_types": ["US new-hire onboarding packet", "I-9 verification follow-up email", "benefits enrollment confirmation"],
        "people": [("new hire", None), ("manager", ("MANAGES", "new hire")), ("benefits coordinator", None)],
        "org": "employer",
        "us": True,
        "values": [("ID:SSN", "new hire"), ("SALARY", "new hire"), ("ADDRESS:RESIDENTIAL", "new hire"),
                   ("DATE:DOB", "new hire"), ("CONTACT:PHONE", "new hire"), ("CONTACT:EMAIL", "benefits coordinator")],
        "optional_people": [("spouse", ("SPOUSE_OF", "new hire"), ("EMERGENCY_CONTACT_OF", "new hire"))],
    },
    "meeting_minutes": {
        "doc_types": ["leadership meeting minutes", "project steering committee minutes", "quarterly review notes"],
        "people": [("chair", None), ("project lead", ("MANAGES", "@analyst")), ("analyst", None)],
        "org": "company",
        "values": [("BUDGET", "@org"), ("PROJECT", "@none"), ("DATE:DEADLINE", "@none"), ("REVENUE", "@org")],
    },
    # v2: several people related to one person, and more kinds of amounts
    "minor_consent": {
        "doc_types": ["surgical consent form for a minor", "paediatric treatment consent letter", "hospital admission note for a child"],
        "people": [("child", None), ("father", ("PARENT_OF", "child")), ("mother", ("PARENT_OF", "child")),
                   ("doctor", ("TREATS", "child"))],
        "org": "hospital",
        "values": [("DATE:DOB", "child"), ("SENSITIVE_ATTRIBUTE:AGE", "child"), ("SENSITIVE_ATTRIBUTE:HEALTH", "child"),
                   ("ID:MEDICAL_RECORD", "child"), ("CONTACT:PHONE", "father"), ("CONTACT:PHONE", "mother"),
                   ("ID:AADHAAR", "mother"), ("FEE", "child", "hospital deposit")],
    },
    "passport_minor": {
        "doc_types": ["minor passport application cover letter", "family visa application summary", "travel consent letter for a child"],
        "people": [("child", None), ("father", ("PARENT_OF", "child")), ("mother", ("PARENT_OF", "child")),
                   ("passport officer", None)],
        "org": None,
        "values": [("DATE:DOB", "child"), ("ID:PASSPORT", "child"), ("ID:PASSPORT", "father"), ("ADDRESS:RESIDENTIAL", "father"),
                   ("CONTACT:PHONE", "mother"), ("CONTACT:EMAIL", "father"), ("FEE", "father", "application fee")],
    },
    "family_insurance": {
        "doc_types": ["family floater health policy schedule", "family health insurance renewal notice", "policy endorsement adding dependants"],
        "people": [("policyholder", None), ("spouse", [("SPOUSE_OF", "policyholder"), ("NOMINEE_OF", "policyholder")]),
                   ("son", ("PARENT_OF", "<policyholder")), ("daughter", ("PARENT_OF", "<policyholder")), ("agent", None)],
        "org": "insurer",
        "values": [("PRICE", "policyholder", "annual premium"), ("ID:POLICY", "policyholder"), ("DATE:DOB", "son"),
                   ("DATE:DOB", "daughter"), ("SENSITIVE_ATTRIBUTE:HEALTH", "spouse"), ("ID:BANK_ACCOUNT", "policyholder"),
                   ("CONTACT:PHONE", "agent")],
    },
    "loan_guarantors": {
        "doc_types": ["business loan sanction with two guarantors", "guarantee deed summary", "loan recovery notice to a borrower and guarantors"],
        "people": [("borrower", None), ("guarantor", ("GUARANTOR_FOR", "borrower")), ("guarantor", ("GUARANTOR_FOR", "borrower")),
                   ("credit officer", None)],
        "org": "lender",
        "values": [("LOAN", "borrower"), ("LOAN", "borrower", "monthly EMI"), ("ID:PAN", "guarantor#0"), ("ID:PAN", "guarantor#1"),
                   ("ADDRESS:RESIDENTIAL", "guarantor#1"), ("ID:BANK_ACCOUNT", "borrower"), ("CONTACT:PHONE", "credit officer")],
    },
    "team_review": {
        "doc_types": ["team compensation review memo", "quarterly team performance summary", "manager's note on team bonuses"],
        "people": [("manager", [("MANAGES", "analyst"), ("MANAGES", "engineer"), ("MANAGES", "designer")]),
                   ("analyst", None), ("engineer", None), ("designer", None)],
        "org": "employer",
        "values": [("SALARY", "analyst"), ("SALARY", "engineer"), ("SALARY", "designer", "annual bonus"), ("SALARY", "manager"),
                   ("ID:EMPLOYEE_ID", "engineer"), ("SENSITIVE_ATTRIBUTE:HEALTH", "designer")],
    },
    "sibling_estate": {
        "doc_types": ["property partition agreement between siblings", "succession certificate application", "family settlement letter"],
        "people": [("sister", ("SIBLING_OF", "brother")), ("brother", None),
                   ("advocate", [("REPRESENTS", "sister"), ("REPRESENTS", "brother")])],
        "org": "law firm",
        "values": [("ADDRESS:RESIDENTIAL", "sister"), ("ADDRESS:RESIDENTIAL", "brother"), ("ID:PAN", "sister"), ("ID:PAN", "brother"),
                   ("OTHER", "sister", "settlement amount"), ("FEE", "advocate", "professional fee")],
    },
    "relocation_letter": {
        "doc_types": ["employee relocation approval letter", "accommodation allowance letter", "transfer and relocation email"],
        "people": [("employee", None), ("manager", ("MANAGES", "employee")), ("hr partner", None)],
        "org": "employer",
        "values": [("PRICE", "employee", "monthly rent of the new flat"), ("FEE", "employee", "security deposit"),
                   ("SALARY", "employee", "relocation allowance"), ("OTHER", "employee", "travel reimbursement"),
                   ("ADDRESS:RESIDENTIAL", "employee"), ("DATE:JOINING", "employee")],
    },
    # v3: chat requests (what people actually paste into chatbots) and the value types public benchmarks count
    "chat_career": {
        "doc_types": ["message a person types into an AI chatbot asking it to write a cover letter, pasting their own background",
                      "chatbot request to rewrite the person's resume summary, with their details pasted in",
                      "request to an AI assistant to draft a LinkedIn About section from the person's career history",
                      "message asking an AI to prepare the person for a job interview, describing their experience"],
        "people": [("user", None)], "us": "random",
        "optional_people": [("former manager", ("MANAGES", "user"))],
        "public_orgs": [("current employer", "EMPLOYERS"), ("university", "UNIVERSITIES"), ("company applied to", "EMPLOYERS")],
        "values": [("LOCATION:CITY", "user"), ("CONTACT:URL", "user"), ("CONTACT:EMAIL", "user"), ("LOCATION:COUNTRY", "user"),
                   ("CONTACT:PHONE", "user"), ("SALARY", "user")],
    },
    "chat_travel": {
        "doc_types": ["chatbot request to draft a visa invitation letter for the person's sister, with travel details",
                      "message asking an AI to plan a trip itinerary around the person's bookings",
                      "request to an AI to write an email to an embassy about a visa appointment",
                      "message asking a chatbot to help write a leave application for an overseas family trip"],
        "people": [("user", None), ("sister", ("SIBLING_OF", "user"))], "us": "random",
        "public_orgs": [("airline", "AIRLINES"), ("hotel", "HOTELS")],
        "values": [("LOCATION:COUNTRY", "user"), ("LOCATION:CITY", "user"), ("LOCATION:CITY", "sister"), ("ID:PASSPORT", "sister"),
                   ("DATE:EVENT", "user"), ("DATE:TIME", "user"), ("CONTACT:PHONE", "user")],
    },
    "chat_business": {
        "doc_types": ["message asking an AI to write a short business plan for the person's company",
                      "chatbot request to draft a reply to a client, pasting the client's email",
                      "request to an AI for Instagram captions and a bio for the person's shop",
                      "message asking a chatbot to review a sales pitch to a named customer"],
        "people": [("owner", None), ("client", None)], "org": "own business", "us": "random",
        "public_orgs": [("client company", "EMPLOYERS"), ("platform", "PLATFORMS")],
        "values": [("CONTACT:URL", "owner"), ("CONTACT:USERNAME", "owner"), ("LOCATION:CITY", "owner"), ("REVENUE", "@org"),
                   ("CONTACT:EMAIL", "client"), ("LOCATION:STATE", "owner")],
    },
    "chat_health": {
        "doc_types": ["message asking an AI chatbot for advice about a health problem, sharing personal details",
                      "request to an AI to write a sick-leave email to the person's employer",
                      "chatbot request to draft a message to a doctor about test results",
                      "message asking an AI for a diet plan that fits the person's religion and condition"],
        "people": [("user", None), ("doctor", ("TREATS", "user"))], "us": "random",
        "public_orgs": [("hospital", "HOSPITALS"), ("employer", "EMPLOYERS")],
        "values": [("SENSITIVE_ATTRIBUTE:HEALTH", "user"), ("SENSITIVE_ATTRIBUTE:AGE", "user"), ("SENSITIVE_ATTRIBUTE:GENDER", "user"),
                   ("SENSITIVE_ATTRIBUTE:RELIGION", "user"), ("LOCATION:CITY", "user"), ("DATE:TIME", "user"), ("DATE:EVENT", "user")],
    },
    "chat_finance": {
        "doc_types": ["message asking an AI to analyse the person's monthly spending, pasting a few transactions",
                      "chatbot request to draft a complaint to the person's bank about a wrong charge",
                      "request to an AI to help plan the person's savings and loan repayments",
                      "message asking a chatbot to explain a credit card statement line by line"],
        "people": [("user", None)], "us": "random",
        "optional_people": [("spouse", ("SPOUSE_OF", "user"))],
        "public_orgs": [("bank", "BANKS"), ("merchant", "BRANDS"), ("app", "PLATFORMS")],
        "values": [("ID:BANK_ACCOUNT", "user"), ("ID:CARD", "user"), ("OTHER", "user"), ("LOAN", "user"), ("DATE:EVENT", "user"),
                   ("DATE:TIME", "user"), ("LOCATION:CITY", "user")],
    },
    "tech_support": {
        "doc_types": ["IT helpdesk ticket about a login problem", "server access request email", "bug report with a few log lines",
                      "security incident note about a suspicious login"],
        "people": [("employee", None), ("it admin", None)], "org": "employer", "us": "random",
        "values": [("ID:IP_ADDRESS", "employee"), ("CONTACT:USERNAME", "employee"), ("CONTACT:URL", "@org"),
                   ("SECRET:PASSWORD", "employee"), ("ID:DEVICE", "employee"), ("DATE:TIME", "@none"), ("DATE:EVENT", "@none"),
                   ("CONTACT:EMAIL", "employee"), ("SECRET:API_KEY", "it admin")],
    },
    "profile_form": {
        "doc_types": ["community membership registration form", "user profile export from a social app",
                      "survey response with demographic questions", "volunteer sign-up form"],
        "people": [("member", None)], "us": "random",
        "public_orgs": [("employer", "EMPLOYERS"), ("school", "UNIVERSITIES")],
        "values": [("SENSITIVE_ATTRIBUTE:GENDER", "member"), ("SENSITIVE_ATTRIBUTE:RELIGION", "member"),
                   ("SENSITIVE_ATTRIBUTE:POLITICS", "member"), ("SENSITIVE_ATTRIBUTE:CASTE_ETHNICITY", "member"),
                   ("SENSITIVE_ATTRIBUTE:SEXUALITY", "member"), ("SENSITIVE_ATTRIBUTE:AGE", "member"), ("LOCATION:CITY", "member"),
                   ("LOCATION:COUNTRY", "member"), ("CONTACT:USERNAME", "member"), ("CONTACT:URL", "member"), ("DATE:DOB", "member")],
    },
    "event_schedule": {
        "doc_types": ["meeting invite email with times and a venue", "itinerary for a conference trip",
                      "delivery and pickup schedule message", "wedding guest arrival plan"],
        "people": [("organiser", None), ("guest", None)], "us": "random",
        "public_orgs": [("venue hotel", "HOTELS"), ("company", "EMPLOYERS")],
        "values": [("DATE:EVENT", "@none"), ("DATE:TIME", "@none"), ("DATE:TIME", "guest"), ("LOCATION:CITY", "@none"),
                   ("LOCATION:COUNTRY", "@none"), ("CONTACT:PHONE", "organiser"), ("CONTACT:URL", "organiser")],
    },
    # held out entirely: the challenge test set has document structures the model never trained on
    "tenancy_agreement": {
        "doc_types": ["residential rental agreement", "tenancy renewal letter", "security deposit refund notice"],
        "people": [("landlord", ("LANDLORD_OF", "tenant")), ("tenant", None), ("witness", None)],
        "org": None,
        "values": [("PRICE", "tenant"), ("FEE", "tenant"), ("ID:AADHAAR", "landlord"), ("ID:PAN", "tenant"),
                   ("ADDRESS:RESIDENTIAL", "landlord"), ("CONTACT:PHONE", "tenant"), ("DATE:JOINING", "tenant")],
    },
    "school_admission": {
        "doc_types": ["school admission confirmation", "fee concession application", "parent-teacher meeting summary"],
        "people": [("student", None), ("father", ("PARENT_OF", "student")), ("mother", ("PARENT_OF", "student")),
                   ("class teacher", None)],
        "org": "school",
        "values": [("DATE:DOB", "student"), ("SENSITIVE_ATTRIBUTE:AGE", "student"), ("FEE", "student"),
                   ("CONTACT:PHONE", "father"), ("CONTACT:EMAIL", "mother"), ("SENSITIVE_ATTRIBUTE:HEALTH", "student")],
    },
}
CHALLENGE_FAMILIES = {"tenancy_agreement", "school_admission"}
V3_FAMILIES = {"chat_career", "chat_travel", "chat_business", "chat_health", "chat_finance", "tech_support", "profile_form",
               "event_schedule"}
V2_FAMILIES = {"minor_consent", "passport_minor", "family_insurance", "loan_guarantors", "team_review", "sibling_estate",
               "relocation_letter"}
FEMALE_ROLES, MALE_ROLES = {"mother", "daughter", "sister", "wife"}, {"father", "son", "brother", "husband"}
FAMILY_ROLES = {"mother", "father", "daughter", "son", "spouse", "co-applicant", "student", "child", "sister", "brother",
                "policyholder"}
ORG_SUFFIX = {"hospital": ["Hospital", "Healthcare", "Medical Centre"], "lender": ["Bank", "Finserv", "Housing Finance"],
              "bank": ["Bank", "Co-operative Bank"], "insurer": ["Insurance", "Life Insurance"],
              "law firm": ["Legal LLP", "& Associates"], "school": ["Public School", "International School"]}
AMOUNT_KINDS = R.AMOUNT_ROLES
GENERIC = {"policy circular": "a company-wide IT acceptable-use policy update",
           "product announcement": "a product feature announcement for customers"}


def _digits(rng, n):
    return "".join(rng.choice("0123456789") for _ in range(n))


def _letters(rng, n):
    return "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(n))


def make_value(kind: str, rng: random.Random, us: bool, owner_name: str | None) -> tuple[str, str, str | None, str | None]:
    """(value, type, role, subtype) for one planned private value."""
    if kind in AMOUNT_KINDS:
        if us:
            v = rng.choice([f"${rng.randint(60, 240)},{rng.randint(0, 9)}00", f"${rng.randint(2, 90)},{rng.randint(100, 999)}"])
        elif kind == "SALARY":
            v = rng.choice([f"₹{rng.randint(6, 60)} LPA", f"₹{rng.randint(4, 40)},{rng.randint(10, 99)},000 per annum",
                            f"₹{rng.randint(40, 300)},{rng.randint(100, 999)} per month"])
        elif kind in ("DEAL_VALUE", "REVENUE"):
            v = rng.choice([f"₹{rng.randint(50, 4000)} crore", f"${rng.randint(20, 900)} million"])
        elif kind in ("PRICE", "FEE"):
            v = rng.choice([f"₹{rng.randint(8, 95)},000", f"₹{rng.randint(1, 9)},{rng.randint(10, 99)},000",
                            f"Rs. {rng.randint(10, 99)},{rng.randint(100, 999)}", f"₹{rng.randint(2, 30)} lakh"])
        else:
            v = rng.choice([f"₹{rng.randint(2, 95)} lakh", f"₹{rng.randint(10, 99)},{rng.randint(100, 999)}",
                            f"Rs. {rng.randint(1, 9)},{rng.randint(10, 99)},{rng.randint(100, 999)}"])
        return v, "AMOUNT", kind, None
    if kind == "PROJECT":
        return f"Project {rng.choice(['Falcon', 'Neptune', 'Bluebird', 'Sapphire', 'Monsoon', 'Atlas', 'Granite', 'Lotus'])}", "PROJECT", None, None
    t, sub = kind.split(":")
    first = (owner_name or "contact").split()[0].lower()
    last = (owner_name or "x y").split()[-1].lower().replace("'", "")
    if sub == "PHONE":
        v = f"+1 ({rng.randint(200, 989)}) {rng.randint(200, 989)}-{_digits(rng, 4)}" if us else \
            f"+91 {rng.choice('6789')}{_digits(rng, 4)} {_digits(rng, 5)}"
    elif sub == "EMAIL":
        v = f"{first}.{last}{rng.randint(1, 99)}@{rng.choice(['gmail.com', 'outlook.com', 'yahoo.com', 'proton.me'])}"
    elif sub == "AADHAAR":
        v = f"{rng.randint(2, 9)}{_digits(rng, 3)} {_digits(rng, 4)} {_digits(rng, 4)}"
    elif sub == "PAN":
        v = _letters(rng, 3) + "P" + _letters(rng, 1) + _digits(rng, 4) + _letters(rng, 1)
    elif sub == "IFSC":
        v = _letters(rng, 4) + "0" + _digits(rng, 6)
    elif sub == "BANK_ACCOUNT":
        v = _digits(rng, rng.choice([11, 12, 14]))
    elif sub == "CARD":
        v = f"{rng.choice(['4', '5'])}{_digits(rng, 3)} {_digits(rng, 4)} {_digits(rng, 4)} {_digits(rng, 4)}"
    elif sub == "SSN":
        v = f"{rng.randint(100, 665)}-{rng.randint(10, 99)}-{_digits(rng, 4)}"
    elif sub == "EMPLOYEE_ID":
        v = rng.choice([f"EMP-{_digits(rng, 5)}", f"E{_digits(rng, 6)}", f"{_letters(rng, 2)}/{_digits(rng, 4)}"])
    elif sub == "MEDICAL_RECORD":
        v = f"MRN-{rng.randint(2019, 2026)}-{_digits(rng, 5)}"
    elif sub == "PASSPORT":
        v = rng.choice(_letters(rng, 1)) + _digits(rng, 7)
    elif sub == "POLICY":
        v = f"POL/{rng.randint(2018, 2026)}/{_digits(rng, 6)}"
    elif sub == "RESIDENTIAL":
        if us:
            city, st, z = rng.choice(US_PLACES)
            v = f"{rng.randint(10, 9800)} {rng.choice(US_STREETS)}, {city}, {st} {z}{_digits(rng, 2)}"
        else:
            city, pin = rng.choice(IN_CITIES)
            v = (f"{rng.randint(1, 450)}, {rng.choice(['Sunrise Apartments', 'Lake View Towers', 'Green Park Society', 'Palm Grove Layout'])}, "
                 f"{rng.choice(IN_STREETS)}, {city} {pin}{_digits(rng, 3)}")
    elif t == "DATE" and sub != "TIME":
        y = rng.randint(1958, 2008) if sub == "DOB" else rng.randint(2024, 2027)
        v = rng.choice([f"{rng.randint(1, 28)} {rng.choice(MONTHS)} {y}", f"{rng.choice(MONTHS)} {rng.randint(1, 28)}, {y}"])
    elif sub == "HEALTH":
        v = rng.choice(DIAGNOSES)
    elif sub == "AGE":
        v = f"{rng.randint(6, 85)} years old"
    elif sub == "BODY_MEASUREMENT":
        v = rng.choice([f"{rng.randint(45, 110)} kg", f"{rng.randint(150, 192)} cm"])
    elif sub == "CITY":
        v = rng.choice(WORLD_CITIES + [c for c, *_ in (US_PLACES if us else IN_CITIES)])
    elif sub == "STATE":
        v = rng.choice(STATES)
    elif sub == "COUNTRY":
        v = rng.choice(COUNTRIES)
    elif sub == "URL":
        v = rng.choice([f"linkedin.com/in/{first}-{last}-{_digits(rng, 3)}", f"https://github.com/{first}{last}{rng.randint(1, 99)}",
                        f"https://www.{first}{last}.com", f"https://{first}-{last}.netlify.app/portfolio",
                        f"https://www.instagram.com/{first}.{last}{rng.randint(1, 99)}", f"www.{last}{rng.choice(['studio', 'designs', 'consulting'])}.in"])
    elif sub == "USERNAME":
        v = rng.choice([f"@{first}_{last}{rng.randint(1, 99)}", f"{first}{last}{rng.randint(10, 99)}", f"{first[0]}{last}_{_digits(rng, 2)}"])
    elif sub == "IP_ADDRESS":
        v = rng.choice([f"{rng.randint(11, 223)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}",
                        f"192.168.{rng.randint(0, 20)}.{rng.randint(2, 254)}"])
    elif sub == "DEVICE":
        v = rng.choice([f"LAPTOP-{_letters(rng, 3)}{_digits(rng, 4)}", f"SN {_letters(rng, 2)}{_digits(rng, 8)}",
                        ":".join(f"{rng.randint(0, 255):02X}" for _ in range(6))])
    elif sub == "PASSWORD":
        v = rng.choice([f"{first.capitalize()}@{rng.randint(1970, 2010)}", f"{last.capitalize()}#{_digits(rng, 4)}!",
                        f"Sunflower{_digits(rng, 3)}$"])
    elif sub == "API_KEY":
        v = rng.choice([f"sk_test_{_letters(rng, 6).lower()}{_digits(rng, 10)}", f"AKIA{_letters(rng, 12)}{_digits(rng, 4)}"])
    elif sub == "TIME":
        h = rng.randint(1, 12)
        v = rng.choice([f"{h}:{rng.choice(['00', '15', '30', '45'])} {rng.choice(['AM', 'PM'])}", f"{rng.randint(6, 22):02d}:{rng.choice(['00', '30', '45'])}",
                        f"{h} {rng.choice(['am', 'pm'])}"])
    elif sub == "GENDER":
        v = rng.choice(["female", "male", "non-binary", "transgender woman", "transgender man"])
    elif sub == "RELIGION":
        v = rng.choice(["Hindu", "Muslim", "Christian", "Sikh", "Buddhist", "Jain", "Jewish", "Catholic", "atheist"])
    elif sub == "POLITICS":
        v = rng.choice(["a registered Democrat", "a Labour Party member", "a Republican voter", "a member of the Green Party",
                        "a left-leaning voter", "a conservative voter"])
    elif sub == "CASTE_ETHNICITY":
        v = rng.choice(["Tamil", "Punjabi", "Hispanic", "Black British", "Dalit", "Yoruba", "Malayali", "Arab", "Bengali"])
    elif sub == "SEXUALITY":
        v = rng.choice(["gay", "lesbian", "bisexual", "asexual", "queer"])
    else:
        raise ValueError(kind)
    return v, t, None, sub


def plan(rng: random.Random, family: str, uid: str) -> dict:
    """A document plan: entities with values and owners, relations, and writing instructions."""
    if family == "generic":
        doc_type = rng.choice(list(GENERIC))
        return {"uid": uid, "family": family, "doc_type": doc_type, "brief": GENERIC[doc_type], "entities": [],
                "relations": [], "ambiguous": None}
    fam = FAMILIES[family]
    us = fam.get("us", False)
    if us == "random":
        us = rng.random() < 0.4
    people = list(fam["people"])
    extra_rel = []
    for opt in fam.get("optional_people", []):
        if rng.random() < 0.5:
            people.append((opt[0], opt[1]))
            extra_rel += [(opt[0], *r) for r in opt[2:]]
            break
    family_last = rng.choice(LAST)
    ents, by_role, names_used = [], {}, set()
    for i, (role, _) in enumerate(people):
        gender = "female" if role in FEMALE_ROLES else ("male" if role in MALE_ROLES else rng.choice(["male", "female"]))
        while True:
            first = rng.choice(MALE if gender == "male" else FEMALE)
            last = family_last if role in FAMILY_ROLES and rng.random() < 0.85 else rng.choice(LAST)
            if first not in names_used:
                break
        names_used.add(first)
        ent = {"key": f"P{i}", "type": "PERSON", "role": role, "name": f"{first} {last}", "gender": gender}
        ents.append(ent)
        by_role.setdefault(role, []).append(ent)
    orgs = []
    if fam.get("org"):
        suffix = rng.choice(ORG_SUFFIX.get(fam["org"], ["Technologies", "Capital", "Pharma", "Logistics", "Retail", "Holdings",
                                                              "Foods", "Ventures", "Labs", "Motors", "Realty", "Textiles"]))
        orgs.append({"key": "O0", "type": "ORG", "role": fam["org"], "name": f"{rng.choice(ORG_A)} {suffix}"})
    for j, r in enumerate(fam.get("orgs", []), 1):
        orgs.append({"key": f"O{j}", "type": "ORG", "role": r, "name": f"{rng.choice(ORG_A)} {rng.choice(ORG_B)}"})
    used_orgs = set()
    for j, (r, pool) in enumerate(fam.get("public_orgs", [])):
        name = rng.choice([o for o in PUBLIC_ORGS[pool] if o not in used_orgs])
        used_orgs.add(name)
        orgs.append({"key": f"Q{j}", "type": "ORG", "role": r, "name": name})
    ents += orgs

    def resolve(role_ref: str):
        if role_ref == "@none":
            return None
        if role_ref == "@org":
            return orgs[0]["key"] if orgs else None
        if role_ref == "@org2":
            return orgs[1]["key"] if len(orgs) > 1 else None
        role, _, idx = role_ref.partition("#")
        cands = by_role.get(role.lstrip("@"), [])
        return cands[int(idx or 0)]["key"] if cands else None

    rels = []
    for i, (role, rel) in enumerate(people):
        for name, target in ([rel] if isinstance(rel, tuple) else rel or []):
            src = ents[i]["key"]
            if target.startswith("<"):  # reversed: that role -> this person ("<policyholder" PARENT_OF son)
                other = resolve(target[1:])
                if other:
                    rels.append([other, name, src])
            else:
                dst = resolve(target)
                if dst and dst != src:
                    rels.append([src, name, dst])
    for role, name, target in extra_rel:
        rels.append([by_role[role][0]["key"], name, resolve(target)])
    if fam.get("org"):
        employed = [e for e in ents if e["type"] == "PERSON" and e["role"] in
                    ("employee", "manager", "hr partner", "new hire", "deal lead", "cfo", "relationship manager",
                     "doctor", "claims officer", "advocate", "payroll lead", "investigator", "class teacher", "sender",
                     "analyst", "engineer", "designer", "agent", "credit officer")]
        for e in employed[:2]:
            rels.append([e["key"], "EMPLOYED_BY", orgs[0]["key"]])

    values = list(fam["values"])
    opt_people = [e for e in ents if e["type"] == "PERSON" and e["role"] in ("mother", "spouse")]
    for kind, owner in fam.get("optional_values", []):
        if owner == "@optional" and opt_people:
            values.append((kind, opt_people[0]["role"]))
    rng.shuffle(values)
    values = values[: max(3, len(values) - rng.randint(0, 2))]
    for k, (kind, owner_ref, *hint) in enumerate(values):
        owner = resolve(owner_ref)
        owner_name = next((e["name"] for e in ents if e["key"] == owner), None)
        v, t, role, sub = make_value(kind, rng, us, owner_name)
        ents.append({"key": f"V{k}", "type": t, "role": role, "subtype": sub, "value": v, "owner": owner,
                     "hint": hint[0] if hint else None})

    # sometimes one value is written so that its owner is genuinely unclear
    ambiguous = None
    persons = [e for e in ents if e["type"] == "PERSON"]
    owned = [e for e in ents if e.get("owner") and e["type"] in ("AMOUNT", "CONTACT", "DATE")]
    if len(persons) >= 2 and owned and rng.random() < 0.05:  # v2: most ambiguity is now built in code (add_ambiguity)
        target = rng.choice(owned)
        a = next(p for p in persons if p["key"] == target["owner"]) if any(p["key"] == target["owner"] for p in persons) else persons[0]
        b = rng.choice([p for p in persons if p is not a])
        if a["gender"] == b["gender"]:
            target["owner"] = R.UNKNOWN
            ambiguous = {"value": target["key"], "between": [a["key"], b["key"]]}
    words = rng.choices(["120 and 320", "350 and 600", "600 and 1000"], [0.6, 0.25, 0.15])[0]
    return {"uid": uid, "family": family, "doc_type": rng.choice(fam["doc_types"]), "us": us, "words": words,
            "entities": ents, "relations": rels, "ambiguous": ambiguous}


WRITER_PROMPT = """Write ONE realistic document: {doc_type}. Between {words} words. Plain text (markdown tables only if the document type asks for a table).

Use ONLY these people, organisations and private values. Each value must appear exactly as written here.
The role after each person describes their part in the document; give them natural job titles where needed.
{spec}

Relationships the document must make clear: {relations}
{ambiguity}
Tag EVERY mention of every listed item as [[KEY|text]]: full names, first names, title + surname ("Mr Rao", "Dr. Iyer"),
third-person pronouns that refer to a listed person (he, him, his, himself, she, her, hers, herself) EVERY time they
occur, and descriptions that refer to them ("the employee", "her mother"). Do not tag "you", "your" or "I".
Private values keep their exact text inside the tag: [[V1|value as listed]]. Make it clear in the text who each private
value belongs to (e.g. "Rohan's salary", "his address", a table row, a signature block), but vary how you say it.
Refer to people in varied ways: sometimes first name, sometimes title + surname, sometimes a pronoun.
Do NOT add any other person, phone number, email, ID number, address, specific date or money amount, and no other
city, state, country, company, school, bank, brand, app, website, username or time of day.
Return only the tagged document, nothing else."""

GENERIC_PROMPT = """Write ONE realistic document: {brief}. Between 100 and 250 words. It must contain no personal data at all:
no names of people, no organisation names, no phone numbers, emails, addresses, ID numbers, specific dates or money amounts.
Return only the document."""


def writer_messages(p: dict) -> list[dict]:
    if p["family"] == "generic":
        return [{"role": "user", "content": GENERIC_PROMPT.format(brief=p["brief"])}]
    lines = []
    for e in p["entities"]:
        if e["type"] == "PERSON":
            lines.append(f"- {e['key']}: person, {e['name']}, {e['role']} ({'he/him' if e['gender'] == 'male' else 'she/her'})")
        elif e["type"] == "ORG":
            lines.append(f"- {e['key']}: organisation, {e['name']} ({e['role']})")
        else:
            what = e["role"].lower().replace("_", " ") if e["type"] == "AMOUNT" else (e["subtype"] or e["type"]).lower().replace("_", " ")
            if e["type"] == "PROJECT":
                what = "internal project codename"
            if e.get("hint"):
                what = e["hint"]
            owner = "" if not e.get("owner") else (" — whose it is must stay unclear (see below)" if e["owner"] == R.UNKNOWN
                                                   else f" — belongs to {e['owner']}")
            lines.append(f"- {e['key']}: {what}: {e['value']}{owner}")
    names = {e["key"]: e.get("name", e["key"]) for e in p["entities"]}
    rels = "; ".join(f"{names[a]} {r.lower().replace('_', ' ')} {names[b]}" for a, r, b in p["relations"]) or "none"
    amb = ""
    if p["ambiguous"]:
        a, b = p["ambiguous"]["between"]
        amb = (f"\nWrite {p['ambiguous']['value']} so that a careful reader CANNOT tell whether it belongs to {names[a]} or "
               f"{names[b]} (for example a pronoun that could refer to either, both being the same gender). Tag that pronoun "
               f"with the key of whichever person you had in mind, but do not resolve it anywhere in the text.\n")
    return [{"role": "user", "content": WRITER_PROMPT.format(doc_type=p["doc_type"], words=p.get("words", "120 and 320"),
                                                               spec="\n".join(lines),
                                                               relations=rels, ambiguity=amb)}]


TAG = re.compile(r"\[\[([A-Z]\d+)\|([^\[\]|]+?)\]\]")
_PRONOUN = re.compile(r"\b(he|him|his|himself|she|her|hers|herself)\b", re.IGNORECASE)
_SECOND = re.compile(r"(?i)^(you|your|yours|yourself|yourselves|i|me|my|mine|we|our|us)$")
_TITLES = {"mr", "mrs", "ms", "dr", "prof", "shri", "smt", "sir", "madam", "adv", "advocate"}
_LEAKY = [re.compile(p) for p in (r"https?://|www\.|\b[\w-]+\.(?:com|in|org|net|io|app)\b", r"\b\d{1,2}:\d{2}\b",
                                  r"\b\d{1,2}\s?(?:am|pm|AM|PM|a\.m\.|p\.m\.)(?!\w)", r"\b\d{1,3}(?:\.\d{1,3}){3}\b",
                                  r"[\w.+-]+@[\w-]+\.\w+", r"\+\d[\d\s()-]{8,}", r"\b\d{6,}\b", r"[₹$]\s?\d",
                                  r"\bRs\.?\s?\d", r"\b[A-Z]{5}\d{4}[A-Z]\b", r"\b\d{3}-\d{2}-\d{4}\b",
                                  r"\b\d{1,2} (?:%s) \d{4}\b" % "|".join(MONTHS), r"\b(?:%s) \d{1,2}, \d{4}\b" % "|".join(MONTHS))]


def untag(tagged: str) -> tuple[str, list[tuple[str, int, int]]]:
    out, mentions, cursor = [], [], 0
    for m in TAG.finditer(tagged):
        out.append(tagged[cursor:m.start()])
        start = sum(len(x) for x in out)
        out.append(m.group(2))
        mentions.append((m.group(1), start, start + len(m.group(2))))
        cursor = m.end()
    out.append(tagged[cursor:])
    return "".join(out), mentions


def _digits_of(v: str) -> str:
    return re.sub(r"\D", "", v)


def check(p: dict, tagged: str) -> tuple[dict | None, str]:
    """Turn the writer's output into a gold document, or say why it can't be trusted.

    Safe repairs instead of drops: untag "you/your" (often the letter's reader, who isn't in the plan) and bare
    role words; accept a value written with the same digits; tag missed names and missed he/she when only one
    planned person has that gender. Pronouns that are still ambiguous go to the reader (`pending`).
    """
    tagged = tagged.strip().strip("`").strip()
    if p["family"] == "generic":
        if "[[" in tagged:
            return None, "tags in generic doc"
        for pat in _LEAKY + [_PRONOUN]:
            if pat.search(tagged):
                return None, f"personal data in generic doc: {pat.pattern[:20]}"
        return {"uid": p["uid"], "family": p["family"], "doc_type": p["doc_type"], "text": tagged, "entities": [],
                "relations": [], "pending": []}, ""
    if "[[" in TAG.sub("", tagged) or "]]" in TAG.sub("", tagged):
        return None, "malformed tag"
    text, mentions = untag(tagged)
    by_key = {e["key"]: e for e in p["entities"]}
    persons = [e for e in p["entities"] if e["type"] == "PERSON"]
    got: dict[str, list[tuple[int, int]]] = {}
    for key, s, e in mentions:
        if key not in by_key:
            return None, f"unknown key {key}"
        ent, surface = by_key[key], text[s:e]
        if re.fullmatch(r"(?i)(he|she|they)/(him|her|them)(/\w+)?", surface.strip()):
            continue  # a pronouns field ("she/her") copied from the plan: not a mention
        if ent["type"] in ("PERSON", "ORG") and re.search(r"['’]s$", surface) and not R.is_reference(surface):
            e -= 2  # "Amara's": the name is the mention, not the possessive
            surface = text[s:e]
        if ent["type"] in ("PERSON", "ORG"):
            words = set(re.findall(r"[\w']+", surface.lower()))
            if _SECOND.match(surface.strip()):
                continue  # second person: not annotated
            if ent["type"] == "PERSON" and not R.is_reference(surface):
                parts = set(re.findall(r"[\w']+", ent["name"].lower()))
                names = words - _TITLES
                if not names <= parts or not names:
                    if words <= set(ent["role"].split()) | _TITLES:
                        continue  # a bare role word ("chair", "Advocate"): not a mention
                    return None, f"name form not from plan: {surface!r}"
        elif surface != ent["value"]:
            dv = _digits_of(ent["value"])
            if not (surface.lower() == ent["value"].lower() or (len(dv) >= 2 and _digits_of(surface) == dv)):
                return None, f"value changed: {key}"
        got.setdefault(key, []).append((s, e))

    taken = [False] * len(text)
    for spans in got.values():
        for s, e in spans:
            for i in range(s, e):
                taken[i] = True

    def free(s: int, e: int) -> bool:
        return not any(taken[s:e])

    def claim(key: str, s: int, e: int) -> None:
        got.setdefault(key, []).append((s, e))
        for i in range(s, e):
            taken[i] = True

    # missed names: full name, first name, surname (if no one else shares it), organisation name or its first word
    surnames = {}
    for e in persons:
        surnames.setdefault(e["name"].split()[-1], []).append(e["key"])
    forms = []
    for e in persons:
        first, last = e["name"].split()[0], e["name"].split()[-1]
        forms += [(e["name"], e["key"]), (first, e["key"])]
        if len(surnames[last]) == 1:
            forms.append((last, e["key"]))
    for e in p["entities"]:
        if e["type"] == "ORG":
            forms += [(e["name"], e["key"]), (e["name"].split()[0], e["key"])]
    for form, key in sorted(forms, key=lambda x: -len(x[0])):
        for m in re.finditer(rf"(?<![\w]){re.escape(form)}(?![\w])", text):
            if free(m.start(), m.end()):
                claim(key, m.start(), m.end())
    # missed he/she: unique gender -> that person; otherwise the reader decides
    pending = []
    for m in _PRONOUN.finditer(text):
        if not free(m.start(), m.end()):
            continue
        gender = "male" if m.group(1).lower() in ("he", "him", "his", "himself") else "female"
        cands = [e for e in persons if e["gender"] == gender and e["key"] in got]
        if len(cands) == 1:
            claim(cands[0]["key"], m.start(), m.end())
        elif cands:
            pending.append((m.start(), m.end()))
            for i in range(m.start(), m.end()):
                taken[i] = True
        else:
            return None, "pronoun with no matching person"

    # values planned as text (cities, countries, handles) the writer wrote again without a tag: tag them too
    for e in p["entities"]:
        if e["type"] in ("LOCATION", "SENSITIVE_ATTRIBUTE", "CONTACT", "SECRET", "ID") and e.get("value") and e["key"] in got:
            for m in re.finditer(rf"(?<![\w]){re.escape(e['value'])}(?![\w])", text):
                if free(m.start(), m.end()):
                    claim(e["key"], m.start(), m.end())
    if p["family"] in V3_FAMILIES:
        # known places and organisations, and times of day, the writer added on its own: they are private under the v3
        # policy, so they become entities (no owner) instead of untagged text the target would teach the model to leave
        extra: dict[str, str] = {}

        def add(kind: str, surface: str, **fields) -> str:
            k = extra.get((kind, surface.lower()))
            if not k:
                k = f"X{len(extra)}"
                extra[(kind, surface.lower())] = k
                by_key[k] = {"key": k, "type": kind, **fields}
            return k
        for g in GAZETTEER:
            for m in re.finditer(rf"(?<![\w]){re.escape(g)}(?![\w])", text):
                if free(m.start(), m.end()):
                    if g in COUNTRIES or g in STATES or g in WORLD_CITIES:
                        sub = "COUNTRY" if g in COUNTRIES else ("STATE" if g in STATES else "CITY")
                        k = add("LOCATION", g, subtype=sub, value=g, owner=None, role=None)
                    else:
                        k = add("ORG", g, role="organisation", name=g)
                    claim(k, m.start(), m.end())
        for m in re.finditer(r"\b\d{1,2}:\d{2}(?:\s?(?:AM|PM|am|pm|a\.m\.|p\.m\.))?|\b\d{1,2}\s?(?:am|pm|AM|PM|a\.m\.|p\.m\.)(?!\w)", text):
            if free(m.start(), m.end()):
                claim(add("DATE", m.group(0), subtype="TIME", value=m.group(0), owner=None, role=None), m.start(), m.end())
    bare = "".join(c if not taken[i] else " " for i, c in enumerate(text))
    for pat in _LEAKY:
        if pat.search(bare):
            return None, f"untagged value: {pat.pattern[:20]}"
    for e in p["entities"]:
        parts = re.findall(r"[\w']+", e.get("name", "")) if e["type"] == "PERSON" else e.get("name", "").split()[:1]
        for part in parts:  # organisation suffixes ("Bank", "Life") are ordinary words
            if len(part) > 2 and re.search(rf"\b{re.escape(part)}\b", bare):
                return None, f"untagged name part {part!r}"
    if not any(by_key[k]["type"] == "PERSON" for k in got):
        return None, "no person"
    for k in got:
        owner = by_key[k].get("owner")
        if owner and owner != R.UNKNOWN and owner not in got:
            return None, "owner never named"
    us = R.units(text)
    for spans in list(got.values()) + [pending]:
        for s, e in spans:
            if not any(a <= s and e <= b for a, b in us):
                return None, "mention crosses a unit boundary"

    # renumber keys in order of first appearance: PERSON_1, ORG_1, SALARY_1, ...
    order = sorted(got, key=lambda k: min(s for s, _ in got[k]))
    counts, ids = {}, {}
    for k in order:
        ent = by_key[k]
        base = ent["role"] if ent["type"] == "AMOUNT" and ent["role"] != "OTHER" else ent["type"]
        counts[base] = counts.get(base, 0) + 1
        ids[k] = f"{base}_{counts[base]}"
    entities = []
    for k in order:
        ent = by_key[k]
        item = {"id": ids[k], "type": ent["type"], "mentions": sorted(got[k])}
        if ent["type"] in ("PERSON", "ORG", "AMOUNT"):
            item["role"] = ent["role"]
        if ent.get("subtype"):
            item["subtype"] = ent["subtype"]
        if ent.get("owner"):
            item["owner"] = R.UNKNOWN if ent["owner"] == R.UNKNOWN else ids[ent["owner"]]
        if ent["type"] == "PERSON":
            item["gender"] = ent["gender"]
        entities.append(item)
    rels = [[ids[a], r, ids[b]] for a, r, b in p["relations"] if a in ids and b in ids]
    return {"uid": p["uid"], "family": p["family"], "doc_type": p["doc_type"], "text": text, "entities": entities,
            "relations": rels, "ambiguous": bool(p["ambiguous"]), "pending": pending}, ""


AMBIGUOUS_THINGS = [("bonus", "SALARY"), ("revised allowance", "SALARY"), ("reimbursement", "OTHER"),
                    ("salary advance", "LOAN"), ("one-time payment", "OTHER")]


def renumber(gold: dict) -> dict:
    """Re-mint ids in order of first appearance (after an insertion), updating owners and relations."""
    ents = sorted(gold["entities"], key=lambda e: min(s for s, _ in e["mentions"]))
    counts, ids = {}, {}
    for e in ents:
        base = e["role"] if e["type"] == "AMOUNT" and e.get("role") and e["role"] != "OTHER" else e["type"]
        counts[base] = counts.get(base, 0) + 1
        ids[e["id"]] = f"{base}_{counts[base]}"
    for e in ents:
        e["id"] = ids[e["id"]]
        if e.get("owner") and e["owner"] != R.UNKNOWN:
            e["owner"] = ids[e["owner"]]
    gold["entities"] = ents
    gold["relations"] = [[ids[a], r, ids[b]] for a, r, b in gold["relations"]]
    return gold


def add_ambiguity(gold: dict, rng: random.Random, us: bool) -> dict | None:
    """Insert one sentence about two people and a new amount: owner UNKNOWN by construction, or (as the
    contrast case) clearly one of them. Built in code because a writer asked to be ambiguous rarely is."""
    text = gold["text"]
    persons = [e for e in gold["entities"] if e["type"] == "PERSON"]
    firsts = {}
    for e in persons:
        names = [text[s:t] for s, t in e["mentions"] if not R.is_reference(text[s:t])]
        if names:
            firsts[e["id"]] = min(names, key=len).split()[-1] if min(names, key=len).split()[0].lower().rstrip(".") in \
                {"mr", "mrs", "ms", "dr", "prof"} else min(names, key=len).split()[0]
    cands = [e for e in persons if e["id"] in firsts]
    if len(cands) < 2:
        return None
    a, b = rng.sample(cands, 2)
    thing, role = rng.choice(AMBIGUOUS_THINGS)
    value = make_value(role if role != "OTHER" else "OTHER", rng, us, None)[0]
    same_gender = a.get("gender") == b.get("gender")
    clear = rng.random() < 0.4
    A, B = firsts[a["id"]], firsts[b["id"]]
    if clear:
        sent, owner = rng.choice([f"{A} and {B} both met the committee this week. {A}'s {thing} of {value} has been approved.",
                                  f"After the review with {B}, the {thing} of {value} for {A} was approved."]), a["id"]
    elif same_gender:
        pron = "His" if a.get("gender") == "male" else "Her"
        sent, owner = f"{A} and {B} both met the committee this week. {pron} {thing} of {value} has been approved.", R.UNKNOWN
    else:
        sent, owner = f"{A} and {B} were both reviewed; a {thing} of {value} was approved for one of them.", R.UNKNOWN
    paras = [m.start() for m in re.finditer(r"\n\n", text)]
    pos = paras[-1] if len(paras) >= 2 else len(text)
    insert = "\n\n" + sent
    shift = len(insert)
    for e in gold["entities"]:
        e["mentions"] = [(s + shift if s >= pos else s, t + shift if s >= pos else t) for s, t in e["mentions"]]
    text = text[:pos] + insert + text[pos:]
    base = pos + 2
    def at(sub: str, start: int = 0) -> tuple[int, int]:
        i = sent.index(sub, start)
        return base + i, base + i + len(sub)
    a_spans = [at(A)] + ([at(A, sent.index(A) + 1)] if sent.count(A) > 1 else [])
    next(e for e in gold["entities"] if e["id"] == a["id"])["mentions"] += a_spans
    next(e for e in gold["entities"] if e["id"] == b["id"])["mentions"].append(at(B))
    gold["entities"].append({"id": "NEW_1", "type": "AMOUNT", "role": role, "owner": owner, "mentions": [at(value)]})
    for e in gold["entities"]:
        e["mentions"] = sorted(e["mentions"])
    gold["text"] = text
    gold["ambiguous"] = owner == R.UNKNOWN
    gold["inserted"] = "unknown" if owner == R.UNKNOWN else "clear"
    if any(not any(x <= s and t <= y for x, y in R.units(text)) for e in gold["entities"] for s, t in e["mentions"]):
        return None
    return renumber(gold)


VERIFY_PROMPT = """Read this document carefully.
{doc}

People and organisations:
{people}

1. For each private value below, who does it belong to? Answer with a person or organisation id, or "UNKNOWN" if the
   text does not make it clear (don't guess), or "NONE" if it belongs to no one in particular.
{values}
2. For each reference below (unit number and text, in document order), which person or organisation does it refer to?
{refs}

Return JSON: {{"owners": {{"<value id>": "<id | UNKNOWN | NONE>", ...}}, "refs": ["<id>", ...]}}"""


def verify_messages(gold: dict) -> tuple[list[dict], list[str], list[tuple]]:
    """The reader's prompt, the value ids asked about, and the references in document order:
    (start, end, gold id or None for a pending pronoun the reader must resolve)."""
    text, us = gold["text"], R.units(gold["text"])
    people = [f"- {e['id']}: {text[e['mentions'][0][0]:e['mentions'][0][1]]}" for e in gold["entities"]
              if e["type"] in ("PERSON", "ORG")]
    vals = [e for e in gold["entities"] if e["type"] in R.OWNED_TYPES]
    values = [f"- {e['id']}: {text[e['mentions'][0][0]:e['mentions'][0][1]]}" for e in vals]
    refs = [(s, t, e["id"]) for e in gold["entities"] if e["type"] in ("PERSON", "ORG")
            for s, t in e["mentions"] if R.is_reference(text[s:t])]
    refs += [(s, t, None) for s, t in gold.get("pending", [])]
    refs.sort()
    unit = lambda s: next(i for i, (a, b) in enumerate(us, 1) if a <= s < b)
    ref_lines = [f"- [{unit(s)}] {text[s:t]}" for s, t, _ in refs]
    msg = VERIFY_PROMPT.format(doc=R.render_units(text, us), people="\n".join(people) or "- none",
                               values="\n".join(values) or "- none", refs="\n".join(ref_lines) or "- none")
    return [{"role": "user", "content": msg}], [e["id"] for e in vals], refs


def agrees(gold: dict, raw: str, value_ids: list[str], want_owners: list[str], refs: list[tuple]) -> tuple[bool, str]:
    """Check the reader against the plan; on success, adds the pending pronouns it resolved to gold."""
    data = _loads(raw)
    owners, answers = data.get("owners", {}), data.get("refs", [])
    ents = {e["id"]: e for e in gold["entities"]}
    for vid, want in zip(value_ids, want_owners):
        got = str(owners.get(vid, "")).upper()
        ent = ents.get(vid, {})
        if ent.get("type") == "LOCATION" or ent.get("subtype") in ("TIME", "EVENT"):
            # whose place or time it is is often genuinely loose ("Dubai" for the user or the trip): the reader decides
            if got in ents or got == R.UNKNOWN:
                ent["owner"] = got
            else:
                ent.pop("owner", None)
            continue
        if want == "NONE":
            continue  # unowned values (a meeting date): any answer is fine
        if got != want:
            return False, f"owner {vid}: plan {want}, reader {got}"
    if refs:
        if len(answers) != len(refs):
            return False, "reference count"
        known = [(str(a).upper(), r[2]) for a, r in zip(answers, refs) if r[2]]
        hits = sum(a == b for a, b in known)
        if hits < len(known) - (1 if len(known) >= 8 else 0):
            return False, f"references {hits}/{len(known)}"
        persons = {e["id"]: e for e in gold["entities"] if e["type"] == "PERSON"}
        for a, (s, t, gid) in zip(answers, refs):
            if gid:
                continue
            pid = str(a).upper()
            want_gender = "male" if gold["text"][s:t].lower() in ("he", "him", "his", "himself") else "female"
            if pid not in persons or persons[pid].get("gender") != want_gender:
                return False, "pending pronoun unresolved"
            persons[pid]["mentions"] = sorted(persons[pid]["mentions"] + [(s, t)])
    gold["pending"] = []
    return True, ""


class Meter:
    def __init__(self, model: str):
        self.lock, self.model = threading.Lock(), model
        self.tokens = {"prompt": 0, "cached": 0, "completion": 0}

    def add(self, usage: dict) -> None:
        with self.lock:
            self.tokens["prompt"] += usage.get("prompt_tokens", 0)
            self.tokens["cached"] += usage.get("prompt_cache_hit_tokens", 0)
            self.tokens["completion"] += usage.get("completion_tokens", 0)

    def usd(self) -> float:
        p_in, p_cached, p_out = TOKEN_PRICES[self.model]
        t = self.tokens
        return ((t["prompt"] - t["cached"]) * p_in + t["cached"] * p_cached + t["completion"] * p_out) / 1e6


def build(out: Path, n: int, seed: int, model: str, workers: int, budget_usd: float, ambiguity: float = 0.25,
          only: set[str] | None = None) -> dict:
    rng = random.Random(seed)
    if only:
        fams, weights = sorted(only), [1.0] * len(only)
    else:
        fams = [f for f in FAMILIES if f not in CHALLENGE_FAMILIES and f not in V3_FAMILIES] + ["generic"]
        weights = [1.6 if f in V2_FAMILIES else 1.0 for f in fams[:-1]] + [0.3]
    plans = [plan(random.Random(rng.random()), rng.choices(fams, weights)[0], f"er-{seed}-{i:05d}") for i in range(n)]
    # thinking off: with reasoning on, Flash spent the whole token budget thinking and wrote nothing
    no_think = {"thinking": {"type": "disabled"}}
    writer = DeepSeekBackend(model, max_tokens=4500, extra=no_think)
    writer.json_mode = False
    reader = DeepSeekBackend(model, max_tokens=1500, extra=no_think)
    meter = Meter(model)
    out.mkdir(parents=True, exist_ok=True)
    kept_f, drop_f = open(out / "docs.jsonl", "a"), open(out / "dropped.jsonl", "a")
    done = {json.loads(l)["uid"] for l in (out / "docs.jsonl").read_text().splitlines() if l.strip()} | \
           {json.loads(l)["uid"] for l in (out / "dropped.jsonl").read_text().splitlines() if l.strip()}
    lock, stats = threading.Lock(), {"kept": 0, "dropped": 0, "reasons": {}}

    def work(p):
        if p["uid"] in done or meter.usd() > budget_usd:
            return
        try:
            raw, u = writer._call(writer_messages(p))
            meter.add(u)
            gold, why = check(p, raw)
            if gold and gold["entities"] and random.Random(p["uid"]).random() < ambiguity:
                gold = add_ambiguity(gold, random.Random(p["uid"] + "a"), p.get("us", False)) or gold
            if gold and gold["entities"]:
                msgs, vids, refs = verify_messages(gold)
                want = [next(e.get("owner") or "NONE" for e in gold["entities"] if e["id"] == v) for v in vids]
                vraw, vu = reader._call(msgs)
                meter.add(vu)
                ok, why = agrees(gold, vraw, vids, want, refs)
                if not ok:
                    gold = None
        except (BackendError, ContractError, ValueError, KeyError, StopIteration) as exc:
            gold, why = None, f"error: {exc!s:.80}"
        with lock:
            if gold:
                kept_f.write(json.dumps(gold, ensure_ascii=False) + "\n")
                kept_f.flush()
                stats["kept"] += 1
            else:
                drop_f.write(json.dumps({"uid": p["uid"], "family": p["family"], "why": why}) + "\n")
                drop_f.flush()
                stats["dropped"] += 1
                r = why.split(":")[0]
                stats["reasons"][r] = stats["reasons"].get(r, 0) + 1
            if (stats["kept"] + stats["dropped"]) % 50 == 0:
                print(f"{time.strftime('%H:%M:%S')} kept {stats['kept']} dropped {stats['dropped']} "
                      f"${meter.usd():.2f} {dict(sorted(stats['reasons'].items(), key=lambda x: -x[1])[:5])}", flush=True)

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(work, plans))
    stats["usd"], stats["tokens"] = round(meter.usd(), 3), meter.tokens
    return stats


def split(src: Path, out: Path, seed: int, val: int, test: int, challenge: int) -> dict:
    """Split by document (every document has its own fictional people), holding two families out entirely."""
    docs = [json.loads(l) for l in src.read_text().splitlines() if l.strip()]
    rng = random.Random(seed)
    rng.shuffle(docs)
    chal = [d for d in docs if d["family"] in CHALLENGE_FAMILIES][:challenge]
    rest = [d for d in docs if d["family"] not in CHALLENGE_FAMILIES]
    parts = {"test": rest[:test], "val": rest[test:test + val], "train": rest[test + val:], "challenge": chal}
    out.mkdir(parents=True, exist_ok=True)
    for name, ds in parts.items():
        (out / f"{name}.docs.jsonl").write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in ds))
    for name in ("train", "val"):
        rows = [{"messages": R.messages(d["text"]) + [{"role": "assistant", "content": R.target_json(d["text"], d)}]}
                for d in parts[name]]
        (out / f"{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    stats = {name: len(ds) for name, ds in parts.items()}
    stats["families"] = {}
    for d in docs:
        stats["families"][d["family"]] = stats["families"].get(d["family"], 0) + 1
    (out / "stats.json").write_text(json.dumps(stats, indent=1))
    return stats


def split2(v1: Path, src: Path, out: Path) -> dict:
    """v2 data: v1 train plus the new documents for training; v1 val, test and challenge unchanged, so results
    compare directly with v1. Rows have no worked example in the prompt (the fine-tune doesn't need one)."""
    load = lambda f: [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    new = [d for d in load(src) if d["family"] not in CHALLENGE_FAMILIES]
    parts = {"train": load(v1 / "train.docs.jsonl") + new, "val": load(v1 / "val.docs.jsonl"),
             "test": load(v1 / "test.docs.jsonl"), "challenge": load(v1 / "challenge.docs.jsonl")}
    random.Random(5).shuffle(parts["train"])
    out.mkdir(parents=True, exist_ok=True)
    for name, ds in parts.items():
        (out / f"{name}.docs.jsonl").write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in ds))
    for name in ("train", "val"):
        rows = [{"messages": R.messages(d["text"], example=False) + [{"role": "assistant", "content": R.target_json(d["text"], d)}]}
                for d in parts[name]]
        (out / f"{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    stats = {name: len(ds) for name, ds in parts.items()}
    stats["new_documents"] = len(new)
    stats["inserted"] = {k: sum(d.get("inserted") == k for d in parts["train"]) for k in ("unknown", "clear")}
    stats["families"] = {}
    for d in parts["train"]:
        stats["families"][d["family"]] = stats["families"].get(d["family"], 0) + 1
    (out / "stats.json").write_text(json.dumps(stats, indent=1))
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m muse_shield.resolution_data")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--out", type=Path, default=Path("runs/er/gen"))
    b.add_argument("--n", type=int, default=2000)
    b.add_argument("--seed", type=int, default=7)
    b.add_argument("--model", default="deepseek-flash")
    b.add_argument("--workers", type=int, default=24)
    b.add_argument("--budget-usd", type=float, default=4.5)
    b.add_argument("--ambiguity", type=float, default=0.25, help="share of documents that get a code-built ownership sentence")
    b.add_argument("--only", default="", help="comma-separated families (v3: --only v3 for the eight v3 families)")
    s2 = sub.add_parser("split2", help="v2: v1 train + new documents; v1 val/test/challenge unchanged")
    s2.add_argument("--v1", type=Path, default=Path("runs/er/v1"))
    s2.add_argument("--src", type=Path, default=Path("runs/er/gen2/docs.jsonl"))
    s2.add_argument("--out", type=Path, default=Path("runs/er/v2"))
    s = sub.add_parser("split")
    s.add_argument("--src", type=Path, default=Path("runs/er/gen/docs.jsonl"))
    s.add_argument("--out", type=Path, default=Path("runs/er/v1"))
    s.add_argument("--seed", type=int, default=11)
    s.add_argument("--val", type=int, default=60)
    s.add_argument("--test", type=int, default=150)
    s.add_argument("--challenge", type=int, default=80)
    a = ap.parse_args(argv)
    if a.cmd == "build":
        only = V3_FAMILIES if a.only == "v3" else ({f for f in a.only.split(",") if f} or None)
        print(json.dumps(build(a.out, a.n, a.seed, a.model, a.workers, a.budget_usd, a.ambiguity, only), indent=1))
    elif a.cmd == "split":
        print(json.dumps(split(a.src, a.out, a.seed, a.val, a.test, a.challenge), indent=1))
    else:
        print(json.dumps(split2(a.v1, a.src, a.out), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
