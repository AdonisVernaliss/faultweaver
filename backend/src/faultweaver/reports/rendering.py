"""Offline, dependency-free presentations of the canonical report document."""

import html
import re
from importlib.resources import files

from faultweaver.reports.schemas import ReportDocument

REPORT_CSP = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
_STYLE = files("faultweaver.reports").joinpath("report.css").read_text(encoding="utf-8")


def _escape(value) -> str:
    return html.escape(str(value), quote=True)


def _markdown(value) -> str:
    # Prose is plain text, never user-supplied Markdown/HTML. Escape line starts
    # and punctuation so links, headings, fences and raw HTML cannot be injected.
    escaped = re.sub(r"([\\`*_{}\[\]<>|!#=~])", r"\\\1", str(value)).replace("\r", "")
    return re.sub(r"(?m)^(\s*)([-+]|\d+\.)[ \t]", r"\1\\\2 ", escaped)


class Writer:
    def __init__(self, format_name: str):
        self.html = format_name == "html"
        self.parts: list[str] = []

    def heading(self, level, title, anchor=None):
        if self.html:
            self.parts.append(
                f"<h{level}"
                + (f' id="{_escape(anchor)}"' if anchor else "")
                + f">{_escape(title)}</h{level}>"
            )
        else:
            self.parts.append("#" * level + " " + _markdown(title) + "\n")

    def paragraph(self, text):
        if text:
            self.parts.append(f"<p>{_escape(text)}</p>" if self.html else _markdown(text) + "\n")

    def table(self, headings, rows, *, link_first=False):
        if self.html:
            head = "".join(f'<th scope="col">{_escape(h)}</th>' for h in headings)
            body = []
            for row in rows:
                cells = []
                for index, value in enumerate(row):
                    content = _escape(value)
                    if index == 0 and link_first:
                        content = f'<a href="#{_escape(value)}">{content}</a>'
                    cells.append("<td>" + content + "</td>")
                body.append("<tr>" + "".join(cells) + "</tr>")
            self.parts.append(
                f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"
            )
        else:

            def row_text(row):
                return "| " + " | ".join(_markdown(v).replace("\n", " ") for v in row) + " |"

            self.parts.append(
                row_text(headings)
                + "\n"
                + row_text(["---"] * len(headings)).replace("\\-", "-")
                + "\n"
                + "\n".join(row_text(row) for row in rows)
                + "\n"
            )

    def ordered(self, items, *, attack_path=False):
        if not items:
            return
        if self.html:
            self.parts.append(
                "<ol"
                + (' class="attack-path"' if attack_path else "")
                + ">"
                + "".join(f"<li>{_escape(item)}</li>" for item in items)
                + "</ol>"
            )
        else:
            self.parts.append(
                "\n".join(
                    f"{i}. {_markdown(item).replace(chr(10), chr(10) + '   ')}"
                    for i, item in enumerate(items, 1)
                )
                + "\n"
            )

    def code(self, text):
        if self.html:
            self.parts.append(f"<pre><code>{_escape(text)}</code></pre>")
        else:
            runs = re.findall(r"`+", text)
            fence = "`" * max(3, 1 + max((len(run) for run in runs), default=0))
            self.parts.append(f"{fence}text\n{text}\n{fence}\n")


def render_document(document: ReportDocument, format_name: str) -> str:
    writer = Writer(format_name)
    report = document.report
    if writer.html:
        writer.parts.append("<header><p>FAULTWEAVER / WEB &amp; API SECURITY ASSESSMENT</p>")
    writer.heading(1, report.title)
    writer.paragraph(
        f"{document.engagement.name} · {report.display_id} · "
        + (f"Revision {report.revision}" if report.revision else "DRAFT PREVIEW")
    )
    writer.paragraph(f"Engagement status: {document.engagement.status}")
    if report.generated_at:
        writer.paragraph(f"Generated: {report.generated_at.isoformat()}")
    writer.paragraph("Confidential assessment material. Share only with authorized recipients.")
    if writer.html:
        writer.parts.append(
            '</header><nav aria-label="Report sections">'
            + "".join(
                f'<a href="#{anchor}">{label}</a>'
                for anchor, label in [
                    ("summary", "Summary"),
                    ("scope", "Scope"),
                    ("findings", "Findings"),
                    ("chains", "Attack Chains"),
                    ("retests", "Retests"),
                    ("evidence", "Evidence"),
                ]
            )
            + "</nav>"
        )
    writer.heading(2, "Executive Summary", "summary")
    writer.paragraph(
        report.executive_summary or "No executive interpretation supplied by the operator."
    )
    writer.heading(2, "Scope", "scope")
    writer.paragraph(
        "Configured authorization scope at generation time; "
        "discovered routes do not expand authorization."
    )
    writer.table(
        ["Scheme", "Host", "Port", "Path restriction", "Active"],
        [
            [s.scheme, s.host, s.port, s.path_prefix, "Yes" if s.active else "No"]
            for s in document.scope
        ],
    )
    writer.heading(2, "Methodology")
    writer.paragraph(report.methodology or "No methodology supplied by the operator.")
    writer.heading(2, "Assessment Limitations")
    writer.paragraph(
        report.limitations
        or "No assessment limitations supplied; this does not imply unrestricted coverage."
    )
    writer.heading(2, "Severity Summary")
    writer.paragraph(
        "Included confirmed Findings only. Severity is independent of remediation status; "
        "Fixed and Accepted Risk remain in these counts."
    )
    writer.table(
        ["Severity", "Count"], [[key, value] for key, value in document.summary.severity.items()]
    )
    writer.heading(2, "Findings Overview", "findings")
    writer.table(
        ["ID", "Severity", "Title", "Status", "Asset", "Latest retest"],
        [
            [f.display_id, f.severity, f.title, f.status, f.affected_asset, f.latest_retest]
            for f in document.findings
        ],
        link_first=True,
    )
    if not document.findings:
        writer.paragraph(
            "No confirmed Findings are included. This is not a statement that the assessed "
            "application is free of vulnerabilities."
        )
    for finding in document.findings:
        if writer.html:
            writer.parts.append('<article class="finding">')
        writer.heading(2, f"{finding.display_id} — {finding.title}", finding.display_id)
        writer.paragraph(
            f"Severity: {finding.severity} · Status: {finding.status}"
            + (" · Archived" if finding.archived else "")
        )
        writer.paragraph(
            f"Affected asset: {finding.affected_asset}" if finding.affected_asset else ""
        )
        if finding.affected_endpoints:
            writer.heading(3, "Affected Endpoints")
            writer.code("\n".join(finding.affected_endpoints))
        for title, body in [("Description", finding.description), ("Impact", finding.impact)]:
            if body:
                writer.heading(3, title)
                writer.paragraph(body)
        if finding.reproduction_steps:
            writer.heading(3, "Reproduction Steps")
            writer.ordered(finding.reproduction_steps)
        writer.heading(3, "Preserved Finding Evidence")
        writer.paragraph(", ".join(finding.finding_evidence_ids) or "No immutable Evidence linked.")
        writer.paragraph(
            "Original and supporting snapshots remain preserved here. Retest Evidence is "
            "referenced separately below; a snapshot may support both."
        )
        if finding.remediation:
            writer.heading(3, "Remediation")
            writer.paragraph(finding.remediation)
        if finding.references:
            writer.heading(3, "References")
            writer.ordered(finding.references)
        writer.heading(3, "Latest Retest")
        writer.paragraph(finding.latest_retest)
        if writer.html:
            writer.parts.append("</article>")
    writer.heading(2, "Attack Chains", "chains")
    if not document.attack_chains:
        writer.paragraph("No Attack Chains included.")
    for chain in document.attack_chains:
        writer.heading(3, f"{chain.display_id} — {chain.title}", chain.display_id)
        writer.paragraph(f"Status: {chain.status}")
        writer.paragraph(chain.description)
        writer.ordered(
            [
                f"{step.finding_id or 'Intermediate step'} — {step.title}"
                + (f"\n{step.description}" if step.description else "")
                + (f"\nEvidence: {', '.join(step.evidence_ids)}" if step.evidence_ids else "")
                for step in chain.steps
            ],
            attack_path=True,
        )
        writer.paragraph(
            f"Resulting impact: {chain.resulting_impact}" if chain.resulting_impact else ""
        )
        writer.paragraph(f"Evidence: {', '.join(chain.evidence_ids)}" if chain.evidence_ids else "")
    writer.heading(2, "Retest Results", "retests")
    writer.paragraph(f"Retested Findings: {document.summary.retested_findings}")
    if document.summary.retested_findings:
        writer.table(
            ["Latest result", "Findings"], list(document.summary.latest_retest_results.items())
        )
    for retest in document.retests:
        writer.heading(3, f"{retest.display_id} — {retest.finding_id}", retest.display_id)
        writer.paragraph(
            f"{retest.status} · {retest.tested_at.isoformat()} · "
            + ("Latest result" if retest.latest else "Historical result")
        )
        writer.paragraph(retest.operator_notes)
        writer.paragraph("Retest Evidence: " + (", ".join(retest.evidence_ids) or "None linked"))
    writer.heading(2, "Conclusion")
    writer.paragraph(report.conclusion or "No conclusion supplied by the operator.")
    writer.heading(2, "Appendix — Preserved Evidence", "evidence")
    writer.paragraph(
        "Bounded redacted excerpts from immutable Evidence, not live target responses. "
        "Review all exports for incidental confidential content before sharing."
    )
    for evidence in document.evidence:
        writer.heading(3, f"{evidence.display_id} — {evidence.title}", evidence.display_id)
        writer.paragraph(f"{evidence.evidence_type} · Captured {evidence.captured_at.isoformat()}")
        for excerpt in evidence.excerpts:
            writer.paragraph(excerpt.label)
            writer.code(excerpt.text)
    if document.assessments:
        writer.heading(2, "Appendix — Baseline Assessment Metadata")
        writer.paragraph("Bounded automated activity is not proof of complete assessment coverage.")
        writer.table(
            ["Run", "Target", "Status", "Requests"],
            [[a.display_id, a.target_url, a.status, a.request_count] for a in document.assessments],
        )
    if document.warnings:
        writer.heading(2, "Report Review Notes")
        writer.ordered(document.warnings)
    if writer.html:
        writer.parts.append(
            f"<footer><p>Faultweaver {_escape(document.application_version)} · "
            f"Report schema {_escape(document.report_schema_version)} · "
            f"Renderer {_escape(document.renderer_version)}</p></footer>"
        )
        return (
            '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta http-equiv="Content-Security-Policy" content="{_escape(REPORT_CSP)}">'
            f"<title>{_escape(report.title)}</title><style>{_STYLE}</style></head><body><main>"
            + "\n".join(writer.parts)
            + "</main></body></html>\n"
        )
    return "\n".join(writer.parts) + "\n"
