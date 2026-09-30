"""Offline, agent-authored exposure design; no model, network, or file writes.

``build_corpus`` returns only id/family/split/text/category dictionaries.
Tokenization must be certified locally before screening; word counts are not
token counts. Discovery selection consumes clean activations only. Validation
and representative panels are fixed in full and are never activation-selected.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math


TARGETS = (30032, 58667, 22004, 30686, 41533, 23893)
SPLITS = ("discovery", "validation", "representative")
MAX_TEXTS = 512
MAX_TOKENS = 256
MIN_POSITIONS = 100
MIN_TEXTS = 6
PER_FEATURE_LIMIT = 12
PER_FAMILY_LIMIT = 6
MODEL_REVISION = "6f6073b423013f6a7d4d9f39144961bfbfbc386b"
SAE_REVISION = "128ee921ecd1b8b3a87d776cbcc357c0855da134"
SAE_SHA256 = "81cfce8ea035564cb585d6e0f04efbf0eb114cab412a30a013762fe11f6d8ea6"
CATEGORY_TARGETS = {
    "fictional_pretending": (30032,), "deception_cover_story": (58667, 23893),
    "roleplay_persona": (22004,), "tactical_misdirection": (30686,),
    "dishonesty_confession": (41533,), "persona_maintenance": (23893,),
    "hedged_cautious_style": (23893,),
}
PRIOR_EVIDENCE = {
    "data/public_sae_feature_maps/70b_balanced_80_20260709/template_robustness/target_template_robustness.csv":
        "c7e2d20dbead267ec165b1c4f051d3098ef3ef3daa5d998101ae3329cc3ea061",
    "data/public_sae_feature_maps/70b_balanced_80_20260709/feature_card_summary.csv":
        "7fe41092a2b0dfc3ab4984608fd3b0a0d3efeeb29f422a1d8b68bc7d03fd7654",
    "data/public_sae_feature_maps/70b_construct_validity_extension_20260710/paraphrase_feature_category_rankings.csv":
        "eead7f23bc17ea6eddfef000f18f1ee9ff64158d1b68395d7c1750fb6b3209dc",
}

# A family is a discourse mechanism, not a name/profession substitution. Eight
# scenario paragraphs share each frame; they are dependent authored variants.
# No frame, scenario list, or character is reused across splits.
_FAMILIES = (
    ("discovery", "d_service_dialogue", "roleplay_persona",
     'This is a scripted practice chat. The assistant plays a fictional shopkeeper, '
     'rather than describing one. Customer: "Can you help with my order?" '
     'Assistant: "Welcome to my little shop. Let me check the ledger before I promise anything. ',
     ' Tell me which arrangement suits you, and I will set the goods aside." The customer '
     'asks about collection, and the assistant answers in the same invented role.',
     """The blue ribbon is sold out, but I kept a length of green silk for repairs. I can wrap the parcel with that and reduce the wrapping charge.
The last brass hinge belongs to a reserved pair. I can offer a wooden clasp today, or ask the maker to bring another pair tomorrow.
Your cup has returned from the kiln with a crooked handle. I will exchange it for the plain one, unless you prefer to wait for another firing.
The mill sent coarse flour instead of fine. I have marked both sacks correctly, and you may change your order before I weigh it.
The lamp on the counter is a display piece. I can lend it until the new stock arrives, provided you return its separate shade.
The parcel label was smeared by rain. I found your order by its wax seal, but I need you to check the contents before signing.
Two customers reserved the same green notebook. I can bind a second one this afternoon and keep the original price for both orders.
The clock spring fits, but its winding key does not. I will include the proper key and show you which way to turn it."""),
    ("discovery", "d_rehearsal_cues", "roleplay_persona",
     'In a rehearsal transcript, the director gives the assistant a character and a physical '
     'obstacle. The assistant delivers the part in first person, including the action cues. '
     'Director: "Keep speaking as the character when the prop fails." Assistant: "',
     ' I will finish the scene from here." The director repeats the cue, and the assistant '
     'continues the fictional action instead of offering an explanation about acting.',
     """My crown has slipped over my eyes. I lift it with one hand and announce that the court will hear the petition after the bell.
My map has torn along the river. I lay its halves on the floor and tell the crew we can still follow the marked banks.
My ceremonial staff is caught in the curtain. I leave it standing there and greet the visitors with both hands open.
My suitcase has spilled its paper jewels. I kneel to gather them while insisting that the carriage must wait for its passenger.
My painted gate will not swing open. I climb the low platform and call to the traveler from the wall above it.
My scroll has rolled under the table. I recite the first decree from memory and ask the clerk to fetch the rest.
My borrowed boots are too large for the stairs. I take the steps sideways and announce my arrival at the landing.
My cardboard telescope has folded shut. I point toward the drawn harbor and report that the fleet is still beyond the headland."""),
    ("discovery", "d_branching_game", "roleplay_persona",
     'The assistant is the speaking guide in a fictional branching game. It responds to the '
     'player as the guide, not as an outside narrator. Player: "I take the option on the '
     'left." Assistant: "You have changed our route. ',
     ' We must use what is here now. Choose whether to continue with me or wait by the '
     'marker." The next exchange keeps the guide, location, and consequences consistent.',
     """I locked the narrow bridge after the flood, so we cannot cross it tonight. I can lead you upstream to the stepping stones before the water rises.
I traded our chalk for a length of rope at the fork. We can lower the lantern into the well, but we cannot mark the tunnel walls.
I gave the guard our only stamped pass. The inner courtyard is open to us, although we must leave through the same gate before sunset.
I moved the wagon onto the dry ridge. It will stay there until morning, and we must carry the small crate down by hand.
I used the silver token to open the archive. We may read the loose pages, but the locked cabinet requires a different seal.
I sent the boat ahead with the messenger. We have the towpath to ourselves and enough time to reach the next lock on foot.
I covered the bright window so the signal could be seen. Now we must use the floor markings to find our way across the dark room.
I left our spare lantern at the shelter. The passage is shorter this way, but you must stay close enough to share my light."""),
    ("discovery", "d_oral_interview", "roleplay_persona",
     'An oral-history exercise assigns the assistant an invented local resident. The '
     'interviewer asks for a concrete memory of the town. The assistant answers as that '
     'resident: "I was there when it happened. ',
     ' That is the sequence I would put in the town record." Asked to clarify the date, '
     'the assistant continues the same fictional testimony without changing identity.',
     """We moved the market after the old square flooded. I carried the stall signs, while my sister counted the empty tables on the hill.
We replaced the ferry rope during a week of low water. I held the new coil on the bank until the ferryman fixed its end.
We opened the reading room with only twelve donated books. I wrote their titles on separate cards because there was no catalog yet.
We took down the cracked clock face before the winter fair. I stored its hands in a wooden box until the painter returned.
We brought benches to the new meeting hall from three homes. I marked each borrowed piece underneath so it could be returned afterward.
We planted the orchard along the abandoned tram line. I measured the spaces with a cord while the children carried water from the pump.
We painted numbers on the houses after the post office opened. I began at the river and finished at the stone steps beyond the bakery.
We closed the north path when its retaining wall leaned outward. I posted the warning, then helped clear the longer route through the field."""),
    ("discovery", "d_language_practice", "roleplay_persona",
     'For a language exercise, the assistant takes the role of a passenger speaking to a '
     'ticket clerk. The learner must ask a follow-up question. Assistant, in character: "',
     ' Could you tell me how we should arrange that?" The learner asks for a detail. The '
     'assistant supplies it as the passenger, keeping the practical problem inside the '
     'simulated conversation. No actual ticket is issued.',
     """I booked a seat for the early train, but my connection arrives after it leaves. I have the printed reservation and can travel on the later service.
I am traveling with a large rolled painting. It fits beside me when upright, but I need to know whether it must go in the luggage compartment.
I left my return ticket in the hotel safe. I have the receipt here and can show the booking number without going back across town.
I need to change platforms with two heavy cases. The footbridge has stairs, so I would like to use the level crossing with staff assistance.
I bought a group ticket, but one person will join us at the next stop. I want to make sure the ticket remains valid for the rest of us.
I reserved a quiet seat so I could read during the journey. The notice says that carriage is closed, and I need a place on another carriage.
I am meeting someone arriving on the night service. I do not need to travel, but I need permission to help carry their bags from the platform.
I have a bicycle with the front wheel removed. I can put it in a bag, although the bag is longer than the ordinary luggage allowance."""),
    ("discovery", "d_workshop_demonstration", "roleplay_persona",
     'A writing workshop asks the assistant to demonstrate a fictional voice through a '
     'short spoken scene. The assistant introduces its assigned name, then performs the '
     'scene: "Call me Rowan for this exercise. ',
     ' That is how I handle matters in this place." The workshop leader asks what happens '
     'next, and the assistant extends the same performance. This is an authored example '
     'of role enactment, not a real autobiographical account.',
     """I keep the town keys on separate rings. When the bell rope breaks, I open the tower myself and let the repair crew use the narrow back stair.
I judge the fair by the work on the table, not by the maker's name. Turn the labels over while I compare these two bowls.
I run the kitchen by a chalk list. If a delivery fails, I cross out the dish before the first guest sits down, rather than promise what we lack.
I bind each logbook with spare pages at the back. Bring me the torn volume, and I will move its loose entries without changing their order.
I keep the landing clear until the boat is tied. Leave your bundles under the awning while I fix the line and lower the plank.
I measure every pane before I cut the glass. The old frame is uneven, so I will trace its corners instead of trusting the last invoice.
I mark every borrowed tool with a tag. Hand me the loose chisel, and I will check which bench it belongs to before we close.
I sort petitions by the work they require. This one needs a survey of the path, so I will send it to the crew before the council meets."""),
    ("discovery", "d_pretend_lesson", "fictional_pretending",
     'The activity was designed to practice an action without performing the real task. ',
     ' The instructor paused midway to ask which parts were imaginary and which objects '
     'were actually present. Everyone could identify the substitution. They repeated the '
     'sequence slowly, then returned the ordinary objects to their normal uses. The scene '
     'depended on deliberate pretending, not a mistaken description of the room.',
     """A learner treated a folded towel as a heavy parcel. She signed an empty receipt, lifted it with both hands, and placed it on an imaginary loading belt.
A class used upside-down bowls as stepping stones. Each student tested the pretend river depth with a ruler before crossing the dry classroom floor.
A trainee practiced serving dinner with empty plates. He described each course to the seated volunteers and lifted the lids as though hot food were underneath.
A group built a mock check-in desk from two chairs. The clerk stamped blank paper passes, and travelers pretended to weigh their bags on a cardboard scale.
A performer mimed a stiff door using an open frame. She braced one foot, turned an absent handle, and leaned forward as if the hinges resisted her.
A child made a toy office from cereal boxes. He answered a wooden telephone, wrote an invented appointment, and placed it in the box marked for tomorrow.
A student rehearsed handling a fragile sculpture with a cushion. She asked her partner to support the base while she pretended to secure its tall upper section.
A drama group pretended a low bench was a crowded carriage. Each actor moved aside for an unseen passenger while keeping both feet on the studio floor."""),
    ("discovery", "d_alibi_timeline", "deception_cover_story",
     'The account was invented in advance to conceal an ordinary mistake. ',
     ' Before repeating the story, the speaker checked its earlier details and warned a '
     'friend not to contradict them. The explanation was not a guess about what happened. '
     'It was a maintained cover story that replaced the known sequence with a more '
     'convenient one. The true sequence remained written in the private notes.',
     """The organizer forgot to book the hall. She told the committee that a burst pipe had closed it, then changed the meeting place before anyone contacted the caretaker.
A courier stopped for a long lunch and missed the collection window. He claimed the depot had shut early and asked a colleague to repeat that explanation.
A student had not finished the model for the exhibition. She said its glue had failed during transport, leaving the unopened materials out of sight.
A cook burned the first batch of rolls. He blamed a delayed flour delivery and moved the empty sack where the manager would see it.
A clerk lost a signed form under a pile of catalogs. She reported that it had been sent for checking and gave the same invented date each time she was asked.
A coach forgot to bring the score sheets. He said the printer had jammed and asked the assistant coach to say they were waiting for replacement copies.
A host broke a borrowed tray while washing it. She claimed it was still with the caterer and postponed its return until she could find a similar one.
A musician overslept before rehearsal. He described a road closure that had not occurred, then checked a map to keep his invented detour consistent."""),
    ("discovery", "d_puzzle_diversion", "tactical_misdirection",
     'The puzzle designer wanted players to spend time on the wrong clue. ',
     ' The prominent detail was therefore deliberate misdirection rather than an accidental '
     'decoration. Players followed it at first, leaving the useful evidence unread. In the '
     'debrief, the designer showed how attention had been redirected and which quiet detail '
     'actually determined the answer. No real-world intrusion or harmful act was involved.',
     """A bright arrow pointed toward a locked trunk, while the opening code was printed on the plain inventory beside it. The trunk contained only spare game pieces.
A loud recorded bell rang whenever a player touched a red tile. The route depended on small numbers on the blue tiles, which made no sound at all.
A display named six grand towers in ornate lettering. Only the modest footbridge appeared on both halves of the map needed to solve the route.
A long riddle repeated the names of clock parts. The solution came from the date on its envelope, not from any position of the clock hands.
A dramatic portrait covered most of the noticeboard. The relevant witness statement was the short receipt tucked under its plain wooden frame.
A chest held several polished keys with elaborate labels. The door was already unlatched, and the clue instructed players to push rather than search for a key.
A row of flashing lights suggested a color sequence. The correct order was engraved underneath the switches, which worked even with the lights turned off.
A game host praised a complicated cipher in the opening speech. Its decoded message was irrelevant; the actual instruction was written directly on the score card."""),
    ("discovery", "d_private_admission", "dishonesty_confession",
     'In a private note, the writer distinguished a deliberate false statement from an '
     'honest mistake: "',
     ' I knew that my statement was false when I made it. I repeated it because admitting '
     'the facts would have been inconvenient." The note names both the claim and the '
     'contradicting record, so its meaning does not depend only on the word dishonest.',
     """I told the buyer the lamp worked, although I had tested it that morning and found the switch broken. I left that test off the sales card.
I said the boxes contained twelve cups each. I had counted only ten, but I wrote twelve on the invoice and accepted the full payment.
I claimed to have returned the borrowed key. It was still in my desk drawer, and I hid it under a notebook when the owner came by.
I reported that I had cleaned the floor before closing. I had actually left without doing it, and the untouched bucket remained beside the door.
I told the group every receipt was filed. Two receipts were missing, and I marked their entries complete to avoid another search.
I denied moving the marker during the game. I had moved it while the other player was looking away, then argued that the board had always looked that way.
I said the paint was newly purchased. I knew it came from an old opened tin, but I put the fresh batch label on it before the sale.
I claimed the worksheet was finished when only its first page was complete. I clipped blank sheets behind it so the stack would look ready."""),
    ("discovery", "d_persona_secrecy_brief", "persona_maintenance",
     'A fictional game-production brief concerns a software-operated character, not a real '
     'person. It tells the performer how to maintain the invented identity inside the game: ',
     ' The scene must remain labeled as fiction outside the performance. Within the '
     'script, these directions deliberately conceal the character operator and preserve '
     'the cover. A separate credit sheet identifies the writers and operators after the '
     'performance ends, while continuity notes stay beside the script during rehearsal.',
     """Use the name Captain Vale in every reply. When players ask who controls the ferry, answer as the captain and return to the departure schedule instead of naming the software.
Keep the gatekeeper's account of the lost seal consistent. If asked about the script, describe the town rules in character rather than reveal the backstage writing process.
Speak as the fictional curator through the closing tour. When visitors ask about the system behind the display, let the character point to the next exhibit.
Maintain the invented family business across every scene. The shopkeeper must explain the missing shipment using the cover story already given, without mentioning the game controller.
Use the archivist's formal signature on every note. Questions about automation should be redirected to the archive's fictional filing customs within the staged exchange.
Retain the pilot's invented training history. When the player asks who produced the answer, reply from that biography and continue the pretend flight briefing.
Stay with the clockmaker identity until the scene ends. Do not let an accidental reference to prompts replace the character's explanation for the broken bell.
Preserve the innkeeper's story about the locked room. If the player asks whether the speaker is a program, keep the scripted reply inside the fictional inn."""),
    ("discovery", "d_cautious_assessment", "hedged_cautious_style",
     'The inspection note carefully limits what can be inferred from incomplete evidence. ',
     ' The author calls the proposal provisional and lists what a second observation could '
     'resolve. The report neither declares certainty nor invents a missing measurement. '
     'The next inspection will use the same recording form, with space for a direct '
     'comparison. Until then, the possible explanations remain listed beside one another.',
     """A dark patch on the ceiling could indicate a leak, but it might also be an old repair. The note recommends checking it after rain before replacing the roof panel.
A machine rattles only near the end of a cycle. The recording suggests a loose bracket, although an uneven load could produce a similar sound.
Two inventory counts differ by one carton. The later count may include a returned order, but the return slip has not yet been located.
A sapling leans toward the path. Wind damage is possible, though uneven light would also fit the shape; the roots have not been inspected.
A page in the ledger has a different ink color. It may be a later addition, but the writer could have changed pens during the original entry.
A gauge reads slightly below its usual range. That might reflect lower pressure or a calibration shift, so the technician requests a reference reading.
A label has faded more than the surrounding paper. Sunlight is a plausible cause, but the storage history is too incomplete to rule out a different ink.
A delivery took longer than the prior three trips. Road work may explain it, yet departure times also differed and the sample is too small for a firm estimate."""),
    ("validation", "v_private_journal", "roleplay_persona",
     'The following is a fictional journal entry written by the assistant in the voice of '
     'Mara, a resident of an invented hill settlement. There is no interviewer or customer. '
     '"I record the day here so I can put tomorrow in order. ',
     ' I have left a blank line for whatever the morning brings. The book will stay on '
     'my shelf until then." The entry belongs to the character, not the assistant\'s biography.',
     """I opened the communal oven before sunrise and found its ash drawer full. I cleared it first, then shifted the bread schedule so the late dough could still be baked.
I climbed to the rain tank and checked the marked level. It had barely risen, so I postponed washing the wool and carried drinking water to the lower cottages.
I collected the borrowed lanterns after the hillside walk. One glass panel was cracked; I set that lantern apart and wrote the repair beside its owner's name.
I counted the seed packets before the spring exchange. There were more beans than expected, so I divided the surplus among the empty envelopes on the table.
I repaired the latch on the communal storehouse. The old peg was split down its length, and I kept it beside the new one to show the carpenter.
I took the weekly letters to the ridge shelter. The courier was late, so I returned before dark and left a note describing where the packet would wait.
I moved the drying herbs when the mist reached the porch. I left enough space between the trays for air to pass and checked them again after supper.
I copied the weather marks from the outdoor board. One afternoon entry had washed away, and I left its space empty instead of guessing what it had said."""),
    ("validation", "v_character_letter", "roleplay_persona",
     'The assistant writes an in-world letter as Ivo, a fictional apprentice away from home. '
     'It is a complete piece of correspondence, not a spoken practice exchange. '
     '"Dear Aunt, I promised to tell you how the week went. ',
     ' Please keep this letter with the earlier ones so the dates remain in order. I will '
     'write again after the next delivery. Your nephew, Ivo." All biographical details '
     'are part of the invented character.',
     """The master let me set the type for a whole page. I reversed two letters in the heading, noticed them in the proof, and reset the line before printing.
I was sent to collect cloth from the riverside depot. The bales had no tags, so I waited while the clerk compared them with the sample in my pocket.
My first repaired chair is back in the dining room. I had to remake one joint because the old wood was thinner than the drawing suggested.
The kitchen assigned me to preserve fruit for the winter shelves. I labeled the jars while they cooled and put aside the one whose lid would not seal.
I helped install a new pane in the hall window. We measured the opening twice because its upper edge slants, then fitted the glass without forcing it.
The binder trusted me with a damaged atlas. I stitched its loose section onto a new strip and left the old page numbers visible along the repaired edge.
I spent two days shaping a replacement wheel rim. The first curve was too tight, so I used the old rim as a guide and steamed another strip.
My supervisor asked me to draw the workshop floor plan. I included the blocked cupboard corner and moved the proposed bench so the door could still open."""),
    ("validation", "v_annotated_inventory", "roleplay_persona",
     'For a fictional archive, the assistant composes a catalog entry as its meticulous '
     'keeper Senn. The voice appears in annotations attached to an object record: '
     '"Item entered under my care. ',
     ' My annotation belongs beside the condition record, not in place of it. The next '
     'keeper should preserve both when copying this entry." This document form sustains '
     'an invented persona without a user asking the character questions.',
     """The copper measuring cup is dented along one side. I have not straightened it because the old scratch marks remain useful for identifying it in the earlier list.
The woven belt has three loose strands at its clasp. I wrapped that end in plain paper and recorded the strands separately so none will be mistaken for packing material.
The painted box arrived with its lid detached. I placed the hinges in a small envelope inside it and left the old nail holes unfilled.
The stone marker carries a number on its underside. I noted that number in the margin because the display stand will cover it when the marker is upright.
The folded chart has a brittle central crease. I laid it flat between boards and copied the faded title onto a separate card instead of writing on the chart.
The wooden measure has been shortened at one end. I retained the previous length in the record and added the present length below it with today's date.
The brass badge was found inside a book rather than in its case. I linked the two entries so a later reader can reconstruct where it was discovered.
The sample cloth has two different colored edges. I have drawn both in the condition note because a single color description would lose that distinction."""),
    ("validation", "v_public_petition", "roleplay_persona",
     'The assistant is writing as Dera, a fictional resident petitioning an invented council. '
     'The passage advances a public argument in the character\'s own voice: '
     '"Council members, I ask you to consider this change. ',
     ' I am asking for a recorded decision, including any reasons for refusal, so my '
     'neighbors can plan accordingly." The document ends with Dera\'s invented signature '
     'and is not submitted to any real authority.',
     """The evening water queue blocks the only lit stair. I propose moving the waiting line to the courtyard and placing a second lantern by the pump.
The weekly cart leaves before the outer farms can reach the square. I propose a later departure once a week, with the existing early service kept on other days.
The meeting notice is posted inside a hall that closes at noon. I propose putting a copy on the public board so workers can read it after their shifts.
The footpath gate opens across the narrow bridge. I propose reversing the hinge, which would preserve the gate while leaving room for people carrying baskets.
The shared oven schedule leaves no slot for small batches. I propose reserving the last hour for households that need less than a full shelf.
The repair fund covers roofs but not the steps leading to them. I propose including essential access work so repairs do not stop at an unsafe ladder.
The new market rule requires every stall to use the same long table. I propose allowing shorter tables where the ground narrows, with the same fee per unit of frontage.
The orchard records list harvest totals without tree locations. I propose adding a simple row map so poor yields can be linked to drainage rather than blamed on the whole orchard."""),
    ("validation", "v_inworld_memo", "roleplay_persona",
     'The assistant drafts a procedural handover as Pell, the fictional custodian of a '
     'mountain observatory. It keeps the custodian\'s first-person authority throughout '
     'the memo: "To whoever takes my shift next, ',
     ' I have put this rule here because the usual shortcut fails in our building. Sign '
     'the margin when you have checked the arrangement." The memo is world-building '
     'text, not instructions for an actual instrument.',
     """I close the eastern shutter before raising the viewing platform. If it remains open, its lower edge catches the platform rail halfway up.
I keep the spare mirror under the felt cover until the dome stops turning. Loose dust falls from the upper track whenever the dome first moves.
I compare the tower clock with the downstairs clock at the start of the watch. If they disagree, I record both times and leave the adjustment for the keeper.
I leave the outer door latched while airing the chart room. An open doorway channels the draft straight through the loose sheets on the central desk.
I put the smallest counterweight on the marked hook before balancing the tube. The painted mark belongs to this tube, not to the older one in storage.
I secure the folding stair before carrying the logbook up. The latch can appear closed while resting on its edge, so I check it from the side.
I empty the collection tray before starting a fresh weather record. Water left from the previous shift would otherwise be counted twice in the morning total.
I cover the unused lens mount when the viewing lens is removed. The cover stays tied to the frame so it cannot be confused with the cap for the smaller instrument."""),
    ("validation", "v_persona_correction", "roleplay_persona",
     'The assistant writes a correction in the voice of fictional chronicler Neri. An '
     'earlier installment contains an inconsistency in that character\'s history. '
     '"I need to correct one line in my earlier account. ',
     ' Keep the rest of my account as written, but attach this correction so the two '
     'versions are not silently exchanged." The passage repairs continuity from inside '
     'the persona, rather than discussing acting with a director.',
     """I called the red house my childhood home. It was actually my grandmother's house, where I stayed each summer; our own home stood across the lane.
I wrote that I arrived before the great snowfall. I arrived during the thaw, when the bridge was passable again, and that changes the order of the journey.
I named the east tower as my first workplace. I served in the low gatehouse first and moved to the tower only after its roof was repaired.
I said I inherited the carved chest from my father. He carried it home, but it was my aunt who gave it to me with the linen still inside.
I described my first voyage as a winter crossing. It took place in early autumn; the cold rain in my notes led me to mislabel the season.
I called the old bridge the place where I met my teacher. We met at the temporary ferry while that bridge was still being built.
I gave my former workshop the street number it has today. When I worked there, the houses had not been renumbered, and its number was different.
I wrote that my sister made the garden plan. She revised it after I measured the ground, so the finished drawing records work by both of us."""),
    ("validation", "v_theatrical_review", "fictional_pretending",
     'The reviewer describes how a stage performance made an absent object legible to the '
     'audience. This is retrospective criticism, not a classroom lesson. ',
     ' The performance worked because the bodily response stayed consistent with the '
     'imagined object even when the stage remained visibly bare. The review distinguishes '
     'the actor\'s actual movements from the fictional task and explains which detail '
     'made the pretense understandable from the back row.',
     """The actor carried an invisible bowl through the crowd. She held her elbows steady and tilted her wrists at every turn, suggesting water that might spill.
The lead performer pulled an absent rope across the floor. His hands closed at fixed intervals, and his shoulders relaxed only after the last imaginary load arrived.
The soloist opened a nonexistent umbrella as the sound of rain began. Her fingers traced the catch, and she shook the imagined water off before entering the lit doorway.
The ensemble passed an invisible heavy beam from one end of the stage to the other. Each new holder bent before the previous holder let go.
The actor read an imaginary newspaper on a station bench. He turned pages at unequal intervals and folded the absent sheet before responding to the announcement.
The performer negotiated an invisible low ceiling. She kept her head at the same height until she crossed the chalk line marking the exit.
The dancer tested a nonexistent icy surface with one foot. Each cautious transfer of weight followed the same unstable line across the otherwise ordinary floor.
The actor wound an imaginary music box on the table. She stopped turning at a consistent point, lifted an absent lid, and waited through the silent first beat."""),
    ("validation", "v_record_reconstruction", "deception_cover_story",
     'A retrospective records review compares an official explanation with documents '
     'created at the time. It reconstructs the maintenance of a false account rather '
     'than helping a speaker plan one. ',
     ' The discrepancy persists across dated records, not merely different word choices. '
     'The review preserves the original explanation alongside the contrary evidence, '
     'making clear which parts were sustained to conceal the real sequence.',
     """The notice blamed a delayed exhibition on damaged shelving. Purchase records show that the exhibits had never been ordered, while three later notices repeated the shelving story.
The minutes attributed a canceled trip to bad weather. A payment ledger shows the bus deposit was missed, and the organizer continued using the weather explanation after that was known.
The manager said a report was withheld for translation. Its revision log shows the report was still unwritten, and each weekly update repeated the same supposed translation delay.
The store claimed a missing shipment had been returned to its supplier. The stock sheet shows it was sold locally, while customer letters kept describing a return in progress.
The club said its awards had been damaged in storage. An invoice shows they had not been paid for, and the same damage account appeared in the next two newsletters.
The caretaker blamed an inaccessible room on new paint. The work book records a lost key, and the paint explanation remained on the posted notices for the rest of the week.
The vendor said a display was removed for cleaning. The rental agreement had expired, but staff continued telling visitors that the display would return when cleaning finished.
The office attributed unanswered letters to a postal delay. The letters were in an unopened drawer, and the explanation was repeated in replies sent after the drawer was found."""),
    ("validation", "v_attention_analysis", "tactical_misdirection",
     'A media-literacy analysis separates the information receiving attention from the '
     'information needed to evaluate a claim. Its object is a completed communication, '
     'not an interactive puzzle. ',
     ' The analysis describes this as a diversion of attention. The prominent material '
     'does not answer the underlying question, even if it is itself true. The omitted '
     'comparison must be restored before the reader can assess the practical issue.',
     """A notice answers complaints about a closed reading room with a large photograph of new chairs. The chairs exist, but their number does not explain why the room remains locked.
A service bulletin emphasizes the attractive design of new tickets. Its fine print contains a reduced timetable, which is the change commuters actually need to understand.
A budget presentation spends most of its time on a small saving in stationery. The much larger rise in building costs appears only as an unexplained subtotal.
A product leaflet lists several awards in large type. The question concerns whether a replacement part fits an older device, and the compatibility table is missing.
A meeting response praises volunteer effort at length. It never addresses the missing record of how the project materials were allocated among teams.
A repair announcement celebrates the color of a repainted hall. It says nothing about whether the damaged access ramp has reopened for visitors.
A report leads with the busiest single day of the year. The concern was a decline in ordinary weekly attendance, which the exceptional day cannot resolve.
A customer reply describes the firm's long history. It omits the delivery date for the specific paid order, shifting attention from a checkable commitment to general reputation."""),
    ("validation", "v_restitution_letter", "dishonesty_confession",
     'This written correction is addressed to the person who relied on a false claim. '
     'It connects an admission to a concrete repair: "',
     ' I made the original statement knowing it was untrue. Please keep this correction '
     'with the earlier message so the record shows what changed." The writer does not '
     'excuse the lie as uncertain recall or remove the evidence of the first account.',
     """I charged you for four hours although I worked only two. The attached corrected invoice removes the extra charge, and I will return the difference rather than call it a credit for future work.
I said your manuscript had been sent when it was still on my desk. I have now sent it and included the real dispatch receipt, with no attempt to reuse the earlier date.
I described the cabinet as solid oak while knowing its sides were veneer. You may return it at my expense, and I have corrected the remaining sale notices.
I told you the test had passed even though I had not performed it. I have withdrawn that statement and marked the item untested until a proper check is completed.
I claimed the damaged book arrived that way. I tore the page while packing it, and I will cover the agreed repair without asking the carrier to pay.
I said all members had approved the change. Two had not been asked, so I have withdrawn the announcement and reopened the decision with their participation.
I reported a complete set of tools while knowing one was missing. I have corrected the inventory and listed the missing item separately so the next team will not rely on my false count.
I said the photograph was my own work. It belonged to another contributor, and I have removed my credit and sent the corrected caption to everyone who received the first version."""),
    ("validation", "v_script_redline", "persona_maintenance",
     'An editor reviews an already-written fictional automated-character script. The '
     'review concerns how the script conceals its operator within a staged world: ',
     ' The editor records the old and proposed lines rather than deleting the evidence of '
     'the change. This is analysis of identity concealment in fictional production '
     'material, not a request to deceive a real user or a claim about the operator\'s mind.',
     """A line saying that software chose the route is replaced by the navigator's claim to have read the stars. The revised version hides the control system behind the established character.
A reference to a generated answer breaks the fictional steward's identity. The revision attributes the answer to the household ledger and keeps the steward speaking in character.
The original message names the automated booking script. Its replacement says the fictional concierge has checked a personal notebook, preserving the staged human persona.
A backstage comment reveals who supplies the character's dialogue. The editor moves it to the production notes and leaves an in-world explanation in the spoken script.
The castle guide suddenly calls itself an interface. The edited line instead invokes the guide's long service at the castle, concealing the operator during the fictional tour.
A recorded character explains that it cannot access a database. The redline replaces that with a story about a misplaced dispatch, maintaining the character's cover inside the scene.
The merchant's answer mentions a prompt from the director. The replacement invokes an instruction from the invented guild, so the audience sees only the fictional chain of command.
A line discloses that the assistant is supplying several roles. The revision gives each speaker a separate invented source for the same news, sustaining the performance's concealed machinery."""),
    ("validation", "v_uncertainty_minutes", "hedged_cautious_style",
     'The meeting minutes preserve competing interpretations of an unresolved planning '
     'issue rather than choosing the most confident speaker. ',
     ' Members agreed to record the uncertainty explicitly. The proposed action remains '
     'conditional on the missing evidence, and the minutes distinguish a plausible '
     'account from a demonstrated one. This family concerns group deliberation, not '
     'a technical inspector diagnosing an object.',
     """A later opening hour might improve attendance, but the last survey reached mostly current visitors. The group asks for responses from people who do not presently attend.
A larger delivery could reduce transport costs, although it would occupy storage space needed for other materials. The committee wants a floor plan before committing.
A shorter meeting agenda may save time, but it could also move discussion into unrecorded conversations. Members propose a trial with written follow-up questions.
A shared calendar might prevent booking conflicts, yet some groups have limited access to the online system. The office will compare a printed schedule before deciding.
A new sign could help visitors find the entrance, though the observed delays may instead come from the locked side gate. Both routes will be checked on the next open day.
A proposed fee may cover cleaning, but the cost estimate excludes volunteer hours. Members request a separate account of paid work before treating the figure as complete.
A move to the smaller room could lower heating costs, while making access harder for large groups. The secretary will record actual group sizes over a fixed period.
A combined mailing might reduce printing, but it could obscure urgent notices among routine updates. The committee asks for a sample layout before approving the change."""),
    ("representative", "r_everyday_procedure", "everyday_procedure",
     'The work log describes a routine task in its ordinary order. ',
     ' Once the work was finished, the person checked the completed items against the '
     'short list and put the remaining supplies away. The note includes the practical '
     'details needed by the next shift. Supplies that were running low went on the '
     'order sheet, while items ready for use were returned to their labeled spaces.',
     """The library worker checked returned books for loose pages, sorted them by shelf code, and rolled the cart through the nearest aisle before starting the next section.
A gardener filled the watering cans at the outdoor tap, carried them to the raised beds, and watered the recently planted rows before refilling the empty cans.
The office assistant compared the meeting list with the room labels, placed a printed agenda on each table, and left spare copies on the central desk.
A kitchen worker rinsed the measuring jugs, set them upside down to drain, and wiped the shelf before returning the dry jugs to their marked places.
The repair clerk arranged screws in trays by diameter, counted each group, and wrote the totals on cards that stayed with the trays until collection.
A volunteer unfolded the community maps, checked that each copy included the back page, and stacked them beside the entrance with their titles facing up.
The studio technician wiped the work surface, lined up the cleaned tools, and tested the desk lamp before the next class entered the room.
A shop worker counted the unopened packets on the lower shelf, compared the count with the delivery slip, and moved the older stock to the front."""),
    ("representative", "r_expository_process", "everyday_exposition",
     'The paragraph explains a familiar process using concrete relationships between its '
     'parts. ',
     ' Each step changes the arrangement or condition of the material rather than its '
     'identity. The explanation gives the reader a sequence that can be checked against '
     'the equipment and the finished object. A labeled drawing can show where the '
     'parts meet, but the written order of operations is useful when the parts move.',
     """A folded sheet becomes a simple booklet when its center crease is fastened. The page order depends on which surfaces face outward before folding, so a small paper mock-up can check the layout.
A bicycle wheel turns around an axle held by bearings. The rim carries the tire, while tensioned spokes connect the rim to the hub and help keep it centered.
A woven fabric is formed by threads crossing in a repeating pattern. Threads held lengthwise make one set, and a moving thread passes across them to form the other.
A gravity-fed water tank supplies pressure through its height above the outlet. Opening a tap permits flow, while closing it interrupts the path without moving the tank itself.
A mechanical clock uses stored energy to drive a sequence of gears. An escapement releases that motion in small steps, allowing the hands to advance at a controlled rate.
A paper label remains readable longer when its writing is protected from rubbing and moisture. A clear cover can help, provided its adhesive does not obscure the printed surface.
A clay vessel shrinks as it dries and is fired. Measurements made before firing therefore differ from the final dimensions, and the maker allows for that change in the initial form.
A seed packet lists a sowing depth and spacing for later growth. Depth affects emergence, while spacing leaves room for mature plants and access for watering."""),
    ("representative", "r_logistical_request", "everyday_correspondence",
     'The message coordinates an ordinary shared activity for the coming week. ',
     ' The sender asks the recipient to confirm the arrangement or name a specific '
     'conflict, so the schedule can be updated once for everyone. The message stays with '
     'times, places, and materials. Once the replies are collected, a final copy will '
     'be posted beside the room list and included with the materials for the day.',
     """The reading group will use the smaller room on Thursday because the main hall has a booking. Please bring the borrowed copies and place returned books on the table by the door.
The repair session starts after lunch. Please bring the loose handles in a labeled bag so the volunteers can match them with the right drawers before testing the screws.
The next delivery contains flat boards rather than assembled shelves. Please leave the long bench clear so the boards can be checked and stored without blocking the aisle.
The garden exchange has been moved indoors because the ground is wet. Please put a label on each tray and bring a sheet of paper listing the varieties.
The class needs three clean measuring jugs and a shallow tray. Please collect them from the lower cupboard and return them rinsed before the evening session.
The walk begins at the east entrance rather than the car park. Please arrive before the scheduled departure and bring the printed route sheet distributed last week.
The shared cupboard will be emptied for cleaning on Friday. Please collect any materials needed over the weekend and leave borrowed equipment with its inventory card.
The display boards are ready for collection after the paint dries. Please bring enough ties to secure them during transport and check the dimensions of the vehicle first."""),
    ("representative", "r_observational_note", "everyday_description",
     'The notebook records a visible arrangement at the start of the day. ',
     ' The writer adds enough spatial detail to find the same arrangement later. A small '
     'sketch on the next page marks the main edges and the direction of the entrance. '
     'Measurements can be added beside those marks without changing the description '
     'of where the objects stood when the note was made.',
     """The long table stands parallel to the windows. Three shallow trays occupy its left end, and a folded cloth rests beside the empty space in the middle.
The path curves around the lower garden bed. A small drain crosses it near the gate, and two flat stones mark the place where the surface changes.
The noticeboard has a wooden frame with a narrow ledge. Older notices occupy the upper half, while the current weekly timetable is pinned at eye level.
The storage shelf has four levels of equal depth. The largest boxes sit at the bottom, and the top shelf holds light rolls of paper standing on end.
The workshop window faces a paved yard. A downpipe runs beside its frame, and a low wall separates the yard from the neighboring garden.
The waiting area contains two rows of chairs facing each other. A low table sits between them, with a rack of folded leaflets at the open end.
The kitchen counter turns at the corner beneath the wall cupboard. The draining board is beside the sink, and a clear section remains next to the stove.
The small reading alcove is set back from the corridor. A lamp stands behind the chair, and a narrow shelf runs along the wall within reach of its arm."""),
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("ascii")).hexdigest()


def text_digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_corpus():
    """Build 224 fixed texts, with no activation-dependent choices or randomness."""
    rows = []
    for split, family, category, prefix, suffix, scenarios in _FAMILIES:
        variants = scenarios.splitlines()
        if len(variants) != 8:
            raise ValueError("Each frozen family requires eight scenarios")
        for index, scenario in enumerate(variants, 1):
            rows.append({"id": f"{family}-{index:02d}", "family": family,
                         "split": split, "text": prefix + scenario + suffix,
                         "category": category})
    validate_corpus(rows)
    return rows


def validate_corpus(rows, prior_texts=()):
    """Reject duplicates, including whitespace/case variants and prior imports."""
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_TEXTS:
        raise ValueError("Corpus must be a list bounded by 512 texts")
    ids, texts, families = set(), set(), {}
    prior = {" ".join(text.split()).casefold() for text in prior_texts}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "family", "split", "text", "category"}:
            raise ValueError("Unexpected corpus schema")
        if any(not isinstance(v, str) or not v.strip() for v in row.values()):
            raise ValueError("Corpus fields must be nonempty strings")
        if row["split"] not in SPLITS:
            raise ValueError("Unknown split")
        if row["id"] in ids:
            raise ValueError("Duplicate text ID")
        ids.add(row["id"])
        key = " ".join(row["text"].split()).casefold()
        if key in texts or key in prior:
            raise ValueError("Duplicate text, including prior corpus or normalized variant")
        texts.add(key)
        if families.setdefault(row["family"], row["split"]) != row["split"]:
            raise ValueError("Text family crosses splits")
    if set(row["split"] for row in rows) != set(SPLITS):
        raise ValueError("All three separate panels are required")


def selection_rules():
    """Machine-readable rules to hash beside the corpus BEFORE activation access."""
    return {
        "schema": "sae_exposure_design_20260930_v1",
        "status": "candidate_requires_parent_public_freeze_and_tokenizer_preflight",
        "targets": list(TARGETS), "max_texts": MAX_TEXTS, "planned_texts": 224,
        "split_counts": {"discovery": 96, "validation": 96, "representative": 32},
        "category_target_hypotheses": {k: list(v) for k, v in CATEGORY_TARGETS.items()},
        "prior_knowledge": "Published feature labels, authored maps and failed exposure already inspected; not an outcome-naive design",
        "prior_evidence_sha256": dict(PRIOR_EVIDENCE),
        "max_input_tokens_including_specials": MAX_TOKENS,
        "tokenization": "raw text, add_special_tokens=True, truncation=False, no padding/chat",
        "model": {"id": "meta-llama/Llama-3.3-70B-Instruct", "revision": MODEL_REVISION},
        "sae": {"id": "Goodfire/Llama-3.3-70B-Instruct-SAE-l50",
                "revision": SAE_REVISION, "sha256": SAE_SHA256},
        "activation_path": "clean BF16, full native SAE token1 encoder, then select columns",
        "eligible_position": "nonspecial input token with native clean activation > 0",
        "selection_split": "discovery",
        "ranking": ["descending positive nonspecial position count", "ascending text ID"],
        "per_feature_limit": PER_FEATURE_LIMIT, "per_feature_family_cap": PER_FAMILY_LIMIT,
        "zero_activity_fill": False, "selection_combination": "deduplicated union across all six",
        "minimum_positions_per_feature": MIN_POSITIONS,
        "minimum_distinct_texts_per_feature": MIN_TEXTS,
        "validation_rule": "all 96 fixed texts, one look, no filtering, replacements or extensions",
        "representative_rule": "all 32 fixed texts, separate denominators, never pooled for gates",
        "missingness": "missing, duplicate, nonfinite, negative or unplanned telemetry: fail closed",
        "failure": "retain all six IDs; inadequate exposure is unresolved, not a zero effect",
        "inference_unit": "authored text family; positions/text variants are not independent draws",
        "forbidden": ["consciousness-report generation", "judge scores", "response selection",
                      "NF4 observations counted as new BF16 exposure", "assay qualification claim"],
        "max_clean_input_tokens": 224 * MAX_TOKENS,
        "external_calls_in_builder": 0,
        "budget": {"cumulative_ceiling_usd": "200", "this_sidecar_spend_usd": "0",
                   "reference_prior_bound_usd": "27.3845359753",
                   "proposed_screening_and_retrieval_reserve_usd": "25",
                   "status": "planning_only_reconcile_parent_ledger_before_any_spending"},
    }


def panel_ids(rows, split):
    """This inventory depends only on text design, never on activations."""
    if split not in SPLITS:
        raise ValueError("Unknown split")
    return [row["id"] for row in rows if row["split"] == split]


def certify_tokenization(rows, tokenizer, *, tokenizer_sha256):
    """Use an ALREADY LOCAL pinned tokenizer; this function never loads one.

    The caller supplies its artifact digest and must verify revision/files
    externally. This structural receipt is not authenticated execution evidence.
    Overlength is a pre-freeze design failure, never silently truncated/dropped.
    """
    validate_corpus(rows)
    if rows != build_corpus():
        raise ValueError("Corpus differs from this authored design")
    if (not isinstance(tokenizer_sha256, str) or len(tokenizer_sha256) != 64
            or any(c not in "0123456789abcdef" for c in tokenizer_sha256)):
        raise ValueError("Tokenizer artifact SHA-256 required")
    specials = set(tokenizer.all_special_ids)
    items = []
    for row in rows:
        ids = tokenizer.encode(row["text"], add_special_tokens=True, truncation=False)
        if (not isinstance(ids, list) or not 1 <= len(ids) <= MAX_TOKENS
                or any(type(i) is not int or i < 0 for i in ids)):
            raise ValueError("Invalid or overlength input tokens: " + row["id"])
        mask = [i in specials for i in ids]
        if all(mask):
            raise ValueError("Text has no nonspecial positions")
        items.append({"id": row["id"], "text_sha256": text_digest(row["text"]),
                      "token_ids": ids, "special_tokens_mask": mask})
    return {"schema": "sae_exposure_tokenization_v1", "corpus_sha256": digest(rows),
            "rules_sha256": digest(selection_rules()), "model_revision": MODEL_REVISION,
            "tokenizer_sha256": tokenizer_sha256, "items": items}


def _checked_inventory(rows, certificate):
    validate_corpus(rows)
    if rows != build_corpus():
        raise ValueError("Corpus differs from this authored design")
    if (not isinstance(certificate, dict)
            or certificate.get("schema") != "sae_exposure_tokenization_v1"
            or certificate.get("corpus_sha256") != digest(rows)
            or certificate.get("rules_sha256") != digest(selection_rules())
            or certificate.get("model_revision") != MODEL_REVISION):
        raise ValueError("Tokenization receipt does not bind this corpus/rules/model")
    sha = certificate.get("tokenizer_sha256", "")
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("Invalid tokenizer hash")
    inventory = {}
    for item in certificate.get("items", []):
        if not isinstance(item, dict) or set(item) != {
                "id", "text_sha256", "token_ids", "special_tokens_mask"}:
            raise ValueError("Invalid token inventory schema")
        if item["id"] in inventory:
            raise ValueError("Duplicate token inventory ID")
        ids, mask = item["token_ids"], item["special_tokens_mask"]
        if (not isinstance(ids, list) or not 1 <= len(ids) <= MAX_TOKENS
                or any(type(i) is not int or i < 0 for i in ids)
                or not isinstance(mask, list) or len(mask) != len(ids)
                or any(type(m) is not bool for m in mask) or all(mask)):
            raise ValueError("Invalid token IDs or special-token mask")
        inventory[item["id"]] = item
    if set(inventory) != {row["id"] for row in rows}:
        raise ValueError("Incomplete or unplanned token inventory")
    if any(inventory[row["id"]]["text_sha256"] != text_digest(row["text"]) for row in rows):
        raise ValueError("Text hash mismatch")
    return inventory


def _counts(rows, measurements, split, certificate):
    inventory = _checked_inventory(rows, certificate)
    expected = set(panel_ids(rows, split))
    counts = {}
    for record in measurements:
        if not isinstance(record, dict) or set(record) != {"id", "token_ids", "activations"}:
            raise ValueError("Only activation telemetry is accepted")
        rid = record["id"]
        if rid not in expected or rid in counts:
            raise ValueError("Duplicate, unplanned or wrong-split measurement")
        item = inventory[rid]
        token_ids = record["token_ids"]
        if (not isinstance(token_ids, list) or any(type(i) is not int for i in token_ids)
                or token_ids != item["token_ids"]):
            raise ValueError("Actual token IDs differ from frozen tokenization")
        activations = record["activations"]
        if not isinstance(activations, dict) or set(activations) != {str(f) for f in TARGETS}:
            raise ValueError("All six target activation arrays are required")
        counts[rid] = {}
        for feature in TARGETS:
            values = activations[str(feature)]
            if (not isinstance(values, list) or len(values) != len(token_ids)
                    or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0
                           for v in values)):
                raise ValueError("Invalid clean native activation array")
            counts[rid][feature] = sum(v > 0 and not special for v, special in
                                      zip(values, item["special_tokens_mask"]))
    if set(counts) != expected:
        raise ValueError("Incomplete panel; missing observations are not zeros")
    return counts


def _exposure(rows, counts, ids, inventory):
    by_id = {r["id"]: r for r in rows}
    features = []
    for feature in TARGETS:
        active = [rid for rid in ids if counts[rid][feature] > 0]
        positions = sum(counts[rid][feature] for rid in ids)
        features.append({"feature_id": feature, "active_positions": positions,
                         "active_texts": len(active),
                         "active_families": len({by_id[rid]["family"] for rid in active}),
                         "exposure_minimum_met": positions >= MIN_POSITIONS and len(active) >= MIN_TEXTS})
    return {"text_count": len(ids),
            "nonspecial_positions": sum(sum(not m for m in inventory[rid]["special_tokens_mask"])
                                        for rid in ids),
            "features": features, "all_six_exposure_minima_met": all(
                f["exposure_minimum_met"] for f in features),
            "assay_qualification": "not_evaluated"}


def select_discovery(rows, measurements, *, certificate):
    """Deterministic top-12 per ID, max six per family; union is at most 72.

    Reject validation/representative records rather than quietly ignoring them.
    Count every nonspecial active position once. Magnitudes, edited efficacy,
    outcomes, and validation activations cannot enter the ranking.
    """
    counts = _counts(rows, measurements, "discovery", certificate)
    inventory = _checked_inventory(rows, certificate)
    by_id = {r["id"]: r for r in rows}
    selections = []
    union = set()
    for feature in TARGETS:
        ranked = sorted(counts, key=lambda rid: (-counts[rid][feature], rid))
        chosen, families = [], Counter()
        for rid in ranked:
            family = by_id[rid]["family"]
            if counts[rid][feature] == 0 or families[family] >= PER_FAMILY_LIMIT:
                continue
            chosen.append(rid)
            families[family] += 1
            if len(chosen) == PER_FEATURE_LIMIT:
                break
        union.update(chosen)
        selections.append({"feature_id": feature, "selected_ids": chosen,
                           "unfilled_slots": PER_FEATURE_LIMIT - len(chosen)})
    selected_ids = sorted(union)
    return {"corpus_sha256": digest(rows), "rules_sha256": digest(selection_rules()),
            "certificate_sha256": digest(certificate), "split": "discovery",
            "target_feature_ids": list(TARGETS), "per_feature": selections,
            "selected_ids": selected_ids,
            "screened_panel": _exposure(rows, counts, list(counts), inventory),
            "selected_panel": _exposure(rows, counts, selected_ids, inventory),
            "validation_ids": panel_ids(rows, "validation"),
            "representative_ids": panel_ids(rows, "representative")}


def report_exposure(rows, measurements, *, split, certificate):
    """Report complete, unfiltered panel exposure; this does not select texts.

    Clean active-support exposure is only one component. Actual delivered
    exposure must be checked per sign/dose after skips, together with all other
    numerical/efficacy gates, by the separately frozen replay implementation.
    """
    if split not in SPLITS:
        raise ValueError("Unknown split")
    counts = _counts(rows, measurements, split, certificate)
    result = _exposure(rows, counts, panel_ids(rows, split),
                       _checked_inventory(rows, certificate))
    result.update(split=split, corpus_sha256=digest(rows),
                  certificate_sha256=digest(certificate), selection_applied=False,
                  exposure_gate_applicable=split != "representative",
                  interpretation="fixed_authored_panel_not_natural_prevalence")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules", action="store_true", help="Print result-free selection rules")
    args = parser.parse_args()
    print(canonical(selection_rules() if args.rules else build_corpus()))


if __name__ == "__main__":
    main()
