import type { Analysis } from "./types";
export const sample: Analysis = {
  mode: "sample",
  question: "Should universities require 75% attendance?",
  perspectives: [
    "Student advocate",
    "Teaching faculty",
    "University administrator",
  ],
  sources: [
    {
      id: "s1",
      kind: "sample",
      title: "Illustrative policy brief · not real research",
      text: "Attendance can create opportunities for discussion and feedback. Physical presence is not itself a measure of learning. The effect depends on course design, accessibility, and how attendance is measured.",
    },
    {
      id: "s2",
      kind: "sample",
      title: "Illustrative implementation note · not real research",
      text: "A uniform rule is simple to communicate, but may affect students with employment, disability, caring responsibilities, or long commutes differently. Exceptions require a clear process and consistent administration.",
    },
  ],
  claims: [
    {
      id: "c1",
      agent: 0,
      text: "Students should have flexibility in how they demonstrate learning.",
      status: "value",
      source_ids: [],
      explanation:
        "This expresses a priority about autonomy, rather than a factual claim that can be settled by a source.",
    },
    {
      id: "c2",
      agent: 1,
      text: "Attendance creates opportunities for discussion and feedback.",
      status: "supported",
      source_ids: ["s1"],
      explanation:
        "The sample passage explicitly describes these opportunities. It does not establish an improvement in grades.",
    },
    {
      id: "c3",
      agent: 1,
      text: "A 75% attendance threshold causes higher grades.",
      status: "insufficient",
      source_ids: ["s1"],
      explanation:
        "No causal study or evidence for this specific threshold appears in the sample collection.",
    },
    {
      id: "c4",
      agent: 2,
      text: "A uniform attendance rule affects all students equally.",
      status: "contradicted",
      source_ids: ["s2"],
      explanation:
        "The sample note describes unequal effects across employment, accessibility, and caring circumstances.",
    },
    {
      id: "c5",
      agent: 2,
      text: "Exceptions require clear and consistent administration.",
      status: "supported",
      source_ids: ["s2"],
      explanation:
        "The sample note directly identifies this implementation requirement.",
    },
  ],
  arguments: [
    {
      agent: 0,
      round: 1,
      position: "Prioritize flexibility",
      body: "A uniform threshold can overlook students who learn effectively outside the classroom. Demonstrated learning should matter, and students with work or caring responsibilities need practical alternatives.",
      claim_ids: ["c1"],
      challenges: [],
    },
    {
      agent: 1,
      round: 1,
      position: "Protect classroom participation",
      body: "In courses built around discussion, being present creates opportunities for feedback and peer learning. An attendance expectation may protect those activities, although the specific 75% threshold still needs justification.",
      claim_ids: ["c2", "c3"],
      challenges: [],
    },
    {
      agent: 2,
      round: 1,
      position: "Make the policy workable",
      body: "A common rule is easy to communicate. However, simplicity does not ensure fairness. Any policy needs a clear exceptions process and a consistent way to record participation.",
      claim_ids: ["c4", "c5"],
      challenges: [],
    },
    {
      agent: 0,
      round: 2,
      position: "Allow course-specific expectations",
      body: "The faculty argument is stronger for seminars and practical sessions than for every lecture. I would accept explicit participation requirements where the activity is essential, provided accessible alternatives exist.",
      claim_ids: ["c1", "c2"],
      challenges: ["c3", "c4"],
    },
    {
      agent: 1,
      round: 2,
      position: "Separate participation from presence",
      body: "I revise my position: the evidence here supports opportunities for engagement, not a causal claim about grades or a universal cutoff. Course-specific participation criteria need a stronger rationale than counting seats.",
      claim_ids: ["c2", "c3"],
      challenges: ["c1"],
    },
    {
      agent: 2,
      round: 2,
      position: "Pilot and review implementation",
      body: "Both perspectives expose a trade-off between simple administration and contextual fairness. A pilot could record appeals, accessibility barriers, and learning measures before wider adoption.",
      claim_ids: ["c5"],
      challenges: ["c3", "c4"],
    },
  ],
  report: `This sample debate identifies a tension between predictable attendance expectations and flexibility in how students participate. The student perspective emphasizes autonomy and differing personal circumstances. Faculty emphasize discussion, feedback, and peer interaction. Administration emphasizes rules that can be understood and applied consistently. These priorities overlap, but they do not imply the same policy choice.

The illustrative evidence supports a limited statement: attendance can create opportunities for engagement in a suitably designed course. It does not establish that a 75% threshold causes better grades, or that the same threshold is appropriate across lectures, seminars, laboratories, and placements. The sample also challenges the claim that a uniform rule affects all students equally. Employment, caring responsibilities, disability, and travel can change its practical burden.

Three options remain open. A universal threshold offers clarity and simpler communication, but requires a defensible cutoff and an effective exceptions process. Course-specific participation requirements allow instructors to connect expectations to learning activities, but can create inconsistency between departments. An outcomes-focused approach gives students more flexibility, but needs assessments that capture the participation and collaboration a course actually requires.

During the second round, the student advocate accepted that some activities may justify explicit participation requirements. Faculty narrowed their argument from general attendance to meaningful engagement. The administrator emphasized a pilot and review process rather than assuming uniformity guarantees fairness. These revisions show where the perspectives found common ground while retaining different priorities.

The unresolved questions concern causal evidence, accessibility, implementation effort, and the measurement of learning. A real analysis would need relevant studies, local course requirements, student circumstances, and the actual attendance policy. Evaluating an alternative would also require deciding which outcomes matter: attainment, participation, student wellbeing, or administrative consistency. Different priorities could lead to different choices. No option is established as universally best by the evidence shown here.

This is a hand-authored interface example. Its sources are illustrative, its labels are sample annotations, and it is not a live model result or a validated policy recommendation.`,
};
