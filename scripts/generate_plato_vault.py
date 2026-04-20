#!/usr/bin/env python3
"""Generate the Plato's Cave demo vault.

Writes a realistic Obsidian vault of a philosophy grad student studying
Plato's Allegory of the Cave. Uses real paper titles pulled from OpenAlex
as citations; daily journal entries are hand-crafted to reference real
terms (Forms, Socrates, Meno, shadows, Republic Book VII, etc.) so the
Umbra pipeline has real material to work with.

Usage:
    python generate_plato_vault.py --out examples/before
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path
from textwrap import dedent

# --- hand-crafted daily entries -------------------------------------------
# Each is a realistic journal entry from a grad student. Dates are in
# MM-DD-YYYY (root-level daily-note convention).

DAILY_ENTRIES: list[tuple[str, str]] = [
    ("01-08-2024", """- Started reading Republic Book VII this morning. The allegory of the cave still hits differently every time.
- Key observation: Plato uses three stages — shadows, reflections, direct sight of the sun. It's not a single ascent, it's graded.
- Socrates describes the prisoner being "compelled" to turn. Compulsion keeps coming up in Plato's epistemology — like the Meno's slave boy.
- TODO: compare with Phaedo's analogy of recollection. Is the cave another recollection story?
- Meeting with advisor Thursday. Need to pin down thesis angle: is the cave primarily political or epistemic?
"""),

    ("01-11-2024", """Notes from seminar on Forms:

- The theory of Forms isn't in Republic directly — it's assumed. You need Phaedo and Parmenides context.
- Aristotle's critique in Metaphysics A.9 is brutal but fair. The Third Man Argument really does bite.
- One student argued Plato abandoned Forms in Parmenides. I don't buy it. Parmenides is exploratory, not recantatory.
- Read a chapter of Gail Fine's *On Ideas*. Her reading of the self-predication problem is careful.
- Question: does the sun-Good analogy require Forms, or just a hierarchy of being?
"""),

    ("01-15-2024", """Distracted day. Reading around the edges.

Thought experiment: what if the cave is literally about sensory perception vs. mathematical knowledge? The shadows are sense-data. The puppets are physical objects. The sun is the Form of the Good.

Then the ascent tracks: aisthesis → doxa → dianoia → noesis. The divided line literally fits inside the cave.

If true: the cave is a *narrative rendering* of the divided line, not a separate argument.

- Need to write this up properly
- Reeve's intro has something like this but less direct
"""),

    ("01-22-2024", """Read Heidegger's lecture on the cave ("Plato's Doctrine of Truth") today. Strange essay.

- Heidegger thinks the cave marks the *beginning* of metaphysics as the reduction of truth (aletheia) to correctness (orthotes). He says truth becomes judgment-truth, not disclosure.
- I find this overreading. Plato never defines truth as correctness in Republic. Heidegger is reading backward from late-modern problems.
- But: his point about the prisoner's *forced* ascent is real. The violence in the text deserves more attention than Anglo readers give it.
- Foucault's power/knowledge would have a field day with the cave guards.
"""),

    ("01-28-2024", """- Reviewed my notes on epistemology unit. Knowledge as justified true belief keeps coming up but Plato's version in Theaetetus is weirder.
- The cave is PRE-Gettier in an interesting sense: the prisoner's "knowledge" of shadows IS justified relative to their experience.
- This is where I want my thesis to land: the cave is about *epistemic contexts* and transitions between them, not absolute truth.
- Started sketching Chapter 2: "Ascent as Context-Shift"
- Reference: the Meno's paradox of inquiry is solved by recollection — the cave offers another solution via direct experience of the Good.
"""),

    ("02-03-2024", """Light day.

Morning: reread the dialectic passages in Republic VII. The training regimen for guardians (arithmetic, geometry, astronomy, harmonics, dialectic) maps onto the stages of the cave. It's not decorative.

Afternoon: coffee with Miriam. She's working on Aristotle's Nicomachean Ethics. We argued about whether Plato is committed to moral realism via the Form of the Good. She says yes obviously, I say the textual evidence is thinner than people admit. Good to be challenged.

Read: half a chapter of Julia Annas's *Platonic Ethics, Old and New*.
"""),

    ("02-09-2024", """- Finished first draft of the intro chapter!
- Main claim: the cave is a *method* for doing philosophy, not a destination. The returning philosopher is the real figure.
- Problem: I keep using "noesis" without defining it clearly. Need a glossary appendix.
- Wrote 2100 words. Sent draft to advisor.
- Procrastinated by reading about the Eleusinian Mysteries. There's a real question whether Plato is cribbing from mystery religion in VII.
"""),

    ("02-16-2024", """Conversation with philosophy of science friend:

Her argument: the cave is a bad model for science because it implies there's a single truth (the sun) rather than a web of theories. Kuhn/Lakatos make it obsolete.

My pushback: the cave isn't about scientific theories, it's about the psychology of believing. The sun is a regulative ideal, not a claim about physics. Descartes's method of doubt is in the same family.

She wasn't convinced. Neither was I, totally.

Key question: can you be a Platonist about ethics without being one about science? Mark Schroeder-style quasi-realism says yes. Parfit says no. I'm leaning Parfit but it's expensive.
"""),

    ("02-20-2024", """- Read a contemporary paper: "Design and development of an interactive educational intervention based on Plato's allegory of the cave through storytelling in a digital learning environment" (OpenAlex). Fun that the allegory shows up in edtech research.
- The authors use the cave to frame digital immersion as analogous to the shadows — students are prisoners of algorithmic curation. Cute but maybe too cute.
- Filed under "applications of the cave" for my lit review.
- Separately: Birdie asked if the cave is depressing. Good question. I said no — the *ascent* is what matters. Pessimistic readings miss the movement.
"""),

    ("02-26-2024", """Bad day for writing. Good day for reading.

- Annas: "Understanding the Good is not an information transfer." This is the heart of my argument.
- The Good isn't a proposition you learn, it's an orientation you acquire. That's why Plato keeps saying it can't be "taught" (see the Seventh Letter).
- TODO: incorporate Seventh Letter material even though its authenticity is disputed. Whether or not Plato wrote it, the view is Platonic.
- Watched a lecture on the Theaetetus. The knowledge-as-perception thesis is demolished in the first 20 pages. Plato clearly doesn't believe sense-perception gives knowledge.
"""),

    ("03-04-2024", """Had a breakthrough or a delusion, not sure which.

What if the cave is a *therapy* rather than an argument? Like Wittgenstein's "showing the fly out of the bottle." The prisoner isn't convinced by premises — he's *disoriented*, then *reoriented*.

Then Plato isn't doing proof-style philosophy at all. He's doing something closer to psychoanalysis or religious conversion.

This would explain: (1) the violence and compulsion in the ascent, (2) the returning philosopher's inability to persuade his former peers, (3) why Plato writes dialogues instead of treatises.

Sketch paragraph, expand later.
"""),

    ("03-11-2024", """- Wrote 1800 words on dialectic.
- Plato's dialectic in Republic VI-VII is *downward* from hypotheses to the unhypothetical. This is backwards from modern "bottom-up" reasoning.
- The unhypothetical first principle is the Form of the Good. It underwrites everything but can't itself be proved.
- Parallel to Spinoza: substance as the thing whose concept requires no other concept. But Spinoza is monist; Plato is pluralist about Forms.
- Kristin stopped by. Asked how the diss is going. I said "slow and suspiciously focused." She laughed.
"""),

    ("03-19-2024", """Thinking about shadows.

- In the cave, shadows are cast by puppets held by someone behind the prisoners. Who holds the puppets? Plato never says.
- Some readings (Bloom): the puppeteers are politicians / sophists / poets — the cave is a political critique of opinion-manufacturing.
- Other readings (Ferrari): the puppeteers are nobody in particular — the allegory shouldn't be pressed for narrative coherence.
- I think Bloom is right about *a* reading but wrong to make it exhaustive. The cave is doing political work AND epistemological work.
"""),

    ("03-25-2024", """- Read Iris Murdoch's *The Sovereignty of Good*. Murdoch's Platonism is wonderful — the Good as an object of *attention* rather than a premise in an argument.
- She writes: "The task of attention goes on all the time and at apparently empty and everyday moments we are 're-fastening' our vision." That's the cave's moral.
- Cite Murdoch heavily in the conclusion chapter.
- Also: her argument that consciousness is morally dense, not morally neutral, maps onto the cave. The prisoner's attention IS their morality.
"""),

    ("04-02-2024", """Nepali wedding planning took most of the day — registered a new Airbnb block, confirmed catering.

Evening reading: Jacques Derrida on Plato's pharmakon. He's looking at Phaedrus not Republic but the same worry applies: writing as a shadow of living speech, speech as a shadow of thought.

Derrida says the cave is a metaphor of metaphor. Shadows of shadows. That's clever but I can't use it in the thesis — too far out.

File under: "things I learned but won't cite."
"""),

    ("04-15-2024", """Advisor meeting today. Good and bad.

- Good: she likes the "therapy not argument" framing from last month. Wants me to develop it as Chapter 3.
- Bad: she thinks the Heidegger section is a distraction. Cut it or make it work. I'll probably cut.
- Action items: re-read the Meno for recollection-vs-ascent comparison, draft Chapter 3 outline by 5/1, find a recent paper on the sun analogy.
- Got a strong coffee, went home, stared at wall.
"""),

    ("04-29-2024", """- Outlined Chapter 3: "The Cave as Therapy."
- Sections: (1) the violence of the ascent, (2) compulsion in Platonic pedagogy, (3) parallel with Wittgenstein, (4) why the returning philosopher fails.
- Wrote the first section. Fine, not great.
- Sunk cost fallacy: I keep thinking about the Heidegger section even though I'm cutting it. Murder your darlings.
- Watched a bad movie with Birdie. Needed it.
"""),

    ("05-10-2024", """Teaching day. Undergrads were weirdly into the cave today. Two asked whether the cave was about *social media*.

Good question actually. The cave's prisoners are (1) immobilized, (2) fed curated images, (3) unaware they are being fed. That's uncomfortably close to algorithmic feed design.

But the cave's exit is *outward* to nature. The social media "exit" is also digital. Maybe the better modern analogy is TV, not the internet.

Made a mental note: DON'T write a trend piece. Focus on the thesis.
"""),

    ("05-22-2024", """- Re-read the sun analogy (Republic 507a-509c). Three things: (1) the sun is cause of both being and becoming visible, (2) the Good is cause of both being and becoming knowable, (3) the Good is BEYOND being.
- That last part — epekeina tes ousias — is the most disputed phrase in Plato. Some scholars (Rosen) treat it as mystical, others (Schofield) read it deflationarily.
- My thesis needs to take a position. I'll go moderate: the Good is beyond *being* in the sense of being a Form among Forms, but it isn't mystical in the Plotinian sense.
- Found a recent paper to cite: "Circumstantial Evidence" uses cave-like framing for epistemic trust (OpenAlex).
"""),

    ("06-07-2024", """Chapter 3 draft complete. 8,200 words.

- The cave as therapy works better than I thought. The ascent isn't an argument you win, it's an orientation you acquire.
- Key weakness: how does one *start* the ascent? Plato never says. The prisoner is just "turned" by someone offstage.
- Socrates's role in dialogues is probably the answer: the philosopher-midwife who forces the turn.
- Sent to advisor. Feeling okay.
"""),

    ("06-20-2024", """Reading an awful edited volume on Plato and pedagogy. Most chapters are just "here are my lesson plans that reference the cave."

Two good chapters:
- One on Plato's criticism of poets in Republic X. Argues the cave is a kind of "philosophical poem" that criticizes poetry while deploying it.
- One on Plato and Buddhism. The cave's prisoner bears real resemblance to samsara. Parallel, not influence.
- Filed both under "conclusion chapter material."
"""),

    ("07-08-2024", """- Submitted Chapter 2 + Chapter 3 to committee. Defense scheduled for October.
- Brief panic.
- Going to spend July doing Chapter 4 (implications for contemporary moral philosophy) and Chapter 5 (conclusion).
- Birdie made birthday plans. Turning 30. Philosophy hasn't made me wise but it has made me patient.
"""),
]

# Topic / project notes — things that already exist in the vault
# before Umbra runs. These provide keyword targets.

TOPIC_NOTES: list[tuple[str, str, str]] = [
    # (relative_path, title, content)
    ("Philosophy/Epistemology.md", "Epistemology",
     "# Epistemology\n\n"
     "The study of knowledge. Central question: what are the conditions "
     "for knowing something, rather than merely believing it?\n\n"
     "Plato's answer (in Theaetetus): not settled. Knowledge-as-perception "
     "fails; knowledge-as-true-belief fails; knowledge-as-true-belief-plus-"
     "logos is troubled by the Gettier-adjacent problem.\n\n"
     "Contemporary epistemology splits into internalist and externalist "
     "camps. Plato is an internalist, mostly.\n"),

    ("Philosophy/Metaphysics.md", "Metaphysics",
     "# Metaphysics\n\n"
     "The study of what there is and how it is. Plato's metaphysics is the "
     "theory of Forms: abstract, eternal, unchanging entities of which "
     "ordinary particulars are imperfect copies.\n\n"
     "The Form of the Good is the highest — not a Form among Forms but "
     "the ground of all Forms. Epekeina tes ousias (beyond being).\n"),

    ("Philosophy/Dialectic.md", "Dialectic",
     "# Dialectic\n\n"
     "Plato's preferred method of philosophical inquiry. In Republic, "
     "dialectic is *downward* reasoning from hypotheses to an "
     "unhypothetical first principle (the Good).\n\n"
     "Not debate. Not Socratic elenchus exactly. More like guided ascent "
     "toward higher principles.\n"),

    ("Philosophy/Socratic Method.md", "Socratic Method",
     "# Socratic Method\n\n"
     "Elenchus — refutation by cross-examination. Socrates does not "
     "offer positive doctrines; he shows his interlocutors that they "
     "don't know what they thought they knew.\n\n"
     "In later dialogues (Republic, Phaedo) Socrates becomes a "
     "mouthpiece for Plato's own views. The method shifts.\n"),

    ("Greek Thinkers/Plato.md", "Plato",
     "# Plato\n\n"
     "c. 428-347 BCE. Student of Socrates, teacher of Aristotle. Founded "
     "the Academy.\n\n"
     "Writes dialogues, not treatises. Never speaks in his own voice "
     "(except arguably in the disputed Seventh Letter).\n\n"
     "Core commitments: Forms, the immortality of the soul, the primacy "
     "of the Good, the educational mission of philosophy.\n"),

    ("Greek Thinkers/Socrates.md", "Socrates",
     "# Socrates\n\n"
     "c. 470-399 BCE. Executed by Athens for impiety and corrupting the "
     "youth. Wrote nothing. Everything we know comes from Plato, "
     "Xenophon, Aristophanes.\n\n"
     "The 'Socratic Problem': which views in the dialogues are the "
     "historical Socrates's and which are Plato's? Almost certainly "
     "unsolvable.\n"),

    ("Greek Thinkers/Aristotle.md", "Aristotle",
     "# Aristotle\n\n"
     "384-322 BCE. Plato's student for twenty years at the Academy.\n\n"
     "Breaks with Plato on Forms — Aristotle's substances are "
     "individual, not abstract universals. The Third Man Argument "
     "(Metaphysics A.9) is the famous critique of Platonic Forms.\n\n"
     "Ethics, politics, biology, logic — Aristotle systematizes almost "
     "everything. Plato stays poetic.\n"),

    ("Greek Thinkers/Parmenides.md", "Parmenides",
     "# Parmenides\n\n"
     "c. 515-? BCE. Eleatic. The deep background for Plato's "
     "metaphysics: 'Being is, not-being is not.'\n\n"
     "Plato's dialogue Parmenides stages a conversation between young "
     "Socrates and old Parmenides. It contains the Third Man Argument "
     "in Platonic form — Plato knew the problem with his own theory.\n"),

    ("Texts/Republic.md", "Republic",
     "# Republic\n\n"
     "Plato's longest and most ambitious dialogue. Structured around the "
     "question: what is justice, and is the just person happier?\n\n"
     "Contains the cave (VII), the sun analogy (VI), the divided line "
     "(VI), and the myth of Er (X). Also the city-soul analogy that "
     "structures the whole argument.\n\n"
     "Reeve's Hackett translation is standard for undergrad use. "
     "Bloom's translation is tendentious but interesting.\n"),

    ("Texts/Phaedo.md", "Phaedo",
     "# Phaedo\n\n"
     "Set on the day of Socrates's execution. Contains four arguments "
     "for the immortality of the soul, plus the recollection argument "
     "that matters for the cave.\n\n"
     "If learning is recollection (anamnesis), then we must have known "
     "before birth. This commits Plato to pre-existence of the soul "
     "AND transcendent objects of knowledge (Forms).\n"),

    ("Texts/Meno.md", "Meno",
     "# Meno\n\n"
     "Short dialogue. Contains the paradox of inquiry: how can you look "
     "for what you don't know?\n\n"
     "Plato's answer is recollection — illustrated by the slave-boy "
     "passage where Socrates gets an uneducated boy to 'remember' "
     "geometric truths.\n\n"
     "The cave offers a different solution to the same paradox: direct "
     "experience of the Good provides the starting point.\n"),

    ("Texts/Theaetetus.md", "Theaetetus",
     "# Theaetetus\n\n"
     "Plato's most focused epistemological dialogue. What is knowledge?\n\n"
     "Three candidate definitions fail: (1) perception, (2) true belief, "
     "(3) true belief with an account (logos). The dialogue ends "
     "aporetically — no positive definition.\n"),

    ("Concepts/Forms.md", "Theory of Forms",
     "# Theory of Forms\n\n"
     "Plato's central metaphysical thesis. Forms (eide, ideai) are "
     "abstract, eternal, unchanging entities. Ordinary particulars are "
     "imperfect copies that 'participate' in Forms.\n\n"
     "Examples: the Beautiful itself, the Just itself, the Triangle "
     "itself. Forms are the real objects of knowledge; particulars are "
     "the objects of opinion.\n\n"
     "Problems: self-predication, the Third Man Argument, the problem "
     "of participation.\n"),

    ("Concepts/Allegory of the Cave.md", "Allegory of the Cave",
     "# Allegory of the Cave\n\n"
     "Republic Book VII, 514a-520a. The most famous passage in Plato.\n\n"
     "Prisoners are chained in a cave, facing a wall. Behind them, "
     "puppeteers cast shadows of objects on the wall, which the "
     "prisoners mistake for reality. A prisoner is freed, ascends "
     "out of the cave, sees the sun.\n\n"
     "Interpretations: epistemological ascent, political critique of "
     "opinion, Platonic education, ontological hierarchy, therapeutic "
     "reorientation.\n"),

    ("Concepts/Divided Line.md", "Divided Line",
     "# Divided Line\n\n"
     "Republic VI, 509d-511e. A geometric image of the degrees of "
     "reality and knowledge.\n\n"
     "Four segments: (1) eikasia — images, shadows, reflections, "
     "(2) pistis — ordinary objects of sense, (3) dianoia — "
     "mathematical reasoning, (4) noesis — knowledge of Forms.\n\n"
     "The cave narratively stages the divided line.\n"),

    ("Concepts/Form of the Good.md", "Form of the Good",
     "# Form of the Good\n\n"
     "The highest Form. 'Beyond being' (epekeina tes ousias). Cause of "
     "both the being and the knowability of other Forms.\n\n"
     "The sun is its image. Disputed whether the Good is itself a Form "
     "or something beyond Forms. Plotinus takes it beyond; Anglo "
     "readers usually keep it in the Form-hierarchy.\n"),

    ("Concepts/Anamnesis.md", "Anamnesis (Recollection)",
     "# Anamnesis (Recollection)\n\n"
     "Plato's doctrine that learning is remembering. Defended in the "
     "Meno and Phaedo.\n\n"
     "Commits Plato to: (1) the soul existing before birth, (2) "
     "transcendent objects of knowledge, (3) the possibility of "
     "inquiry (solving Meno's paradox).\n\n"
     "Relation to the cave: both describe the acquisition of knowledge "
     "as a *recovery* rather than a first-time discovery.\n"),

    ("Concepts/Aletheia.md", "Aletheia",
     "# Aletheia\n\n"
     "Greek for truth. Heidegger etymologizes it as 'un-concealment' "
     "(a-lethe-ia). Heidegger argues Plato begins the reduction of "
     "truth-as-disclosure to truth-as-correctness.\n\n"
     "Most scholars find Heidegger's reading forced, but the attention "
     "to how Plato treats truth is valuable.\n"),

    ("Sources/Reeve Translation Notes.md", "Reeve Translation Notes",
     "# Reeve Translation Notes\n\n"
     "C.D.C. Reeve's Hackett translation of Republic is the standard "
     "undergrad text. Competent, literal, footnoted.\n\n"
     "Compare with Bloom's (Basic Books) — more interpretive, good for "
     "Straussian readings. Grube/Reeve revised is the edited classic.\n\n"
     "Reeve's introduction is underrated — the discussion of the "
     "divided line is particularly clear.\n"),

    ("Sources/Murdoch Sovereignty of Good.md", "Murdoch Sovereignty of Good",
     "# Murdoch — The Sovereignty of Good\n\n"
     "Iris Murdoch's 1970 book. Three essays. Recasts Plato's Good as "
     "an object of moral *attention*, not a premise in moral argument.\n\n"
     "Key quote: 'The task of attention goes on all the time and at "
     "apparently empty and everyday moments we are re-fastening our "
     "vision.'\n\n"
     "Heavily cited in my conclusion chapter.\n"),

    ("Sources/Annas Platonic Ethics.md", "Annas — Platonic Ethics",
     "# Annas — Platonic Ethics, Old and New\n\n"
     "Julia Annas's 1999 book revisiting Plato's ethics in light of "
     "virtue-ethics revival.\n\n"
     "Key move: understanding the Good is not propositional — it's "
     "formative. You can't 'know' the Good without becoming different.\n"),

    ("Thesis/Chapter Outlines.md", "Thesis Chapter Outlines",
     "# Thesis Chapter Outlines\n\n"
     "- Chapter 1: Introduction. The cave in context.\n"
     "- Chapter 2: Ascent as Context-Shift. Epistemic contexts, not "
     "absolute truth.\n"
     "- Chapter 3: The Cave as Therapy. Orientation, not argument.\n"
     "- Chapter 4: Implications for contemporary moral philosophy.\n"
     "- Chapter 5: Conclusion. Return as the real figure.\n"),

    ("Thesis/Defense Prep.md", "Defense Prep",
     "# Defense Prep\n\n"
     "Committee: advisor (Plato), external (Aristotle / ancient), "
     "internal (moral phil).\n\n"
     "Anticipated hard questions:\n"
     "1. Why prioritize Book VII over the rest of Republic?\n"
     "2. How do you avoid Plotinian mysticism on the Good?\n"
     "3. What does 'therapy' add beyond traditional pedagogy readings?\n"
     "4. How does your reading engage the Third Man Argument?\n"),

    ("Reading List.md", "Reading List",
     "# Reading List (Dissertation)\n\n"
     "## Primary\n"
     "- Republic (Reeve, Hackett)\n"
     "- Phaedo (Grube)\n"
     "- Meno (Grube)\n"
     "- Theaetetus (McDowell)\n"
     "- Parmenides (Gill)\n\n"
     "## Secondary\n"
     "- Julia Annas, *Platonic Ethics, Old and New*\n"
     "- Iris Murdoch, *The Sovereignty of Good*\n"
     "- Gail Fine, *On Ideas*\n"
     "- Myles Burnyeat, *The Theaetetus of Plato*\n"
     "- Gregory Vlastos, *Platonic Studies*\n"),
]


def write_openalex_citations(out_dir: Path, records_tsv: Path) -> None:
    """Drop a Sources/OpenAlex-citations.md summarizing real papers."""
    if not records_tsv.exists():
        return
    lines = ["# OpenAlex Citations", "",
             "*Papers referenced during dissertation research "
             "(auto-pulled from OpenAlex).*", ""]
    with open(records_tsv) as f:
        reader = csv.reader(f, delimiter="\t")
        seen = 0
        for row in reader:
            if len(row) < 4 or not row[0].strip():
                continue
            title = row[0].strip()
            concepts = row[1][:200].strip()
            year = row[2] if len(row) > 2 else ""
            if seen >= 25:
                break
            lines.append(f"- **{title}**"
                         + (f" ({year})" if year and year.isdigit() else ""))
            if concepts:
                lines.append(f"  - Concepts: {concepts}")
            seen += 1
        lines.append("")
    (out_dir / "Sources").mkdir(parents=True, exist_ok=True)
    (out_dir / "Sources" / "OpenAlex Citations.md").write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=str, required=True,
                        help="Output vault directory")
    parser.add_argument("--records",
                        default="examples/plato_cave_records.tsv",
                        help="OpenAlex TSV (for citations)")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # Minimal .obsidian so Obsidian recognizes it as a vault
    (out / ".obsidian").mkdir(exist_ok=True)
    (out / ".obsidian" / "app.json").write_text("{}\n")

    # Daily notes
    for date, body in DAILY_ENTRIES:
        (out / f"{date}.md").write_text(body)

    # Topic notes
    for rel, _title, body in TOPIC_NOTES:
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)

    # OpenAlex citations from real records
    write_openalex_citations(out, Path(args.records))

    print(f"Wrote {len(DAILY_ENTRIES)} daily notes + "
          f"{len(TOPIC_NOTES)} topic notes to {out}")


if __name__ == "__main__":
    main()
