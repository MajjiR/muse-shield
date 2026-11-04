# Sector test error analysis

951 paragraphs, 2945 gold entities, 511 gold context passages.

## Entity errors (count)

| category | base | v1c | v2full | spark |
|---|---|---|---|---|
| split | 0 | 490 | 1 | 0 |
| boundary | 88 | 16 | 10 | 11 |
| type | 2 | 12 | 2 | 0 |
| miss | 74 | 119 | 26 | 20 |
| extra | 181 | 467 | 71 | 39 |
| invalid paragraphs | 49 | 0 | 0 | 0 |

## Entity errors by type (miss+split+boundary+type / extra)

| type | base | v1c | v2full | spark |
|---|---|---|---|---|
| ADDRESS | 1 / 0 | 1 / 0 | 0 / 0 | 0 / 0 |
| AMOUNT | 4 / 2 | 32 / 0 | 0 / 0 | 0 / 0 |
| CONTACT | 2 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| DATE | 6 / 84 | 3 / 108 | 5 / 65 | 13 / 7 |
| ID | 22 / 1 | 0 / 0 | 0 / 0 | 0 / 0 |
| LOCATION | 2 / 1 | 4 / 1 | 2 / 1 | 2 / 18 |
| ORG | 6 / 63 | 10 / 0 | 2 / 0 | 0 / 0 |
| PERSON | 66 / 21 | 524 / 0 | 6 / 0 | 7 / 0 |
| PROJECT | 0 / 4 | 0 / 0 | 0 / 0 | 0 / 0 |
| SENSITIVE_ATTRIBUTE | 55 / 5 | 63 / 358 | 24 / 5 | 9 / 14 |

## Contexts

| | base | v1c | v2full | spark |
|---|---|---|---|---|
| kind ok | 173 | 9 | 308 | 476 |
| wrong kind | 58 | 8 | 38 | 14 |
| missed | 214 | 494 | 165 | 21 |
| extra | 51 | 1 | 52 | 160 |
| missed DEAL | 32 | 126 | 31 | 3 |
| missed DECISION | 43 | 78 | 47 | 4 |
| missed HR | 118 | 227 | 55 | 10 |
| missed NEGOTIATION | 7 | 30 | 5 | 0 |
| missed PLAN | 13 | 32 | 26 | 4 |
| missed PROJECT | 1 | 1 | 1 | 0 |
| amount role wrong / ok | 44 / 117 | 48 / 115 | 58 / 137 | 22 / 173 |

## base: most frequent extra outputs

ORG:'HR'×13, ORG:'granite.in'×3, ORG:'E-commerce Support'×3, PERSON:'Admin Executive'×3, DATE:'22 March 2026'×2, DATE:'15 March 2027'×2, DATE:'7 November 2026'×2, DATE:'tomorrow morning'×2, ORG:'Legal Counsel'×2, DATE:'1 September 2026'×2, DATE:'22 January 2027'×2, DATE:'26 January 2027'×2, ORG:'Finance'×2, ORG:'Healthcare division'×2, PERSON:'Consultant Cardiologist'×2, DATE:'11 November 2026'×2, ORG:'Customer Support'×2, ORG:'customer support'×2, PERSON:'Support Lead'×2, ORG:'Human Resources'×2
- **boundary**: ID gold 'PJMPQ7981T' got 'PAN PJMPQ7981T'; ID gold '3156 1093 1034' got 'Aadhaar 3156 1093 1034'; ID gold 'MTAPZ5461W' got 'PAN MTAPZ5461W'; ID gold '5453 5457 3578' got 'Aadhaar 5453 5457 3578'; ORG gold 'Lumina Motors' got 'Lumina Motors Finance Committee'; AMOUNT gold '$178,321' got 'outstanding term facility of $178,321'; ID gold '5706 5503 5282' got 'Aadhaar 5706 5503 5282'; ID gold 'TNRPU5477E' got 'PAN TNRPU5477E'
- **miss**: AMOUNT '$784,937'; ORG 'Maple Pharma'; ORG 'Indus Ventures'; DATE '17 May 2027'; AMOUNT '$39,883'; PERSON 'LM'; PERSON 'IO'; PERSON 'Arnav'
- **type**: 8136 3615 2229: gold ID, got CONTACT; Hill Road: gold ADDRESS, got LOCATION
- **ctx_kind**: gold PLAN got DEAL; gold HR got PLAN; gold DECISION got DEAL; gold HR got PLAN; gold HR got DEAL; gold DECISION got PLAN; gold DECISION got DEAL; gold NEGOTIATION got DEAL
- **role**: ₹18 lakh: gold FEE, got BUDGET; ₹74,440: gold LOAN, got OTHER; $8,421: gold OTHER, got FEE; ₹50,598: gold OTHER, got FEE; $528,448: gold FEE, got OTHER; $274,877: gold FEE, got OTHER; ₹54 lakh: gold SALARY, got OTHER; ₹28,987: gold BUDGET, got OTHER

## v1c: most frequent extra outputs

SENSITIVE_ATTRIBUTE:'General Counsel'×14, SENSITIVE_ATTRIBUTE:'HR Manager'×9, SENSITIVE_ATTRIBUTE:'Customer Support Associate'×9, SENSITIVE_ATTRIBUTE:'Chief Financial Officer'×7, SENSITIVE_ATTRIBUTE:'Finance Lead'×7, SENSITIVE_ATTRIBUTE:'General Practitioner'×7, SENSITIVE_ATTRIBUTE:'Senior Support Associate'×7, SENSITIVE_ATTRIBUTE:'Team Lead'×7, SENSITIVE_ATTRIBUTE:'VP Corporate Development'×6, SENSITIVE_ATTRIBUTE:'Senior Associate'×5, SENSITIVE_ATTRIBUTE:'Legal Counsel'×5, SENSITIVE_ATTRIBUTE:'Senior Consultant'×5, SENSITIVE_ATTRIBUTE:'Support Lead'×5, SENSITIVE_ATTRIBUTE:'Executive Assistant'×5, SENSITIVE_ATTRIBUTE:'Admin Executive'×5, SENSITIVE_ATTRIBUTE:'Senior Care Coordinator'×4, SENSITIVE_ATTRIBUTE:'Consultant Pathologist'×4, SENSITIVE_ATTRIBUTE:'Support Associate'×4, SENSITIVE_ATTRIBUTE:'Senior Support Specialist'×4, SENSITIVE_ATTRIBUTE:'VP Finance'×3
- **split**: 'Leila Ramaswamy' -> ['Leila', 'Ramaswamy']; 'Gaurav Ansari' -> ['Gaurav', 'Ansari']; 'Bhavna Iyengar' -> ['Bhavna', 'Iyengar']; 'Aarav Okonkwo' -> ['Aarav', 'Okonkwo']; 'Shreya Narayanan' -> ['Shreya', 'Narayanan']; 'Aarav Moreno' -> ['Aarav', 'Moreno']; 'Mihir Chakraborty' -> ['Mihir', 'Chakraborty']; 'Esther Pillai' -> ['Esther', 'Pillai']
- **boundary**: PERSON gold 'Pranav' got 'Pranav Mukherjee'; PERSON gold 'Imran' got 'Imran Dutta'; PERSON gold 'Ms. Clara Narayanan' got 'Clara Narayanan'; AMOUNT gold '₹36 lakh' got '₹36 lakh annually'; ORG gold 'Coral Retail' got 'Coral Retail healthcare support unit'; PERSON gold 'Gaurav' got 'Gaurav Mehra'; PERSON gold 'Kabir' got 'Kabir Okonkwo'; PERSON gold 'Nandini' got 'Nandini Rao'
- **miss**: AMOUNT '$708,331'; AMOUNT '$784,937'; ORG 'Lumina Motors'; AMOUNT '₹6,313'; AMOUNT '$518,903'; ORG 'Coral Retail'; AMOUNT '₹11,564'; AMOUNT '$475,268'
- **type**: WL: gold PERSON, got CONTACT; RV: gold PERSON, got CONTACT; LM: gold PERSON, got SENSITIVE_ATTRIBUTE; IO: gold PERSON, got SENSITIVE_ATTRIBUTE; Fatima Iyengar: gold PERSON, got SENSITIVE_ATTRIBUTE; Amara Saxena: gold PERSON, got SENSITIVE_ATTRIBUTE; Hill Road: gold ADDRESS, got LOCATION; Lavanya Tanaka: gold PERSON, got SENSITIVE_ATTRIBUTE
- **ctx_kind**: gold HR got DECISION; gold DEAL got DECISION; gold HR got DEAL; gold NEGOTIATION got DECISION; gold HR got DECISION; gold DEAL got NEGOTIATION; gold DEAL got DECISION; gold DEAL got DECISION
- **role**: $388,264: gold FEE, got OTHER; ₹74,440: gold LOAN, got OTHER; ₹5 lakh: gold OTHER, got SALARY; $277,442: gold OTHER, got DEAL_VALUE; $73,629: gold LOAN, got DEAL_VALUE; ₹11,965: gold FEE, got OTHER; $8,421: gold OTHER, got FEE; ₹94,944: gold FEE, got BUDGET

## v2full: most frequent extra outputs

DATE:'22 January 2027'×2, DATE:'26 January 2027'×2, SENSITIVE_ATTRIBUTE:'vegetarian'×2, DATE:'7 July 2025'×1, DATE:'19 May 2025'×1, DATE:'16 January 2025'×1, DATE:'26 March 2025'×1, DATE:'19 July 2026'×1, DATE:'16 September 2025'×1, DATE:'18 March 2026'×1, DATE:'7 January 2026'×1, DATE:'13 September 2026'×1, DATE:'3 January 2027'×1, DATE:'17 November 2027'×1, DATE:'16 May 2025'×1, DATE:'18 September 2027'×1, DATE:'20 March 2026'×1, DATE:'6 November 2026'×1, DATE:'19 November 2025'×1, DATE:'4 November 2027'×1
- **split**: 'Sister Clara' -> ['Clara']
- **boundary**: SENSITIVE_ATTRIBUTE gold 'cholesterol showing a mild borderline elevation' got 'mild borderline elevation'; SENSITIVE_ATTRIBUTE gold 'liver and kidney function within normal limits' got 'liver and kidney function within normal limits and cholesterol only mildly above usual'; SENSITIVE_ATTRIBUTE gold 'cholesterol only mildly above usual' got 'liver and kidney function within normal limits and cholesterol only mildly above usual'; PERSON gold 'Dr. Imran Ramaswamy' got 'Imran Ramaswamy'; SENSITIVE_ATTRIBUTE gold 'resolving viral illness' got 'viral illness'; SENSITIVE_ATTRIBUTE gold 'breathing worsens' got 'breathing'; PERSON gold 'Mr. Vivek Weber' got 'Vivek Weber'; SENSITIVE_ATTRIBUTE gold 'fatigue' got 'work-related fatigue'
- **miss**: DATE '14 July 2026'; SENSITIVE_ATTRIBUTE 'fitness clearance'; SENSITIVE_ATTRIBUTE 'medical leave'; SENSITIVE_ATTRIBUTE 'advised rest at home for a few days followed by light duties, with fitness to resume full duties subject to review'; DATE 'May'; SENSITIVE_ATTRIBUTE 'approved medical leave'; SENSITIVE_ATTRIBUTE 'inpatient treatment'; SENSITIVE_ATTRIBUTE 'medical leave'
- **type**: LM: gold PERSON, got ORG; IO: gold PERSON, got ORG
- **ctx_kind**: gold HR got DEAL; gold HR got DEAL; gold DECISION got DEAL; gold DECISION got DEAL; gold DECISION got DEAL; gold DECISION got DEAL; gold DECISION got HR; gold NEGOTIATION got DEAL
- **role**: ₹93 lakh: gold FEE, got BUDGET; $388,264: gold FEE, got BUDGET; ₹18 lakh: gold FEE, got BUDGET; ₹72,774: gold OTHER, got BUDGET; ₹67,908: gold DEAL_VALUE, got OTHER; ₹5 lakh: gold OTHER, got SALARY; $277,442: gold OTHER, got DEAL_VALUE; $943,112: gold OTHER, got DEAL_VALUE

## spark: most frequent extra outputs

LOCATION:'Bengaluru'×5, LOCATION:'Kolkata'×3, LOCATION:'Hyderabad'×3, LOCATION:'Ahmedabad'×2, DATE:'16 September 2025'×1, DATE:'3 January 2027'×1, DATE:'19 November 2025'×1, LOCATION:'Chennai'×1, SENSITIVE_ATTRIBUTE:'occupational health follow-up appointment'×1, SENSITIVE_ATTRIBUTE:'occupational health case'×1, LOCATION:'Kochi'×1, SENSITIVE_ATTRIBUTE:'fatigue'×1, LOCATION:'Lucknow'×1, DATE:'11 November 2025'×1, SENSITIVE_ATTRIBUTE:'low dose maintenance therapy'×1, SENSITIVE_ATTRIBUTE:'recent procedure'×1, SENSITIVE_ATTRIBUTE:'medical leave'×1, SENSITIVE_ATTRIBUTE:'urgent cardiology specialist review'×1, SENSITIVE_ATTRIBUTE:'sick leave'×1, SENSITIVE_ATTRIBUTE:'complete blood count and kidney function are within expected range'×1
- **boundary**: SENSITIVE_ATTRIBUTE gold 'advised rest at home for a few days followed by light duties, with fitness to resume full duties subject to review' got 'has been advised rest at home for a few days followed by light duties, with fitness to resume full duties subject to review'; PERSON gold 'Dr. Imran Ramaswamy' got 'Imran Ramaswamy'; PERSON gold 'Shreya Kulkarni' got 'Dr. Shreya Kulkarni'; PERSON gold 'Shreya Mehra' got 'Ms. Shreya Mehra'; PERSON gold 'Aarav D'Souza' got 'Dr. Aarav D'Souza'; PERSON gold 'Rukmini D'Souza' got 'Dr. Rukmini D'Souza'; DATE gold '13 March 2027' got '13 March 2027 in the morning'; PERSON gold 'Yusuf Ansari' got 'Dr. Yusuf Ansari'
- **miss**: DATE '17 May 2027'; DATE '28 July 2025'; DATE '18 March 2025'; DATE '25 July 2025'; SENSITIVE_ATTRIBUTE 'medical leave'; SENSITIVE_ATTRIBUTE 'inpatient treatment'; SENSITIVE_ATTRIBUTE 'his condition'; LOCATION 'Kolkata'
- **ctx_kind**: gold PLAN got DEAL; gold DEAL got DECISION; gold DECISION got PLAN; gold DECISION got DEAL; gold HR got DEAL; gold DEAL got PLAN; gold DECISION got DEAL; gold PLAN got DEAL
- **role**: ₹5 lakh: gold OTHER, got SALARY; $277,442: gold OTHER, got FEE; $943,112: gold OTHER, got DEAL_VALUE; $752,656: gold OTHER, got DEAL_VALUE; $8,421: gold OTHER, got FEE; ₹32,831: gold OTHER, got DEAL_VALUE; ₹50,598: gold OTHER, got FEE; ₹14 lakh: gold OTHER, got DEAL_VALUE
