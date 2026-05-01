/* caseApi.js — fixture-backed shim for GET /cases/{case_id}
 *
 * Real backend will return the same shape; swap fetchCase() to a real
 * fetch() call when the API is wired up.
 *
 * Response shape (from prompt):
 *   {
 *     case: { id, court_id, case_name, docket_number, date_filed, date_argued,
 *             appeal_from_str, originating_docket_number, has_audio, blocked,
 *             absolute_url, source_docket_id, slug, date_ingested },
 *     primary_opinion_id: number,
 *     opinions: [
 *       { id, source_opinion_id, case_id, cluster_id, absolute_url,
 *         opinion_type, author_id, author_str, author_display, per_curiam,
 *         page_count, download_url, sha1, plain_text, html_with_citations,
 *         clean_text, text_source, extracted_by_ocr, date_ingested }
 *     ],
 *     citations: [ ... ]
 *   }
 */

const CASE_FIXTURES = {
  // Single-opinion case — the common shape.
  5: {
    case: {
      id: 5,
      source_docket_id: 69240367,
      court_id: "scotus",
      absolute_url: "/docket/69240367/richard-eugene-glossip-petitioner-v-oklahoma/",
      slug: "richard-eugene-glossip-petitioner-v-oklahoma",
      case_name: "Richard Eugene Glossip, Petitioner v. Oklahoma",
      case_name_short: "Glossip",
      docket_number: "22-7466",
      date_filed: "2023-05-04",
      date_argued: "2024-10-09",
      appeal_from_str: "Court of Criminal Appeals of Oklahoma",
      originating_docket_number: "PCD-2023-267",
      has_audio: true,
      blocked: false,
      date_ingested: "2026-04-14T02:09:26.719774+00:00",
    },
    primary_opinion_id: 73,
    opinions: [
      {
        id: 73,
        source_opinion_id: 11243457,
        case_id: 5,
        cluster_id: 73,
        absolute_url: "/opinion/10776870/glossip-v-oklahoma/",
        opinion_type: "010combined",
        author_id: 3045,
        author_str: null,
        author_display: "Sonia Sotomayor",
        per_curiam: false,
        page_count: 81,
        download_url: "https://www.supremecourt.gov/opinions/24pdf/604us1r13_c0n2.pdf",
        sha1: "e69fabac02b54c2f2755a87f3d5ae22ee9851311",
        plain_text:
`PRELIMINARY PRINT

Volume 604 U. S. Part 1

GLOSSIP v. OKLAHOMA

CERTIORARI TO THE COURT OF CRIMINAL APPEALS OF OKLAHOMA

No. 22-7466. Argued October 9, 2024 — Decided February 25, 2025

In 1997, Justin Sneed beat Barry Van Treese to death with a baseball bat at an Oklahoma hotel owned by Van Treese and managed by petitioner Richard Glossip. Sneed avoided the death penalty by agreeing to testify that Glossip had hired him to kill Van Treese. The State's case against Glossip turned almost entirely on Sneed's testimony, and the jury convicted Glossip of capital murder.

After the State conceded constitutional error in postconviction proceedings, the Oklahoma Court of Criminal Appeals declined to vacate the judgment, reasoning that Glossip had not satisfied the State's procedural requirements. Glossip sought review here, and we granted certiorari to consider whether the prosecution violated its constitutional obligation to correct false testimony, and whether the lower court's refusal to grant relief on that ground rested on an adequate and independent state-law ground.

Held: The judgment of the Oklahoma Court of Criminal Appeals is reversed, and the case is remanded for further proceedings consistent with this opinion.

I

The factual record is unusually well developed. Two independent counsel — appointed by successive Oklahoma Attorneys General — reviewed the State's files and concluded that material evidence had been suppressed. Among the suppressed materials were notes from a 2003 prosecutorial interview with Sneed indicating that he had been treated for a serious psychiatric condition by a jail physician. The prosecution allowed Sneed to testify falsely on this point and did not correct the record.

II

A conviction obtained through the knowing use of false testimony violates the Due Process Clause when there is any reasonable likelihood that the false testimony could have affected the judgment of the jury. See Napue v. Illinois, 360 U. S. 264, 271 (1959). The standard is not whether the false testimony was decisive; it is whether the State's silence in the face of a known falsehood undermines confidence in the verdict.

Here, Sneed was the State's only direct witness. His credibility was the central issue at trial, and the jury was repeatedly told it could rely on his testimony as that of a reformed man speaking under oath. The undisclosed psychiatric record and the prosecution's awareness of the falsehood are, on this record, sufficient to establish a Napue violation.

III

We turn to the adequacy of the state-law ground. The Oklahoma Court of Criminal Appeals applied its Post-Conviction Procedure Act and concluded that Glossip's claim was procedurally barred. But the State itself joined Glossip in seeking relief and conceded the constitutional violation. In these circumstances, the procedural rule was not regularly applied to the question of federal law before the court, and we therefore reach the merits.

* * *

The judgment is reversed and the case is remanded for further proceedings consistent with this opinion.

It is so ordered.`,
        html_with_citations: null,
        clean_text: null,
        text_source: "plain_text",
        extracted_by_ocr: false,
        date_ingested: "2026-04-14T02:09:26.719774+00:00",
      },
    ],
    citations: [],
  },

  // Multi-opinion case — majority + concurrence + dissent.
  77: {
    case: {
      id: 77,
      source_docket_id: 71877961,
      court_id: "scotus",
      absolute_url:
        "/docket/71877961/learning-resources-inc-et-al-v-donald-j-trump-president-of-the-united-states-et-al/",
      slug: "learning-resources-inc-et-al-v-donald-j-trump-president-of-the-united-states-et-al",
      case_name:
        "Learning Resources, Inc., et al., Petitioners v. Donald J. Trump, President of the United States, et al.",
      case_name_short: "Learning Resources",
      docket_number: "24-1287",
      date_filed: "2025-06-01",
      date_argued: "2026-01-15",
      appeal_from_str: "United States Court of Appeals",
      originating_docket_number: null,
      has_audio: true,
      blocked: false,
      date_ingested: "2026-04-14T02:09:26.719774+00:00",
    },
    primary_opinion_id: 88,
    opinions: [
      {
        id: 88,
        source_opinion_id: 11266325,
        case_id: 77,
        cluster_id: 88,
        absolute_url: "/opinion/11266325/learning-resources-v-trump/",
        opinion_type: "010majority",
        author_id: 3001,
        author_str: null,
        author_display: "John G. Roberts, Jr.",
        per_curiam: false,
        page_count: 29,
        download_url: "https://example.org/opinions/learning-resources-majority.pdf",
        sha1: "majoritysha1",
        plain_text: "",
        html_with_citations: null,
        clean_text:
`LEARNING RESOURCES, INC., ET AL. v. TRUMP, PRESIDENT OF THE UNITED STATES, ET AL.

No. 24-1287. Argued January 15, 2026 — Decided April 28, 2026

CHIEF JUSTICE ROBERTS delivered the opinion of the Court.

Congress has delegated tariff powers only in explicit terms and subject to strict limits. The opinion explains why the statute at issue does not clearly authorize the asserted executive action.

I

The Constitution gives Congress, not the President, the power to lay and collect duties. Congress has, over time, delegated portions of that authority by statute — but the Court has long required that any such delegation be stated with clarity, particularly when it touches matters of vast economic and political significance.

II

The statute the Executive invokes here authorizes adjustments in response to defined emergencies. Petitioners contend, and we agree, that the categorical and durable tariff schedule announced under that authority exceeds the bounds of the delegation. The text speaks to discrete, time-limited responses; the program at issue is neither.

III

We do not foreclose all executive action under the statute. We hold only that the program before us cannot be sustained on the authority cited. Congress remains free to grant the Executive broader authority — but it must do so in terms the public can read and the courts can enforce.

The judgment of the Court of Appeals is reversed.

It is so ordered.`,
        text_source: "html",
        extracted_by_ocr: false,
        date_ingested: "2026-04-14T02:09:26.719774+00:00",
      },
      {
        id: 89,
        source_opinion_id: 11266326,
        case_id: 77,
        cluster_id: 88,
        absolute_url: "/opinion/11266326/learning-resources-v-trump-concurrence/",
        opinion_type: "040concurrence",
        author_id: 3007,
        author_str: null,
        author_display: "Amy Coney Barrett",
        per_curiam: false,
        page_count: 8,
        download_url: "https://example.org/opinions/learning-resources-concurrence.pdf",
        sha1: "concurrencesha1",
        plain_text: "",
        html_with_citations: null,
        clean_text:
`JUSTICE BARRETT, concurring.

I join the Court's judgment but would emphasize a narrower reading of the delegation issue and the interpretive rule applied here.

The Court need not, in my view, reach the broader questions about the major-questions doctrine to resolve this case. The statute's text alone, read in its ordinary sense, does not support the program. That is enough to decide the matter, and I would not reach further.

I write separately because the rule announced today is best understood as a faithful application of ordinary statutory interpretation — not as a freestanding clear-statement principle that operates independently of the text.`,
        text_source: "html",
        extracted_by_ocr: false,
        date_ingested: "2026-04-14T02:09:26.719774+00:00",
      },
      {
        id: 90,
        source_opinion_id: 11266327,
        case_id: 77,
        cluster_id: 88,
        absolute_url: "/opinion/11266327/learning-resources-v-trump-dissent/",
        opinion_type: "050dissent",
        author_id: 3009,
        author_str: null,
        author_display: "Clarence Thomas",
        per_curiam: false,
        page_count: 14,
        download_url: "https://example.org/opinions/learning-resources-dissent.pdf",
        sha1: "dissentsha1",
        plain_text: "",
        html_with_citations: null,
        clean_text:
`JUSTICE THOMAS, dissenting.

The dissent argues that the statutory delegation is broad enough and that the Court's reading improperly narrows the Executive's authority.

The statute speaks in capacious terms. Where Congress uses broad words, the Court's role is to give them their fair meaning — not to graft on additional limitations the text itself does not impose. Today's decision does just that, and it does so in the name of a doctrine that has no firm grounding in the original public meaning of the relevant constitutional provisions.

I would affirm the judgment below. I respectfully dissent.`,
        text_source: "html",
        extracted_by_ocr: false,
        date_ingested: "2026-04-14T02:09:26.719774+00:00",
      },
    ],
    citations: [],
  },
};

/* Friendly label for opinion_type codes. The numeric prefix is CourtListener's
 * sort key; we strip it and humanize. */
function opinionTypeLabel(code) {
  if (!code) return "Opinion";
  const stripped = code.replace(/^0\d{2}/, "");
  const map = {
    combined:    "Opinion",
    majority:    "Majority",
    plurality:   "Plurality",
    concurrence: "Concurrence",
    "concurrence-in-part": "Concurrence in part",
    dissent:     "Dissent",
    "dissent-in-part": "Dissent in part",
    "concurrence-in-part-and-dissent-in-part": "Concur/Dissent in part",
    seriatim:    "Seriatim",
    rehearing:   "Rehearing",
    "on-the-merits": "On the merits",
    "in-chambers": "In chambers",
    remittitur:  "Remittitur",
  };
  return map[stripped] || stripped.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) || "Opinion";
}

/* Friendly court name for known courts. */
function courtLabel(courtId) {
  const map = {
    scotus: "U.S. Supreme Court",
    ca1:    "U.S. Court of Appeals · 1st Cir.",
    ca2:    "U.S. Court of Appeals · 2d Cir.",
    ca9:    "U.S. Court of Appeals · 9th Cir.",
    cadc:   "U.S. Court of Appeals · D.C. Cir.",
  };
  return map[courtId] || courtId || "—";
}

/* Resolved opinion text — picks the populated field per `text_source`. */
function opinionText(op) {
  if (!op) return "";
  if (op.text_source === "html" && op.clean_text) return op.clean_text;
  if (op.plain_text) return op.plain_text;
  if (op.clean_text) return op.clean_text;
  return "";
}

/* Format ISO date as "Mar 4, 2024". Returns "—" for null/undefined. */
function formatDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

const caseApi = {
  /* Mirrors GET /cases/{case_id}. Resolves with the full payload, or
   * rejects with { status, message } on miss. Latency simulated for realism. */
  fetchCase(case_id) {
    return new Promise((resolve, reject) => {
      const id = Number(case_id);
      const hit = CASE_FIXTURES[id];
      const wait = 180 + Math.random() * 220;
      setTimeout(() => {
        if (!hit) {
          reject({ status: 404, message: `case ${id} not found` });
        } else {
          // Defensive: clone so callers can't mutate the fixture.
          resolve(JSON.parse(JSON.stringify(hit)));
        }
      }, wait);
    });
  },
  /* Tiny directory of cases for the prototype's case-jumper UI. The real
   * page won't need this — it lands directly on /cases/{id}. */
  list() {
    return Object.values(CASE_FIXTURES).map((c) => ({
      id: c.case.id,
      case_name_short: c.case.case_name_short,
      docket_number: c.case.docket_number,
      opinion_count: c.opinions.length,
    }));
  },
};

window.caseApi = caseApi;
window.opinionTypeLabel = opinionTypeLabel;
window.courtLabel = courtLabel;
window.opinionText = opinionText;
window.formatDate = formatDate;
