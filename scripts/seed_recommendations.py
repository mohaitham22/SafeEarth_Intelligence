"""
scripts/seed_recommendations.py — seed the recommendations table with fallback rows
for all 8 disaster types × 4 severity levels × 6 items each (192 rows total).

Run from project root:
    py -3.12 scripts/seed_recommendations.py

Idempotent — skips any row whose (disaster_type, severity_level, title) already exists.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import select

from database import AsyncSessionLocal
from models.enums import RecommendationCategory as RC, SeverityLevel as SL
from models.recommendation import Recommendation

# ── category shortcuts ────────────────────────────────────────────────────────
E = RC.evacuation
K = RC.kit
S = RC.shelter
M = RC.medical
C = RC.contact

# ── seed data: {disaster_type: {severity_str: [6-item list]}} ─────────────────
# Each item: (category, title, body)
# Pattern: 2 evacuation + 1 kit + 1 shelter + 1 medical + 1 contact per bucket
SEED: dict[str, dict[str, list[tuple[RC, str, str]]]] = {

    # ── FLOOD ─────────────────────────────────────────────────────────────────
    "Flood": {
        "Low": [
            (E, "Know your flood risk zone",
             "Check your property's flood-risk classification on national flood maps and identify which local roads become impassable during heavy rain."),
            (E, "Plan two evacuation routes",
             "Agree on two routes out of your neighbourhood that avoid low-lying bridges. Walk them in advance so the path is automatic in an emergency."),
            (K, "Assemble a basic flood kit",
             "Store 3 days of water (4 L/person/day), non-perishable food, torch, batteries, copies of IDs, and first aid in a waterproof bag."),
            (S, "Note upper-floor refuges",
             "Identify the highest accessible floor in your home in case rising water prevents evacuation."),
            (M, "Stockpile medications early",
             "Keep at least 7 days of prescription medications in a sealed, waterproof container stored above ground level."),
            (C, "Save emergency numbers offline",
             "Store local emergency services, the national flood hotline, and two family contacts offline on your phone in case you lose signal."),
        ],
        "Medium": [
            (E, "Identify two evacuation routes",
             "Know two routes out of your neighbourhood that avoid low-lying bridges."),
            (E, "Move vehicles to high ground",
             "Park vehicles uphill or in covered structures before rising water cuts off access."),
            (K, "Prepare a basic emergency kit",
             "Pack 3 days of water, food, torch, batteries, first aid, and copies of IDs."),
            (S, "Identify upper-floor refuge",
             "Plan to move to upper floors if water enters the ground floor."),
            (M, "Stock essential medications",
             "Keep at least 7 days of prescription meds in a waterproof bag."),
            (C, "Save emergency contact numbers",
             "Store local emergency services and Red Cross numbers offline on your phone."),
        ],
        "High": [
            (E, "Pre-identify your evacuation route",
             "Know two routes that avoid low-lying bridges and flood zones. Share the plan with all family members before conditions deteriorate."),
            (E, "Move to higher ground immediately",
             "If a flash flood warning is issued, evacuate to higher ground without delay. Do not drive through flooded roads — turn around, don't drown."),
            (K, "Prepare a 72-hour go-bag",
             "Stock 4 litres of water per person per day, non-perishable food, torch, medications, copies of IDs, and a portable radio."),
            (S, "Seek upper floors if trapped",
             "If you cannot evacuate, move to the highest floor and signal rescuers from a window. Do not enter the attic if it has no exit."),
            (M, "Avoid floodwater contact",
             "Floodwater carries sewage, chemicals, and pathogens. Wash all exposed skin with soap and clean water; seek care for any open wound."),
            (C, "Call local emergency services",
             "Notify your emergency number and Red Cross. Check in with family by text to avoid network congestion."),
        ],
        "Critical": [
            (E, "Evacuate immediately if ordered",
             "Follow official evacuation orders without delay. Do not wait to gather belongings — your life is the priority."),
            (E, "Never drive through floodwater",
             "15 cm of fast-moving water can knock an adult down; 30 cm can sweep a car off the road. Turn around, don't drown."),
            (K, "Grab your go-bag only",
             "Take only your pre-packed kit. Do not waste time collecting extra items — every second counts."),
            (S, "Top floor and signal rescuers",
             "If trapped, go to the highest floor, wave a bright cloth from a window. Never enter a sealed attic — you could become trapped if water continues rising."),
            (M, "Treat all floodwater as toxic",
             "Wash every exposed area immediately with soap and clean water. Floodwater carries sewage and pathogens — seek medical care for any wound."),
            (C, "Activate your emergency plan now",
             "Call emergency services, give your exact location, and send text messages to preserve network capacity for rescuers."),
        ],
    },

    # ── STORM ─────────────────────────────────────────────────────────────────
    "Storm": {
        "Low": [
            (E, "Know your storm evacuation zone",
             "Check if your area is in a designated storm surge or evacuation zone and learn the nearest official shelter location."),
            (E, "Plan your indoor shelter room",
             "Identify the strongest interior room in your home away from windows — an interior hallway or bathroom on the lowest floor."),
            (K, "Build a storm emergency kit",
             "Store 3 days of water, food, a battery-powered radio, torch, first aid, and important documents in a waterproof bag."),
            (S, "Identify window-free interior rooms",
             "Note which rooms in your home have no exterior windows — these are your safest shelter spots during high winds."),
            (M, "Keep medications accessible",
             "Store 7 days of prescription medications and basic first aid in a portable waterproof container."),
            (C, "Register for emergency alerts",
             "Sign up for your local meteorological agency's text or email storm warnings. Early notice gives you critical extra minutes."),
        ],
        "Medium": [
            (E, "Secure outdoor items now",
             "Move or tie down garden furniture, rubbish bins, and any loose outdoor objects before winds arrive — they become dangerous projectiles."),
            (E, "Decide: evacuate or shelter in place",
             "Follow official guidance for your zone. If you plan to drive, keep your tank at least half full at all times during storm season."),
            (K, "Charge all devices and get cash",
             "Fully charge phones and portable batteries. Withdraw cash for 3 days — ATMs may go offline after the storm."),
            (S, "Stay away from all windows",
             "During high winds, stay in an interior room away from all windows and exterior walls. Do not open windows to equalise pressure."),
            (M, "Fill prescriptions before the storm",
             "Collect at least 10 days of prescription medications in advance — pharmacies may close for several days after a major storm."),
            (C, "Inform a contact outside the area",
             "Tell someone outside your region your address and storm plan so they can report your status if you lose communications."),
        ],
        "High": [
            (E, "Evacuate coastal and low-lying areas",
             "If you are in a storm surge zone or mobile home, evacuate immediately when warned — storm surge is the leading cause of storm fatalities."),
            (E, "Leave early before roads close",
             "Evacuate well ahead of the storm — roads become gridlocked and dangerous once high winds arrive. Use official evacuation routes only."),
            (K, "Finalise your 72-hour emergency kit",
             "Ensure water, food, medications, documents, cash, and a battery radio are packed. Keep the bag at the door ready to grab."),
            (S, "Move to your designated safe room",
             "Shelter in the strongest interior room, away from all windows. Cover yourself with a mattress or blankets if winds intensify."),
            (M, "Prepare for potential power outage",
             "If you use electrical medical equipment, arrange backup power now and contact your power company's medical priority register."),
            (C, "Confirm your family reunion plan",
             "Contact all family members, confirm shelter locations, and establish a check-in schedule every 2 hours during the storm."),
        ],
        "Critical": [
            (E, "Take shelter immediately",
             "If outdoors, get inside a solid building immediately. Abandon your vehicle if it is threatened by flooding or falling trees."),
            (E, "Stay away from storm surge zones",
             "Do not attempt to drive or walk through surge water — it can be deeper, faster, and more contaminated than it appears."),
            (K, "Access your emergency kit now",
             "Your kit should already be packed. Access medications, water, and torch immediately — do not leave the shelter for supplies."),
            (S, "Go to lowest interior floor for wind",
             "For extreme winds or tornado: go to the lowest floor interior room, crouch below window level, and cover your head with your arms."),
            (M, "Treat injuries with your kit",
             "Do not go outside for medical help unless the situation is life-threatening. Apply first aid from your kit and wait for conditions to improve."),
            (C, "Send your location to emergency services",
             "If injured or trapped, text your GPS coordinates to emergency services. Text uses less network bandwidth than a voice call."),
        ],
    },

    # ── EARTHQUAKE ────────────────────────────────────────────────────────────
    "Earthquake": {
        "Low": [
            (E, "Identify safe spots in every room",
             "For each room, identify the safest position: under a sturdy table or against an interior wall away from windows and heavy furniture."),
            (E, "Walk your post-quake exit route",
             "Know the safest exit from each room and the quickest open-area route away from your building. Walk it once so it is automatic in an emergency."),
            (K, "Prepare a 72-hour earthquake kit",
             "Store water (4 L/person/day), canned food, a manual can opener, torch, first aid, copies of IDs, and sturdy shoes in a waterproof bag."),
            (S, "Secure heavy furniture to walls",
             "Strap bookcases, water heaters, and heavy appliances to wall studs. This significantly reduces injury from toppling objects during shaking."),
            (M, "Keep a first aid kit accessible",
             "Store a well-stocked first aid kit in an easy-to-reach location — earthquake injuries are often lacerations and fractures requiring immediate care."),
            (C, "Designate an out-of-area contact",
             "Choose a family contact outside your region. After an earthquake, local lines are often overloaded but long-distance calls may get through."),
        ],
        "Medium": [
            (E, "Practice Drop, Cover, Hold On",
             "Practice the Drop-Cover-Hold On technique with your household. Get under a sturdy table, cover your neck, and hold on until shaking stops."),
            (E, "Know post-quake exit routes",
             "After shaking stops, check exits for damage before using stairs. Never use lifts. Use pre-agreed meeting points outside and away from buildings."),
            (K, "Check and refresh your kit",
             "Rotate water and food every 6 months. Ensure your kit includes a whistle, dust mask, work gloves, and a manual can opener."),
            (S, "Know where your gas shut-off valve is",
             "Locate your gas shut-off valve and learn how to use it. Gas leaks after an earthquake are a leading cause of post-quake fires."),
            (M, "Learn crush injury first aid",
             "Take a basic first aid course covering compression bandages and treating shock — crush injuries are common in earthquake collapses."),
            (C, "Use texts, not calls, after shaking",
             "Text messages use far less network capacity than voice calls. Send a brief status message to your family contact immediately after the shaking stops."),
        ],
        "High": [
            (E, "Drop, Cover, Hold On immediately",
             "The moment shaking begins: DROP to hands and knees, take COVER under a sturdy table or against an interior wall, and HOLD ON until the shaking fully stops."),
            (E, "Exit carefully after shaking stops",
             "Wait until shaking fully stops. Check the exit for debris before opening a door. Expect aftershocks — stay away from damaged structures at all times."),
            (K, "Access your emergency kit",
             "Retrieve your kit immediately after evacuating. Prioritise water, medications, and a torch. Do not re-enter damaged buildings to retrieve supplies."),
            (S, "Stay away from damaged structures",
             "Aftershocks can collapse already-weakened buildings. Do not re-enter your home until it has been inspected and declared safe by authorities."),
            (M, "Check for gas leaks before using anything",
             "Do not use open flames or any switches if you smell gas. Open windows, leave the building, and call the gas company from outside."),
            (C, "Register yourself as safe",
             "Use national disaster registries or social media check-in features to mark yourself safe — this reduces the burden on emergency services."),
        ],
        "Critical": [
            (E, "Drop, Cover, Hold On — now",
             "Immediately drop to the floor, take cover under a sturdy table or desk, and hold on. If no table is nearby, get against an interior wall and protect your head and neck."),
            (E, "Do not run outside during shaking",
             "Most injuries occur when people run outside. Stay where you are until the shaking fully stops, then exit calmly using stairs only — never lifts."),
            (K, "Grab essentials and exit the building",
             "Take only your pre-packed kit. If the building is compromised, every second inside increases risk from aftershocks. Water and medications are the priority."),
            (S, "Evacuate to open ground away from buildings",
             "After exiting, move to open ground away from buildings, power lines, and trees. Aftershocks can bring down damaged structures without warning."),
            (M, "Do not move spinal injury victims",
             "If someone may have a neck or back injury, do not move them unless there is an immediate life threat. Call emergency services and keep them still and warm."),
            (C, "Call for help only when clear of danger",
             "Once in a safe open area, call emergency services. Give your exact location, the number of injured, and the nature of injuries. Then text family."),
        ],
    },

    # ── WILDFIRE ──────────────────────────────────────────────────────────────
    "Wildfire": {
        "Low": [
            (E, "Create a wildfire evacuation plan",
             "Map two exit routes from your property. Know which direction wildfires typically travel in your area and which road leads away from the prevailing wind."),
            (E, "Register for fire evacuation alerts",
             "Sign up for your local fire authority's emergency alert system. Early warnings give you 20–30 extra minutes to safely evacuate."),
            (K, "Prepare a wildfire go-bag",
             "Pack water, N95 respirators, eye protection, non-synthetic clothing, medications, and IDs in a quick-grab bag."),
            (S, "Create defensible space around your home",
             "Clear vegetation within 10 metres of your home and remove dry leaves from gutters to reduce ember ignition risk significantly."),
            (M, "Stock N95 masks and eye drops",
             "Wildfire smoke contains fine particles that damage lungs. Keep N95 respirators and saline eye drops in your kit for every household member."),
            (C, "Know your local fire authority number",
             "Save your regional fire authority's hotline alongside 112/911. In remote areas, a satellite communicator may be your only reliable option."),
        ],
        "Medium": [
            (E, "Monitor fire behaviour and wind direction",
             "Stay updated on fire location via official fire maps. Be ready to leave as soon as a watch is issued — do not wait for a mandatory evacuation order."),
            (E, "Keep your vehicle fuelled and facing out",
             "Ensure your vehicle always has at least a half tank of fuel and is parked facing the exit so you can leave in under 2 minutes if needed."),
            (K, "Pack your go-bag and load the car",
             "Load your pre-packed bag into the car now. Include medications, N95 masks, eye protection, water, chargers, and irreplaceable documents."),
            (S, "Close all vents, doors, and windows",
             "If sheltering in place, close all external vents, pet doors, windows, and doors to prevent embers entering. Fill sinks and bathtubs with water."),
            (M, "Wear N95 during heavy smoke",
             "Fine smoke particles cause long-term lung damage. Wear an N95 respirator whenever outdoors in smoky conditions — a cloth mask is not sufficient."),
            (C, "Notify family of your evacuation plan",
             "Tell family members your evacuation destination and planned route. Check in once you have reached safety."),
        ],
        "High": [
            (E, "Evacuate immediately on watch or order",
             "Do not wait for a mandatory evacuation order if conditions are worsening. Leave as soon as a watch is issued — early departure is always safer."),
            (E, "Use official evacuation routes only",
             "Avoid shortcuts — fire can cross roads without warning. Follow the official evacuation route even if it seems slower."),
            (K, "Grab your bag and go now",
             "Do not stop to collect extra items. Take your pre-packed kit, medications, and pets. Get out immediately."),
            (S, "Close all openings if forced to shelter",
             "If evacuation is cut off, go inside the most fire-resistant building available. Close all vents and doors. Fill baths and sinks. Stay low as smoke rises."),
            (M, "Wear full respiratory protection",
             "Put on an N95 or P100 respirator immediately. Seal gaps around your mask — wildfire smoke at High severity contains life-threatening fine-particle levels."),
            (C, "Inform fire authority of your location",
             "If you cannot evacuate, call emergency services with your exact address and number of people — this triggers a priority rescue response."),
        ],
        "Critical": [
            (E, "Leave immediately — do not delay",
             "At Critical severity, fire behaviour is extreme and conditions can change in minutes. Leave now. Do not attempt to protect property."),
            (E, "If exit is cut off, drive away from fire",
             "If fire blocks your route, drive away keeping headlights on. If the vehicle is compromised, lie flat in a ditch and cover yourself with a wool blanket."),
            (K, "Grab only medications and water",
             "At Critical severity there is no time for a full go-bag. Grab life-essential items only: medications, water, and your phone. Get out immediately."),
            (S, "Last resort — choose brick or stone",
             "If trapped, choose the most fire-resistant building. Close every opening, fill all containers with water, and stay inside away from windows."),
            (M, "Protect airways at all costs",
             "Use a wet cloth over your mouth and nose if you have no respirator. Stay below smoke level — crawl if necessary. Smoke inhalation causes most wildfire fatalities."),
            (C, "Activate personal locator beacon",
             "If you have a PLB or satellite communicator, activate it now. Otherwise text your GPS coordinates to emergency services. Stay visible for aerial rescue."),
        ],
    },

    # ── VOLCANIC ACTIVITY ─────────────────────────────────────────────────────
    "Volcanic activity": {
        "Low": [
            (E, "Know your volcanic hazard zone",
             "Check which volcanic hazard zone your property is in — zones differ for lava flows, ashfall, pyroclastic surges, and lahars, each requiring different action."),
            (E, "Plan multiple evacuation routes",
             "Lava flows and lahars can cut roads without warning. Plan at least three routes to high ground and away from river valleys."),
            (K, "Prepare a volcanic emergency kit",
             "Include N95 respirators, sealed safety goggles, long-sleeved clothing, water, food, medications, and a battery radio in your kit."),
            (S, "Identify materials to seal your home",
             "Keep tape, damp cloths, and plastic sheeting available to seal windows, doors, and vents during ashfall events."),
            (M, "Stockpile respiratory medications",
             "If anyone in your household has asthma or a respiratory condition, carry a 2-week supply of medications and an extra inhaler at all times."),
            (C, "Subscribe to volcano monitoring alerts",
             "Follow your national volcano observatory's alerts by text, email, or radio. Alert levels can change rapidly and early notice saves lives."),
        ],
        "Medium": [
            (E, "Pre-pack your go-bag for ashfall",
             "Pack your go-bag with N95 respirators, goggles, long-sleeved clothing, water, food, and medications. Keep it at the door ready to go."),
            (E, "Understand alert level meanings",
             "Learn what each alert level means for your local volcano. Level 3 typically means eruption is imminent — evacuate without waiting for Level 4."),
            (K, "Prepare sealing materials for ashfall",
             "Have tape, damp cloths, and plastic sheeting ready to seal windows and door frames. Volcanic ash is an abrasive respiratory and structural hazard."),
            (S, "Avoid all river valleys and low ground",
             "Lahars travel down river valleys at highway speeds with little warning. Never shelter in or near a river valley during volcanic unrest."),
            (M, "Wear N95 respirators outdoors",
             "Volcanic ash particles penetrate standard surgical masks. Wear a properly fitted N95 respirator whenever ash is visible in the outdoor air."),
            (C, "Register with local civil defence",
             "Register your address with your local civil defence authority so evacuation teams know your location. Update them when you evacuate."),
        ],
        "High": [
            (E, "Evacuate hazard zones immediately",
             "If you are inside a designated exclusion or hazard zone, evacuate now. Do not return until the volcano observatory officially downgrades the alert."),
            (E, "Move away from rivers and valleys now",
             "Lahars can travel at 60 km/h down river valleys with no warning. Move to high ground away from all waterways immediately."),
            (K, "Use full respiratory and eye protection",
             "Wear a P100 or N95 respirator and sealed safety goggles whenever outdoors. Volcanic ash causes severe lung damage and eye abrasion."),
            (S, "Shelter in a sealed upper-floor room",
             "If evacuation is impossible, seal yourself in an upper-floor room with tape and damp cloths. Volcanic gases are denser than air and settle in low areas."),
            (M, "Monitor for toxic gas symptoms",
             "Sulphur dioxide and CO2 cause headache, dizziness, and shortness of breath. If symptoms appear, move immediately upwind or to higher ground."),
            (C, "Follow observatory updates every 15 minutes",
             "Volcanic conditions can escalate in minutes. Monitor updates frequently and follow evacuation orders without hesitation."),
        ],
        "Critical": [
            (E, "Evacuate immediately — all zones",
             "At Critical level all hazard zones are life-threatening. Leave now, travel upwind and uphill, and do not stop to collect belongings."),
            (E, "Avoid all river valleys and low areas",
             "Pyroclastic surges and lahars travel in river valleys at devastating speed. Get to high, upwind ground as quickly as possible."),
            (K, "Cover all skin and wear a respirator",
             "If caught in ashfall, cover all exposed skin with long sleeves, wear a P100 respirator, and seal safety goggles. Ash causes rapid lung injury."),
            (S, "Do not shelter near the volcano",
             "At Critical level, no building near the volcano is safe. Your only protection is distance — drive upwind and uphill away from the eruption."),
            (M, "Pyroclastic surge requires immediate shelter",
             "If you see a fast-moving dark cloud (pyroclastic surge), seek the most solid building available immediately and protect your airways — do not stay in the open."),
            (C, "Activate emergency beacon and flee",
             "If you have a PLB, activate it while evacuating. Do not stop to make calls — move away from the volcano and contact authorities from a safe distance."),
        ],
    },

    # ── LANDSLIDE ─────────────────────────────────────────────────────────────
    "Landslide": {
        "Low": [
            (E, "Know if your home is on unstable ground",
             "Check geological surveys or contact your local authority to find out if your property sits on a landslide-prone slope or debris flow path."),
            (E, "Plan an uphill evacuation route",
             "Identify a route that takes you perpendicular to the slope, not down the valley. Moving sideways out of a debris flow path is the safest escape."),
            (K, "Prepare a grab-and-go kit",
             "Store 3 days of water, food, torch, first aid, medications, and waterproof boots in a bag near your exit — landslides often occur at night."),
            (S, "Learn warning signs of slope instability",
             "Watch for new cracks in walls or floors, doors and windows that suddenly stick, tilting utility poles, or springs appearing in unusual places."),
            (M, "Learn wound and fracture first aid",
             "Landslide injuries are typically impact injuries. Know how to apply pressure dressings and improvise splints, as rescue may be delayed by blocked roads."),
            (C, "Report slope cracking to authorities",
             "If you notice cracks in slopes above your home, report them to your local geotechnical or civil defence authority — early reporting saves lives."),
        ],
        "Medium": [
            (E, "Be ready to evacuate on short notice",
             "After heavy rain or earthquakes, landslide risk rises sharply. Have your kit packed and be prepared to leave within 5 minutes of a warning."),
            (E, "Avoid valley bottoms during rain",
             "Stay out of valley bottoms and river channels during and immediately after heavy rain. Debris flows can arrive with almost no warning."),
            (K, "Wear waterproof boots and carry a torch",
             "At night, visibility is near zero during a landslide event. Waterproof boots and a head torch are essential for evacuation over debris-covered terrain."),
            (S, "Move to an upper floor if inside",
             "If a landslide hits while you are inside, move to an upper floor away from the slide direction — ground floors are most vulnerable to the initial impact."),
            (M, "Watch for gas leaks after impact",
             "A landslide can rupture gas lines. If you smell gas after a slide, evacuate immediately, do not use any switches, and call the gas company from outside."),
            (C, "Alert neighbours on the same slope",
             "If you receive a warning, knock on doors of nearby neighbours — particularly the elderly and those without internet access. Community warning saves lives."),
        ],
        "High": [
            (E, "Evacuate slopes and valleys immediately",
             "If there is a warning or heavy sustained rain, evacuate slopes and valley floors without delay. Do not wait to see the landslide — it may be seconds away."),
            (E, "Move perpendicular to the slope",
             "If caught in a landslide's path, run perpendicular to the flow direction to get out of its path. Running downhill keeps you in the debris channel."),
            (K, "Grab your kit and waterproof footwear",
             "Take your emergency kit and wear sturdy waterproof boots. Debris fields are hazardous terrain and you may need to walk significant distances to safety."),
            (S, "Abandon ground-floor rooms on the slope side",
             "Move to the upper floor opposite the slope direction. Ground floors on slope-facing walls are most likely to be hit first."),
            (M, "Be prepared for traumatic injuries",
             "Landslide casualties typically involve fractures, lacerations, and crush injuries. Keep your first aid kit accessible and know how to treat severe bleeding."),
            (C, "Report road blockages to emergency services",
             "After a landslide, report blocked roads immediately — this determines where rescue resources are sent first."),
        ],
        "Critical": [
            (E, "Move immediately to high, open ground",
             "If a landslide is imminent or occurring, move immediately to high ground away from the slide path. Do not stop to collect any belongings."),
            (E, "If caught in a slide, curl and protect",
             "If you cannot outrun a landslide, curl into a ball, protect your head with your arms, and try to hold onto a tree or fixed object."),
            (K, "Leave everything — take only yourself",
             "At Critical severity there is no time for a kit. Get out of the landslide path immediately. Reach high ground first, then call for help."),
            (S, "Do not re-enter damaged buildings",
             "Aftershocks or secondary slides can collapse already-damaged structures. Stay in the open on stable high ground until authorities declare the area safe."),
            (M, "Listen for buried survivors",
             "After the slide, listen for calls and tapping. Mark the last seen location of missing persons for search teams. Do not attempt deep excavation — it can re-trigger slides."),
            (C, "Call emergency services from high ground",
             "Once safely clear, call emergency services with your location, the number of people involved, and any known buried victims. Stay accessible for rescue coordination."),
        ],
    },

    # ── DROUGHT ───────────────────────────────────────────────────────────────
    "Drought": {
        "Low": [
            (E, "Assess your water supply sources",
             "Identify alternative food and water sources in your area in case drought disrupts supply chains. Know your nearest emergency water distribution point."),
            (E, "Plan for livestock water needs",
             "If you manage animals, identify in advance the alternative water sources and pasture you would use if your primary supply fails."),
            (K, "Build a household water reserve",
             "Store a minimum 3-day water supply (4 litres per person per day) in sealed food-grade containers in a cool, dark location. Rotate every 6 months."),
            (S, "Insulate your home against heat",
             "Reduce indoor temperature with reflective window film, shade cloth, and draft sealing. Drought conditions frequently co-occur with extreme heat."),
            (M, "Monitor for early heat illness signs",
             "Learn to recognise dehydration and heat exhaustion symptoms early, especially in children and the elderly — these groups are most vulnerable."),
            (C, "Register for government water assistance",
             "Contact your local authority to register for water assistance programs or emergency water trucking before your supply becomes critical."),
        ],
        "Medium": [
            (E, "Implement household water rationing",
             "Short showers, no lawn watering, full-load appliances only. Reducing household use extends community supply and preserves reserves for emergencies."),
            (E, "Locate community water sources",
             "Find your nearest community water distribution point or emergency standpipe and note the operating hours and container requirements."),
            (K, "Expand your water reserve to 7 days",
             "Store a 7-day water supply in food-grade containers only. Do not use containers that previously held non-food chemicals."),
            (S, "Maximise home cooling without AC",
             "Close blinds during the day, open windows at night. Use wet towels and fans. Identify the coolest room in your home as a heat refuge."),
            (M, "Increase water intake proactively",
             "In drought-affected hot conditions, adults need at least 2–3 litres of water per day — more for outdoor workers, children, and the elderly."),
            (C, "Report crop failures to authorities",
             "If you rely on agriculture, report crop failures to your local department to access emergency support and relief programs early."),
        ],
        "High": [
            (E, "Comply with all water restriction orders",
             "Follow official water rationing orders immediately. Rationing preserves supply for drinking and sanitation — the minimum needed for survival."),
            (E, "Prepare to relocate if water is cut",
             "If household water supply is cut, be prepared to relocate to a community shelter or area with reliable water access. Have your bag packed."),
            (K, "Fill every clean container with water now",
             "While supply is still available, fill every clean food-grade container. Sanitise containers first with dilute bleach (1 teaspoon per 4 litres of water)."),
            (S, "Avoid outdoor exertion during peak heat",
             "Stay indoors between 11am and 3pm. Drought heat can cause rapid dehydration and heat stroke in healthy adults within minutes."),
            (M, "Check vulnerable people daily for dehydration",
             "Check on elderly neighbours, children, and anyone with chronic illness every day. Dehydration progresses rapidly. Signs: dark urine, confusion, dry mouth."),
            (C, "Contact authorities if water supply fails",
             "If household water supply is completely cut, contact your local emergency management authority immediately to access emergency distribution."),
        ],
        "Critical": [
            (E, "Follow all water distribution instructions",
             "At Critical drought severity, follow every official instruction for water collection and distribution. Access to water is a survival priority."),
            (E, "Relocate immediately if directed",
             "If authorities order evacuation to water-available areas, comply without delay. Water scarcity at this level is a life-threatening emergency."),
            (K, "Prioritise water above all other supplies",
             "Every available container should hold water. Conserve obsessively — use greywater for sanitation and reserve clean water for drinking only."),
            (S, "Minimise all physical activity",
             "Reduce body water loss by minimising exertion. Stay in the coolest available shelter, particularly during daylight hours. Move only when absolutely necessary."),
            (M, "Treat severe dehydration as an emergency",
             "Severe dehydration causes confusion, organ failure, and death. If someone cannot keep water down or is confused, seek emergency medical care immediately."),
            (C, "Report health emergencies to authorities",
             "If anyone in your community shows signs of severe dehydration or waterborne illness, report it to health authorities immediately — disease spreads rapidly in drought."),
        ],
    },

    # ── EXTREME TEMPERATURE ───────────────────────────────────────────────────
    "Extreme temperature": {
        "Low": [
            (E, "Identify cooling centres near you",
             "Locate your nearest air-conditioned public cooling centre (library, community hall, shopping mall) and its opening hours before a heat event occurs."),
            (E, "Know your vulnerable neighbours",
             "Identify elderly, very young, or chronically ill people near you. Extreme temperature fatalities are concentrated in these groups — check on them during events."),
            (K, "Prepare a temperature emergency kit",
             "Store electrolyte solution, sunscreen SPF50+, a battery-powered fan, cold packs, and warm blankets for cold snaps. Include all prescription medications."),
            (S, "Identify the coolest room in your home",
             "Note which room stays coolest — typically north-facing with thick walls. Prepare it as your heat refuge with water and a fan."),
            (M, "Learn to recognise heat stroke",
             "Heat stroke signs: body temperature above 40°C, confusion, no sweating, flushed skin. This is a medical emergency — cool immediately and call an ambulance."),
            (C, "Plan daily check-ins during heat events",
             "Make a daily check-in plan with elderly or isolated neighbours during extreme temperature events. A single wellness call can save a life."),
        ],
        "Medium": [
            (E, "Reduce outdoor time during peak heat",
             "Avoid outdoor activity between 11am and 4pm. If you must be outside, seek shade every 30 minutes and carry at least 2 litres of water."),
            (E, "Use public cooling centres if needed",
             "If your home exceeds 32°C indoors without cooling, move to a public cooling centre for several hours during the hottest part of the day."),
            (K, "Stock electrolytes and cooling supplies",
             "Have oral rehydration salts, a spray bottle with water, light loose-fitting clothing, and cold compresses available. Do not rely on a single cooling method."),
            (S, "Block out daytime heat",
             "Keep blinds and curtains closed during the day. Open windows only at night when outdoor temperature falls below indoor temperature."),
            (M, "Hydrate before you feel thirsty",
             "Thirst is a late signal of dehydration. Drink 250 ml of water every hour in hot conditions — more if you are outdoors or physically active."),
            (C, "Check on vulnerable people twice daily",
             "During a sustained heat event, check on elderly or isolated neighbours morning and afternoon. Heat illness can progress rapidly in those living alone."),
        ],
        "High": [
            (E, "Stay indoors during extreme heat",
             "At High severity, outdoor exposure during peak hours is dangerous. Stay indoors in the coolest available space. If your home has no cooling, go to a public shelter."),
            (E, "Move vulnerable people to cooled spaces now",
             "Do not leave children, elderly, or ill people in hot cars or hot homes. Move them to air-conditioned spaces immediately — heat stroke can develop in minutes."),
            (K, "Apply active cooling measures",
             "Wet towels on the neck, wrists, and armpits reduce core temperature rapidly. Combine with a fan for best effect. Apply every 15 minutes."),
            (S, "Never leave anyone in a hot vehicle",
             "A car interior can reach 60°C on a 30°C day within minutes. Never leave children or pets in vehicles — break a window immediately if you see a child in distress."),
            (M, "Recognise and treat heat exhaustion",
             "Signs: heavy sweating, cold/pale skin, fast weak pulse, nausea, headache. Move to a cool place, apply wet cloths, sip water. Call emergency services if unresponsive."),
            (C, "Alert emergency services if someone collapses",
             "If someone collapses from heat, call emergency services immediately. Apply ice to the neck, armpits, and groin while waiting — heat stroke is fatal without rapid cooling."),
        ],
        "Critical": [
            (E, "Move to air-conditioned space immediately",
             "At Critical severity, outdoor temperatures are immediately dangerous to life. Move everyone to the coolest available air-conditioned space without delay."),
            (E, "Stop all outdoor exertion now",
             "Physical exertion in Critical heat can cause heat stroke in healthy adults within minutes. All outdoor work and activity must stop until temperature drops."),
            (K, "Maximise cooling aggressively",
             "Apply ice packs to the neck, wrists, and armpits of all household members. Spray skin with cool water and use fans continuously. Monitor body temperature."),
            (S, "Close all heat entry points",
             "Keep all blinds, curtains, and exterior doors closed. Only open windows if outdoor temperature is lower than indoor temperature."),
            (M, "Treat heat stroke as a life emergency",
             "If someone stops sweating, becomes confused, or has a body temperature above 40°C, cool them aggressively with ice and call an ambulance immediately."),
            (C, "Check on every vulnerable person now",
             "In a Critical heat emergency, call or visit every elderly, ill, or isolated person you know. Heat deaths cluster in vulnerable people who live alone without cooling."),
        ],
    },
}

# ── Severity string → ORM enum ────────────────────────────────────────────────
_SEV = {
    "Low":      SL.low,
    "Medium":   SL.medium,
    "High":     SL.high,
    "Critical": SL.critical,
}


async def main() -> None:
    inserted = 0
    skipped  = 0

    async with AsyncSessionLocal() as db:
        for disaster_type, severities in SEED.items():
            for severity_str, items in severities.items():
                sev_enum = _SEV[severity_str]

                # Fetch existing titles for this bucket (idempotency)
                stmt = select(Recommendation.title).where(
                    Recommendation.disaster_type  == disaster_type,
                    Recommendation.severity_level == sev_enum,
                )
                result = await db.execute(stmt)
                existing = {r for r in result.scalars().all()}

                for category, title, body in items:
                    if title in existing:
                        skipped += 1
                        continue
                    db.add(Recommendation(
                        id            = uuid.uuid4(),
                        disaster_type = disaster_type,
                        severity_level= sev_enum,
                        category      = category,
                        title         = title,
                        body          = body,
                    ))
                    inserted += 1

        await db.commit()

    total = inserted + skipped
    print(f"Done. {inserted} inserted, {skipped} skipped (already existed). Total rows processed: {total}.")
    print(f"Coverage: {len(SEED)} disaster types × 4 severity levels × 6 items = {len(SEED) * 4 * 6} expected rows.")


if __name__ == "__main__":
    asyncio.run(main())
